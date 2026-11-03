"""Explore's questions (POST /api/ask): a spoken or typed question about a published figure,
answered by Muse Spark from that figure alone.

- Audio is a WAV of mono 16-bit PCM at 16 or 24 kHz (the transcribe endpoint's input). It
  goes to the file transcribe endpoint, push to talk, with the figure's part, line and group
  names as keyword hints (`keywords`, docs: voice/schemas, Transcribe Request).
- The answer prompt (app/prompts/ask_answer.v1.json) gets the published regions.json in
  words: title, subject, summary, each touchable part with its neighbors and their
  directions (computed in code when the figure was laid out), what it is inside, its group
  and the teacher's description; the parts not touchable yet; the lines; the part under
  the finger and the ones touched just before. And the figure image. Spark answers at low
  reasoning effort, in a fixed shape: answer_text, source, cited_part_ids.
- Code has the last word: off_figure and unsure get fixed wording that sends the student
  to the teacher; a teacher_description answer must cite a part that has a description,
  or it is unsure; the answer keeps two sentences at most; cited ids are the figure's.
- At most SESSION_QUESTIONS per Explore session. Every Meta call goes through LiveCaller,
  so it is metered and in the ledger."""

import io
import re
import time
import wave
from collections import defaultdict
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

from app.meta.live import MalformedResponseError
from app.models.regions import Region, RegionsFile

Source = Literal["figure", "teacher_description", "off_figure", "unsure"]
PROMPT = "ask_answer.v2.json"
TEXT_PROMPT = "ask_answer_text.v2.json"  # the latency experiment's variant: no figure image
SESSION_QUESTIONS = 50
CALLS_PER_QUESTION = 2  # transcribe, then Spark
MAX_SENTENCES = 2
RECENT = 3
WAV_RATES = (16000, 24000)
SAMPLE_BYTES = 2

OFF_FIGURE = "This figure does not show that. Ask your teacher."
UNSURE = "I am not sure from this figure. Ask your teacher."
NOT_HEARD = "I did not catch a question. Hold the screen and ask again."
CAPPED = f"That is {SESSION_QUESTIONS} questions for this session. Ask your teacher."
FAILED = "Questions are not working right now. Labels still work."
# A question gets this long, transcribe and Spark together; then the route says FAILED. The
# slowest Spark answer in the committed live evals is 18.7 s (eval/qa/scores.json, Nov 3,
# answer prompt v2, 73 questions) and transcribe p95 is 1.4 s (eval/qa/VOICE.md): about
# 20.1 s, so 30 s is 1.5 times that. Explore gives up at 35 s
# (apps/web/src/explore/camera.ts ASK_TIMEOUT_MS), after this sentence would have arrived.
DEADLINE_S = 30.0


def _ids(f: RegionsFile) -> list[str]:
    return list(dict.fromkeys(r.id.partition("_")[0] for r in f.regions))


def answer_schema(f: RegionsFile) -> dict[str, Any]:
    """Spark's answer, per figure: {"reply": one of two shapes}. A teacher_description reply
    must name a described_part_id from the parts that have a teacher's description, so the
    citation rule holds by construction: the Model API constrains decoding to the schema
    ("decoding itself is constrained, so the output is guaranteed to conform",
    dev.meta.ai/docs/structured-output). anyOf sits below the root, as strict mode requires
    ("anyOf is supported below the root"), every object sets additionalProperties false and
    requires all its keys. A figure with no description has the second shape only."""
    ids = _ids(f)
    described = list(dict.fromkeys(r.id.partition("_")[0] for r in f.regions if r.description))
    cites = {"type": "array", "items": {"type": "string", "enum": ids}}
    other: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "required": ["source", "answer_text", "cited_part_ids"],
        "properties": {
            "source": {"type": "string", "enum": ["figure", "off_figure", "unsure"]},
            "answer_text": {"type": "string"},
            "cited_part_ids": cites,
        },
    }
    shapes = [other]
    if described:
        shapes.insert(0, {
            "type": "object",
            "additionalProperties": False,
            "required": ["source", "answer_text", "described_part_id", "cited_part_ids"],
            "properties": {
                "source": {"type": "string", "enum": ["teacher_description"]},
                "answer_text": {"type": "string"},
                "described_part_id": {"type": "string", "enum": described},
                "cited_part_ids": cites,
            },
        })  # fmt: skip
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["reply"],
        "properties": {"reply": {"anyOf": shapes}},
    }


