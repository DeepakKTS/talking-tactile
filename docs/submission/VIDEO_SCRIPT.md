# Video script

Under 3 minutes, planned at 2:50, following the shot list in `docs/DEMO.md` (same numbers,
same times). If the form's limit is shorter, cut shot 9 first, then shot 6.

Criterion is the judging criterion the shot mainly serves: creativity, technical ambition, or
whether it works. **Phone** marks shots that need footage from the iPhone in its mount over the
printed sheet; the rest are screen recordings on the Mac or a still.

Every number said or shown names its file. TBD: not measured yet; say nothing in its place
until it is.

| # | Time | On screen | Narration | Caption | Criterion | Phone |
|---|---|---|---|---|---|---|
| 1 | 0:00 to 0:12 | The printed textbook heart beside the raised sheet; a hand on the raised one | "A blind student can feel the shape of a heart on a raised sheet. Talking Tactile tells them what they are touching." | Heart diagram credit line (see below) | Creativity | Yes |
| 2 | 0:12 to 0:40 | Author on the Mac: upload heart.png; the parts Spark lists; SAM's outlines; the "Needs you" list; the aortic arch merged in one press | "The teacher uploads the textbook figure. Muse Spark reads it and plans each part for touch. SAM 3.1 outlines every part. Code, not the model, decides the geometry: gaps, textures, braille. What the models were unsure of goes to the teacher." | "Pipeline wait shortened." In mock mode also: "Replayed model answers." | Technical ambition | No |
| 3 | 0:40 to 0:55 | Check the parts, describe the left ventricle, Publish; the print PDF with its 100 mm bar | "Nothing is touchable until the teacher checks it. Publishing refuses a sheet that breaks a tactile design rule. The sheet prints at exact scale." | "100 mm bar: measure it after printing." | Whether it works | No |
| 4 | 0:55 to 1:07 | The phone in its mount over the sheet; Start; a helper sets the corners; the outline matches the printed marks | "On the student's side, a phone camera watches the sheet. Its corners tie the camera to the page." | none | Technical ambition | Yes |
| 5 | 1:07 to 1:30 | A finger enters parts: a tone on entry, the name after a rest; on the left ventricle, hold and say "tell me more" | "Each part has its own tone. Rest a finger and the phone says the part's name, with no network at all. Say "tell me more" to hear what the teacher wrote about it." | Part names as spoken | Whether it works | Yes |
| 6 | 1:30 to 1:42 | "Where is the aorta?": guidance beeps speed up toward it | "Directions come from the sheet's geometry, never from a language model." | none | Technical ambition | Yes |
| 7 | 1:42 to 2:12 | Hold to talk: "What does the left ventricle do?"; the answer from the teacher's description. Then "What does the right ventricle do?": sent back to the teacher | "Hold to ask. Muse Voice Transcribe hears the question, with the figure's part names as hints. Muse Spark answers only from this figure. If the figure does not say, it tells the student to ask their teacher. In our live tests, 36 of 38 heart questions were answered from the right source." | "36 of 38: eval/qa/RESULTS.md". On the cut wait: "Wait shortened." | Whether it works | Yes |
| 8 | 2:12 to 2:24 | Wi-Fi off on the phone: touch still speaks; a question says "Questions need the network. Labels still work." | "With the network gone, touch still works, and the phone says what does not." | "Wi-Fi off" | Whether it works | Yes |
| 9 | 2:24 to 2:36 | The Commons brain sheet, a few touches | "The same steps work on a second figure." | Brain figure credit line (see below) | Creativity | Yes |
| 10 | 2:36 to 2:50 | End card: the three Meta models and their jobs; both credit lines | "Talking Tactile. Built on Muse Spark, SAM 3.1 and Muse Voice Transcribe." | Model list; both credit lines | Technical ambition | No |

Narration: about 250 words, so it fits with room for the app's own voice.

Spoken commands ("tell me more", "where is the aorta") are recognized on the phone, but the
words come from Muse Voice Transcribe, so they need the network. The tones and names in shots
5, 8 and 9 need none.

## Numbers that may appear

| Number | Where it is shown or said | Source |
|---|---|---|
| 36 of 38 heart questions answered from the right source | Shot 7 | `eval/qa/RESULTS.md` |
| Release of the talk button to the first spoken word: p50 5.0 s, Chrome on the Mac | Not said; use only if asked | `eval/qa/VOICE.md` |
| Release to first word on the iPhone | Not said | TBD: the device latency film |
| Fingertip error on the 9-point sheet | Not said | TBD: Gate B, `eval/gate-b/README.md` |

## Captions for every take

- Heart: "Heart diagram-en.svg by ZooFari, CC BY-SA 3.0, via Wikimedia Commons. Resized and
  placed on a white background." Shown in every shot with the heart, or on the end card
  covering them all.
- Brain: "Blausen 0111 BrainLobes.png by BruceBlaus (Blausen.com staff, Medical gallery of
  Blausen Medical 2014), CC BY 3.0, via Wikimedia Commons."
- Any shortened wait says so on screen. Any mock-mode take says "Replayed model answers."
