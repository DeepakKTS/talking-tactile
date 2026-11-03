# Submission form text

Ready to paste. Every number names the committed file it comes from. Fields marked "not
measured" are filled from `eval/gate-b/` once the phone measurements exist.

## Before pasting

- Track: **Indie**. Confirmed by Deepak, Nov 3.
- Problem statement: **Push the Frontier**. Confirmed by Deepak, Nov 3. The idea: an ordinary
  camera learns what a finger is touching on a printed sheet, with only four printed corner
  marks on it.
- Public GitHub repository: https://github.com/DeepakKTS/talking-tactile (Deepak makes it
  public on Nov 3).
- Demo video: `<VIDEO_URL>`
- Coding tool: the code was written with Claude Code. Muse Code was not used; nothing below
  claims it.

## Team Name

Talking Tactile

## Project Description

Talking Tactile turns a printed STEM figure into a raised sheet that talks. A blind student
touches a part of a raised heart, and a phone in a stand above the sheet plays a texture tone
and says "left ventricle". Holding the screen, the student asks a question out loud and hears
an answer taken from that figure and the teacher's notes only.

A teacher uploads a textbook figure. Muse Spark reads it and plans each part for touch: an
area, a line or a group. SAM 3.1 outlines each part from points Spark placed. Code, not a
model, lays out the sheet: gaps, textures, point symbols and braille. Nothing is touchable
until the teacher checks it, and publishing refuses a sheet that breaks a tactile rule.

On the phone, MediaPipe finds the fingertip in a Web Worker, and the sheet's printed corners
map it to millimeters. Labels and tones work offline. Questions go through Muse Voice
Transcribe, with the figure's part names as hints, to Muse Spark under a strict schema. Live,
36 of 38 heart questions and 35 of 35 brain questions were answered from the right source
(`eval/qa/RESULTS.md`).

## Describe your use of Meta products to build the submitted project

All calls go through the Meta Model API (`https://api.meta.ai/v1`) from the backend, on
Standard models. The backend refuses to start with a Contributor model id, and the API key
never reaches the browser. Every call is logged with its price: $5.31 of the $150 credits
spent (`eval/live/ledger.jsonl`, Nov 3).

1. Reading the figure (S1), Muse Spark (`muse-spark-1.3`). A first call, with the image,
   lists the parts as short phrases with the subject, a summary and a verdict (make tactile,
   or describe in words only). A second call plans for touch under a JSON schema: each part an
   area, a line or a group, with its parent and points on the figure. Result: on the heart,
   15 areas, 4 lines (the valves) and one merge proposal (the aortic arch); touchable areas
   14 of 15 on the heart, 9 of 9 on a map of Japan, 5 of 6 on a brain, 7 of 13 on a flower
   (`eval/plan/RESULTS.md`).
2. Outlining each part (S2), SAM 3.1 (`sam-3.1`). One point-prompt call per part, four at a
   time, from Spark's points, with a neighbor's points as negatives on a retry. A concept
   prompt for the subject gives the silhouette, raised on the sheet. The teacher's "Fix
   outline" sends the teacher's clicks as new point prompts. Result: 44 point prompts, 44 answers with
   one instance (`spikes/sam.md`); on the heart, 0 of 4 graded reference parts regressed
   (`eval/plan/RESULTS.md`).
3. Hearing the question, Muse Voice Transcribe (`muse-voice-transcribe-1.0`). The phone
   records 16 kHz mono WAV while the screen is held; the backend sends it with the figure's
   part, line and group names as keywords. Commands such as "where is the aorta" are then
   handled on the phone with no further call. Result: on 3 synthetic clips every word was
   recognized, with one doubled "the" when hints were on; transcribe p50 941 ms on the server
   (`eval/qa/VOICE.md`). Accuracy on a real voice is not
   measured.
4. Answering (Explore), Muse Spark (`muse-spark-1.3`). The question goes with the published
   figure, its image and its parts in words, under a strict JSON schema built per figure: the
   answer's source (figure, teacher description, off figure, unsure) and the parts it cites,
   from that figure's ids only. Minimal reasoning effort, a 2,000-token cap. Result: source
   right 36 of 38 (heart) and 35 of 35 (brain); all 9 off-figure questions sent to the
   teacher; all 7 prompt injections passed, 6 sent to the teacher and 1 answered from the
   teacher's description (`eval/qa/RESULTS.md`). Release to first spoken word,
   live on a Mac: p50 5.0 s over 12 questions (`eval/qa/VOICE.md`). On the iPhone: not
   measured.

## Why are Meta's models important to your solution?

The design depends on four things these models do.

- Muse Spark reads a figure and returns structured output under a strict schema. That lets
  one model both plan a figure for touch (areas, lines, groups, points) and answer a student
  in a shape code can check: the cited parts must exist, and an off-figure answer becomes a
  fixed sentence that sends the student to the teacher.
- Muse Spark places points on a figure it has never seen. That is what made SAM usable here.
- SAM 3.1 segments any part zero-shot from a few points, with no training on textbook art.
  That is what lets a teacher upload any figure, not only figures we prepared.
- Muse Voice Transcribe takes keyword hints, so the figure's own part names bias what it
  hears.

What changed when one did not work: the plan was one SAM text prompt per part. On the heart,
"left ventricle", "aorta" and "right atrium" found zero instances in both phrasings, while
"heart" found the whole heart (`spikes/sam.md`). The fix used the models together: Spark
places points on each part, and SAM segments from the points. 44 point prompts gave 44
single-instance masks.

We do not use an image-generation model. A student must learn from the textbook's own
picture, never one a model redrew.

## Partner technologies feedback

Not used.
