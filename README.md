# Talking Tactile

[![tests](https://github.com/DeepakKTS/talking-tactile/actions/workflows/tests.yml/badge.svg)](https://github.com/DeepakKTS/talking-tactile/actions/workflows/tests.yml)

A blind student rests a finger on a raised drawing of a heart. The phone in a stand above the
sheet plays a short tone, then says "left ventricle". The student holds the screen, asks "what
does it do?", and hears an answer taken from this figure and its teacher's notes only.

Talking Tactile turns a printed STEM figure into a raised sheet that talks. It is for teachers
and transcribers who make tactile graphics, and for the blind students who learn from them.

**Watch the demo (3 minutes):** `<VIDEO_URL>`

**Project site:** https://deepakkts.github.io/talking-tactile/ (how it works, the two sheets
with their print PDFs, and a pointer demo that speaks part names in the browser).

Built solo for the Meta Global AI Developer Hackathon (Indie track) on `muse-spark-1.3`,
`sam-3.1` and `muse-voice-transcribe-1.0`, through the Meta Model API.

## How it works

![The teacher's upload, stages S0 to S5 with the Meta model at each, the printed sheet, and the phone's touch and question paths, with the safety rules marked](docs/submission/architecture.svg)

The teacher (Author mode, on a computer):

1. Upload a figure (PNG, JPEG or a PDF page).
2. Muse Spark lists the parts and plans each for touch: an area, a line or a group.
3. SAM 3.1 outlines each part from points Spark placed. Code lays out the sheet in
   millimeters: gaps, textures, point symbols, braille.
4. Review: fix an outline with two clicks, merge, rename, describe. Check each part.
5. Publish, print at 100 percent, raise the lines (swell paper or puffy paint).

The student (Explore mode, on a phone, no screen needed):

1. A sighted helper taps the four lettered corners once.
2. Touch a part: a texture tone, then its name. Touch needs no internet.
3. Hold the screen and talk. "More", "repeat" and "where is the aorta" are handled on the
   phone. Any other question goes to Muse Voice Transcribe, then Muse Spark, which answers
   from the figure or sends the student to the teacher.

## The hard parts

- **SAM text prompts found no heart parts, so Spark places points.** "left ventricle",
  "aorta" and "right atrium" gave zero instances; "heart" gave the whole heart
  (`spikes/sam.md`). Spark now places points and SAM segments from them: 44 point prompts,
  44 single-instance answers. Code keeps points off text and leader lines and retries a mask
  that spills onto a neighbor (`services/api/app/pipeline/s2_points.py`).
- **S1 plans for touch.** Spark marks each part as an area, a line or a group, with
  parents. A valve is a line, spoken when the finger crosses it. Vessels drawn as one shape
  come back as a merge proposal. Heart: 15 areas, 4 lines, one merge for the aortic arch
  (`eval/plan/RESULTS.md`). On a private test figure, planning raised touchable parts from
  5 of 12 to 10 of 10 (`TRACKER.html`, decision of Oct 30).
- **Touch only after the teacher confirms.** Automatic safety rules failed on a different
  figure each time: the aortic arch's members overlap, a shaded brain's lobes are one drawn
  region, clipping cut Japan's regions in half (`TRACKER.html`, decision of Oct 30). A part
  is now touchable only once the teacher checks it (`services/api/app/pipeline/edits.py`);
  overlap detection became a warning (`services/api/app/geometry/overlap.py`).
- **Grounded answers under a strict schema.** Each figure gets its own JSON schema: the
  answer's source (figure, teacher description, off figure, unsure) and the parts it cites,
  from that figure's ids only. An off-figure answer becomes a fixed sentence that sends the
  student to the teacher (`services/api/app/ask.py`). In the eval, all 9 off-figure questions
  went to the teacher, and all 7 prompt injections passed: 6 went to the teacher, 1 was
  answered from the teacher's description (`eval/qa/RESULTS.md`, `eval/qa/README.md`).
- **Cold start on iOS.** On the iPhone, the hand tracker's first GPU start gave no frame in
  5 s; a second tap ran at 20.8 fps (`TRACKER.html`, task d8-46). The CPU fallback timer now
  starts only once the GPU model is ready and has a frame (`apps/web/src/explore/warmup.ts`).
  The Gate B page runs a port held to it by `spikes/tracking/test/parity.test.mjs`.

The model never guesses geometry. Directions, neighbors and distances come from code.

## Results

| What | Result | File |
|---|---|---|
| Part plan, touchable areas (live recordings) | Heart 14 of 15, Japan regions 9 of 9, brain 5 of 6, flower 7 of 13 | `eval/plan/RESULTS.md` |
| S2 against graded reference masks | Heart: 0 of 4 regressed (3 held, 1 improved). Flower: none of 5 held | `eval/plan/RESULTS.md` |
| Questions, live, source right | Heart 36 of 38, brain 35 of 35 | `eval/qa/RESULTS.md` |
| Picture questions (shape, biggest, top) | Heart 5 of 6, brain 6 of 6; 3 of 6 each without the image | `eval/qa/RESULTS.md`, `eval/qa/RESULTS_image_no_image.md` |
| Release to first spoken word, Mac, live | p50 5.0 s over 12 questions; two took 13.8 and 14.7 s | `eval/qa/VOICE.md` |
| Release to first spoken word, iPhone | <!-- tt:voice-device -->not measured: the latency film was cut<!-- /tt:voice-device --> (the Mac figure is above) | `eval/gate-b/README.md` |
| Touch to tone, iPhone | <!-- tt:earcon-device -->not measured: the latency film was cut<!-- /tt:earcon-device --> | `eval/gate-b/README.md` |
| Fingertip error on the 9-point sheet (Gate B, goal 4 mm) | <!-- tt:gate-b -->not measured<!-- /tt:gate-b --> | `eval/gate-b/README.md` |
| Meta credits spent | $5.31 of $150 (Nov 3) | `eval/live/ledger.jsonl` |

## Limitations

- **Not yet tested with blind students or teachers.** No tester session or expert review
  happened before the deadline.
<!-- tt:limits-touch -->
- **Touch accuracy on the phone is not measured yet.** Gate B (`eval/gate-b/README.md`) has
  not run on the demo iPhone.
<!-- /tt:limits-touch -->
- **Latency on the phone was not measured.** The latency film was cut, so touch to tone and
  release to first spoken word on the iPhone have no numbers. The only measured figure is the
  Mac's, live in Chrome: release to first spoken word p50 5.0 s over 12 questions, two at 13.8
  and 14.7 s (`eval/qa/VOICE.md`).
- **A sighted helper sets the corners**, and nothing detects the phone or the sheet moving
  afterward (`docs/EDGE_CASES.md` X5, X6).
- **Continuous vessels are merged by the teacher.** The aorta and its branches are one drawn
  shape with no boundary to split; Spark proposes the merge (`PLAN.md` section 11).
- **Questions need the network** and are slow: 5.0 s at p50 on a Mac, some near 15 s, most of
  it Spark (`eval/qa/VOICE.md`), against a 2.0 s budget in `RULES.md`. Touch needs no
  internet once the sheet has loaded from the Mac.
- **Voice is tested on synthetic speech only**, in English (`eval/qa/VOICE.md`).
- **Small parts are hard.** 6 of the flower's 13 areas need the teacher (`eval/plan/RESULTS.md`).
- No undo for a merge, delete or check (`docs/EDGE_CASES.md` E4). HEIC photos are refused.

## Try it in mock mode (no key, no phone)

Mock mode replays recorded live answers (`fixtures/recorded/`). No key, no network calls.

Needs macOS or Linux, [uv](https://docs.astral.sh/uv/), Node 24 and liblouis
(`brew install liblouis`, or `apt install liblouis-bin liblouis-data`). On Linux the heart
replays; the Commons brain does not, because its image normalizes to other pixels there, so
no recording of it matches (`services/api/tests/recorded_png.py`).

```
git clone https://github.com/DeepakKTS/talking-tactile.git
cd talking-tactile
make install
MOCK_META=1 make dev        # API on :8000, web on http://localhost:5173
```

npm's 11 moderate advisories are in lint tools only (`docs/SECURITY.md`).

1. Once the API answers (the first start can take 40 s), open http://localhost:5173/author,
   choose `fixtures/heart.png`, keep the default options and press "Make a tactile sheet".
2. Wait for "Ready for review." (about 25 s). The "Needs you" list shows the septum, and a
   merge proposal shows the aortic arch.
3. Press "Mark all parts checked", confirm, then "Publish for students".
4. Press "Open version 1 in Explore", then Enter or "Start exploring": Explore says the sheet's
   title and summary. Touch needs a camera over the printed sheet (the live setup below).

On this path a typed question says "Questions are not working right now": mock answers exist
only for the sheets as the question eval published them (the heart with the aortic arch merged
and two teacher descriptions; the brain at grade band "6 to 8"). To try questions, on a fresh
clone run `make demo-sheets` before `MOCK_META=1 make dev` (about a minute, no network). It
publishes both sheets that way and prints their Explore links; a question from
`eval/qa/questions.jsonl`, typed with no finger on the sheet, then gets its recorded answer.

`make check` runs every test, lint and type check, as CI does.

## Run it live with a phone

Copy `.env.example` to `services/api/.env` and set `MODEL_API_KEY`. `make preflight` checks
the setup; `make demo-live` starts the API, the phone's HTTPS server and the Gate B page and
prints the iPhone URLs. `docs/DEMO.md` has every step, including the phone certificate.

## Privacy and safety

- Every call uses a Standard model; Meta's docs say Standard content is not used to train
  Meta models. The backend refuses a Contributor model id (`services/api/app/config.py`).
- The billing page said on Oct 27: "While using free credits your content may be used for
  product improvement". Stop using free credits before a class uses it.
- A question's audio and words are not kept on disk or in logs
  (`services/api/tests/test_ask_retention.py`).
- Camera frames stay on the phone. The API key stays on the backend.

Details: `docs/PRIVACY.md`, `docs/SECURITY.md`.

## Credits and licenses

Code: Apache License 2.0 (`LICENSE`, `NOTICE`). Figures and everything made from them keep
their own licenses (`ATTRIBUTION.md`):

- "Heart diagram-en.svg by ZooFari, CC BY-SA 3.0, via Wikimedia Commons. Resized and placed on
  a white background." The tactile sheet and files made from it are shared under CC BY-SA 3.0.
- "Blausen 0111 BrainLobes.png by BruceBlaus (Blausen.com staff, Medical gallery of Blausen
  Medical 2014), CC BY 3.0, via Wikimedia Commons."

MediaPipe Hand Landmarker (Apache 2.0), liblouis, and `meta-sam-parser` (Meta's SAM License,
installed from PyPI, not distributed here).

## Documents

`PLAN.md` design, `RULES.md` hard rules, `docs/EDGE_CASES.md` edge cases,
`docs/DEMO.md` filming runbook, `docs/review/` independent reviews, `CONTRIBUTING.md`.
