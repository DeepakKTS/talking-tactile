# Talking Tactile: submission write-up

Every number below names the committed file it comes from. What is not measured says so.

## Short (about 150 words)

Talking Tactile turns a printed STEM figure into a raised sheet that a blind student explores
by touch, with a phone that says the part under their finger and answers questions about that
figure only. A teacher uploads a textbook figure. Muse Spark reads it and plans the parts for
touch, SAM 3.1 outlines each part, and code, not a model, decides the geometry: gaps,
textures, braille, neighbors and directions. The teacher checks every part and prints the sheet
at exact scale. On the student's side, a phone over the sheet tracks the fingertip in a Web
Worker, plays a texture tone on entering a part and says its name, with no network needed.
A held question goes through Muse Voice Transcribe, with the part names as hints; Muse Spark
answers from the figure's data or sends the student to the teacher. Live, 36 of 38 heart
questions were answered from the right source (`eval/qa/RESULTS.md`).

## Long (about 500 words)

### The problem

A raised-line figure shows a blind student the shape of a heart or a map, but not what each
shape is. Braille labels need room a figure rarely has, and a transcriber makes each sheet by
hand. Talking Tactile makes the sheet from the textbook figure and lets it talk.

### What it does

Author mode is for the teacher. They upload a figure (PNG, JPEG or a PDF page). Muse Spark
lists the parts as short phrases and plans each one for touch: an area, a line or a group,
with points on the figure. SAM 3.1 outlines each part from those points. Code then lays the
sheet out in millimeters: a 3.2 mm gap between parts, at most five textures, parts too small
to enter turned into point symbols, braille through liblouis, and a rules report. Nothing is
touchable until the teacher checks it, and publishing refuses a sheet that breaks a tactile
rule. The print PDF carries a 100 mm bar to check the scale.

Explore mode is for the student and needs no screen. A phone in a mount watches the sheet.
MediaPipe finds the fingertip in a Web Worker; the sheet's corners map the camera to the page.
Entering a part plays its texture tone, and resting says its name. Labels, tones and "where
is" guidance come from the sheet's file alone, so they work offline. Directions and neighbors
are computed in code; the language model never guesses them. Only picture questions (shape,
biggest, top) are answered from the figure's image.

Holding to talk records a question. Muse Voice Transcribe turns it into words, with the
figure's part names as keyword hints. Commands such as "where is the aorta" are handled on the
phone. Questions go to Muse Spark with the figure's data under a strict schema: it answers
from the figure or the teacher's descriptions, or says the figure does not show that.

### How it uses Meta's models

| Model | Job |
|---|---|
| `muse-spark-1.3` | Reads the figure, plans the parts for touch, answers questions from the figure's data |
| `sam-3.1` | Outlines every planned part, zero-shot, from points and phrases |
| `muse-voice-transcribe-1.0` | Turns a held question into words, with the part names as hints |

No generative image model redraws a figure: a student must learn from the textbook's own
picture.

### What we measured

- Part plans, from live recordings (`eval/plan/RESULTS.md`): touchable areas 14 of 15 on the
  heart, 9 of 9 on a map of Japan's regions, 5 of 6 on a brain figure, and 7 of 13 on a flower,
  where the rest go to the teacher's "Needs you" list.
- Questions, live (`eval/qa/RESULTS.md`): source right for 36 of 38 on the heart and 35 of 35
  on the brain. All 9 questions the figures do not answer were sent back to the teacher. All 7
  prompt injections passed: 6 were sent back, 1 was answered from the teacher's description
  (`eval/qa/README.md` says why that passes).
- Release of the talk button to the first spoken word (`eval/qa/VOICE.md`): p50 5.0 s over 12
  runs in Chrome on the Mac; two of the 12 took about 14 s. On the iPhone:
  <!-- tt:voice-device -->not measured: the latency film was cut<!-- /tt:voice-device -->.
- Fingertip accuracy on the 9-point test sheet (`eval/gate-b/README.md`, target a mean error of
  4 mm or less): <!-- tt:gate-b -->mean 7.93 mm, median 4.0 mm, p95 25.77 mm over 45 touches (`eval/gate-b/RESULTS.md`)<!-- /tt:gate-b -->.
  Gate B fails by that target. Most of the error came from target 9 (five touches, mean 27.41 mm), including the run's first touch at 77.96 mm. The next fix snaps each tapped corner to its printed L mark.
- Touch to tone on the iPhone:
  <!-- tt:earcon-device -->not measured: the latency film was cut<!-- /tt:earcon-device -->.
- Spend: $5.42 of the $150 credits (`eval/live/ledger.jsonl`, 1,037 logged calls, as of
  Nov 4).

### Limits

Mock mode replays recorded model answers, so it answers only the questions that were
recorded. Spoken questions need the network. Latency on the phone was not measured: the
latency film was cut, and the only measured figure is the Mac's, p50 5.0 s from release to the
first spoken word (`eval/qa/VOICE.md`). Figures with many small, touching parts (the
flower) still need the teacher for about half of them.

### Try it

`README.md` has the mock-mode quickstart: no key, no network calls.