_READERS = {
    "k5": "a student in kindergarten to grade 5",
    "6_8": "a student in grades 6 to 8",
    "9_12": "a student in grades 9 to 12",
    "college": "a college student",
}
_DIRECTIONS = {
    "up": "above",
    "down": "below",
    "left": "to the left",
    "right": "to the right",
    "up_left": "above and to the left",
    "up_right": "above and to the right",
    "down_left": "below and to the left",
    "down_right": "below and to the right",
    "inside": "inside it",
    "around": "around it",
}
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_DASHES = re.compile("\\s*[\\u2014\\u2013]\\s*")  # em and en dashes, never spoken

RegionId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_]{1,32}$")]


class AskRequest(BaseModel):
    """What Explore sends with a question; the audio, when spoken, travels beside it."""

    model_config = ConfigDict(extra="forbid")

    figure_id: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    version: int | None = None  # the published version Explore loaded; None for the latest
    question: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] = ""
    region_id: RegionId | None = None
    recent_region_ids: Annotated[list[RegionId], Field(max_length=10)] = []
    session_id: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,64}$")] = "none"


class SparkAnswer(BaseModel):
    """Spark's answer as it came back."""

    answer_text: str
    source: Source
    cited_part_ids: list[str]
    described_part_id: str | None = None  # a teacher_description reply's described part


class Answer(BaseModel):
    """What /api/ask returns."""

    transcript: str
    answer: str  # what Explore says
    source: Source
    cited_part_ids: list[str]
    spark: SparkAnswer | None  # as Spark gave it, before code's last word
    timings_ms: dict[str, float]
    prompt: str = PROMPT
    # Code turned a teacher_description answer into unsure: no described part was cited.
    # The schema makes this impossible on the Model API; counted on the eval in case.
    rule_fallback: bool = False


class WavError(ValueError):
    """Audio the transcribe endpoint would not take."""


def check_wav(data: bytes) -> float:
    """The clip's length in seconds; raises WavError unless it is mono 16-bit PCM WAV at
    16 or 24 kHz."""
    try:
        with wave.open(io.BytesIO(data)) as w:
            ok = (
                w.getnchannels() == 1
                and w.getsampwidth() == SAMPLE_BYTES
                and w.getframerate() in WAV_RATES
            )
            if not ok:
                raise WavError("Audio must be mono 16-bit PCM WAV at 16 or 24 kHz.")
            return float(w.getnframes() / w.getframerate())
    except (wave.Error, EOFError) as exc:
        raise WavError("The audio is not a WAV file.") from exc


def keywords(f: RegionsFile) -> list[str]:
    """The figure's part, line and group names, once each, for the transcribe hints."""
    names = [r.label for r in f.regions]
    names += [x.label for x in f.lines or []]
    names += [r.group for r in f.regions if r.group]
    names += [t.label for t in f.needs_teacher or []]
    return list(dict.fromkeys(n.strip() for n in names if n.strip()))


def _main(regions: list[Region]) -> list[Region]:
    """One region per part: pieces after the first (<part>_<k>) are left out."""
    return [r for r in regions if "_" not in r.id]


def _part_line(r: Region, by_id: dict[str, Region]) -> str:
    out = f"- {r.id}: {r.label}."
    near = [
        f"{n.id} {by_id[n.id].label} ({_DIRECTIONS.get(n.direction, n.direction)})"
        for n in r.neighbors or []
        if n.id in by_id and "_" not in n.id
    ]
    if near:
        out += f" Next to: {', '.join(near)}."
    if r.parent and r.parent in by_id:
        out += f" Inside {by_id[r.parent].label}."
    if r.group:
        out += f" Part of the {r.group}."
    if r.description:
        out += f' Teacher\'s description: "{r.description}"'
    return out


def _named(rid: str | None, by_id: dict[str, Region]) -> str | None:
    if rid is None:
        return None
    r = by_id.get(rid) or by_id.get(rid.partition("_")[0])
    return None if r is None else f"{r.id} {r.label}"


def prompt_text(template: str, f: RegionsFile, req: AskRequest, question: str) -> str:
    """The user message: the published figure in words, the touch context and the question."""
    touch = _main([r for r in f.regions if r.touchable])
    by_id = {r.id: r for r in touch}
    untouchable = [r.label for r in f.regions if not r.touchable]
    untouchable += [t.label for t in f.needs_teacher or []]
    lines = []
    for x in f.lines or []:
        lines.append(
            f"{x.label}, between {x.between[0]} and {x.between[1]}" if x.between else x.label
        )
    recent = [n for n in (_named(r, by_id) for r in req.recent_region_ids[-RECENT:]) if n]
    return template.format(
        title=f.title,
        subject=f.subject.label if f.subject else "not given",
        summary=f.summary,
        reader=_READERS.get(f.grade_band or "", "a school student"),
        count=len(touch),
        parts="\n".join(_part_line(r, by_id) for r in touch) or "none",
        untouchable="; ".join(dict.fromkeys(untouchable)) or "none",
        lines="; ".join(lines) or "none",
        current=_named(req.region_id, by_id) or "no part",
        recent=", ".join(recent) or "nothing",
        question=question.replace('"', "'"),
    )


def final(spark: SparkAnswer, f: RegionsFile) -> tuple[str, Source, list[str]]:
    """Code's last word on Spark's answer: what Explore says, the source and the cites."""
    ids = {r.id.partition("_")[0] for r in f.regions}
    described = {r.id.partition("_")[0] for r in f.regions if r.description}
    named = [*([spark.described_part_id] if spark.described_part_id else []), *spark.cited_part_ids]
    cited = list(dict.fromkeys(i.partition("_")[0] for i in named if i.partition("_")[0] in ids))
    source = spark.source
    if source == "teacher_description" and not set(cited) & described:
        source = "unsure"
    text = _DASHES.sub(", ", spark.answer_text).strip()
    if source in ("figure", "teacher_description") and not text:
        source = "unsure"
    if source == "off_figure":
        return OFF_FIGURE, source, []
    if source == "unsure":
        return UNSURE, source, []
    sentences = _SENTENCE_END.split(text)
    return " ".join(sentences[:MAX_SENTENCES]), source, cited


class SessionCap:
    """Questions per Explore session, counted in this process."""

    def __init__(self, cap: int = SESSION_QUESTIONS) -> None:
        self.cap = cap
        self.asked: dict[str, int] = defaultdict(int)

    def take(self, session: str) -> bool:
        if self.asked[session] >= self.cap:
            return False
        self.asked[session] += 1
        return True


def ms_since(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 1)


class Asker:
    """Answers questions about published figures. figure(figure_id, version) gives the
    published regions.json and the figure image as PNG bytes."""

    def __init__(
        self,
        client: Any,  # MetaClient
        system: str,
        user: str,
        figure: Any,  # Callable[[str, int | None], tuple[RegionsFile, bytes]]
        cap: SessionCap | None = None,
        image: bool = True,
    ) -> None:
        self.client, self.system, self.user, self.figure = client, system, user, figure
        self.cap = cap or SessionCap()
        self.image = image  # False: Spark gets the figure data in words only

    async def ask(self, req: AskRequest, audio: bytes | None) -> Answer:
        """Raises WavError for bad audio and QuestionCapError past the session's cap; a Meta
        call that fails raises its own error."""
        t0 = time.perf_counter()
        f, png = self.figure(req.figure_id, req.version)
        if audio is not None:
            check_wav(audio)
        if not self.cap.take(req.session_id):
            raise QuestionCapError(CAPPED)
        client = self.client.for_job()
        client.cap_calls(CALLS_PER_QUESTION)
        timings: dict[str, float] = {}
        question = req.question
        if audio is not None:
            t = time.perf_counter()
            question = await client.transcribe(req.figure_id, audio, keywords(f))
            timings["transcribe"] = ms_since(t)
        if not question.strip():
            timings["server"] = ms_since(t0)
            return Answer(transcript=question, answer=NOT_HEARD, source="unsure",
                          cited_part_ids=[], spark=None, timings_ms=timings)  # fmt: skip
        user = prompt_text(self.user, f, req, question)
        t = time.perf_counter()
        image = png if self.image else None
        schema = answer_schema(f)
        raw = await client.answer(req.figure_id, image, self.system, user, schema, question)
        timings["spark"] = ms_since(t)
        try:
            spark = SparkAnswer.model_validate(raw.get("reply", raw))
        except ValidationError as exc:
            raise MalformedResponseError("the answer does not fit the schema") from exc
        text, source, cited = final(spark, f)
        fallback = spark.source == "teacher_description" and source == "unsure"
        timings["server"] = ms_since(t0)
        return Answer(transcript=question, answer=text, source=source, cited_part_ids=cited,
                      spark=spark, timings_ms=timings, rule_fallback=fallback)  # fmt: skip


class QuestionCapError(Exception):
    """The session asked SESSION_QUESTIONS already."""
