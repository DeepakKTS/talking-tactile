# TODO.md

Tick boxes as you go. Each block has a time box and a fallback. If a task runs 50 percent over its box, take the fallback.

## Day 0: Oct 23 to 25 (no project code)

- [ ] Submit the hackathon application (answers in APPLICATION.md). Do it Saturday, not Sunday night
- [ ] Email two or three of: a school for the blind, a braille transcription service, a university disability services office. Ask for one 30 minute session on Nov 1 with a student or teacher who reads tactile graphics
- [ ] Buy: puffy fabric paint (2 colors), heavy cardstock, a phone stand or gooseneck clamp, masking tape, a ruler
- [ ] Read BANA Guidelines and Standards for Tactile Graphics, units 1 to 3
- [ ] List 20 openly licensed figures for the eval set (5 labeled diagrams, 5 bar charts, 5 line graphs, 5 maps)
- [ ] Note phone model and laptop GPU so the Day 2 spike has a baseline

## Day 1: Oct 26. Gate A

- [ ] Kickoff stream. Read and accept the Official Rules. Update PLAN.md section 17
- [ ] Get API key and credits. Set BUDGET_USD
- [ ] Repo skeleton: apps/web, services/api, Makefile, CI with lint and tests
- [ ] Spike Muse Spark: one figure in, structured parts list out (skill: meta-api-spike)
- [ ] Spike SAM 3.1: 5 phrases on the heart figure, record mask format and latency
- [ ] Spike Muse Voice: stream 10 seconds of audio, get partial and final transcripts, try keyword hints
- [ ] Meta client wrapper with retry, cache, cost meter, mock mode
- [ ] Gate A: all three models answer and p50 and p95 are written in spikes/
- Fallback: if SAM is weak on line art, test the local SAM 3.1 checkpoint with point prompts today

## Day 2: Oct 27. Gate B

- [ ] Web: camera module, newest frame only
- [ ] Worker with MediaPipe Hand Landmarker, VIDEO mode, 2 hands
- [ ] Homography from 4 corners clicked by hand (auto registration comes Day 5)
- [ ] Print the 9 point test sheet. Run 45 touches. Record error
- [ ] Measure fps on the phone browser and on the laptop. Decide the device
- [ ] Gate B: mean error 4 mm or less
- Fallback: require the pointing pose, raise dwell to 800 ms, keep regions above 12 mm

## Day 3: Oct 28

- [ ] S0 ingest with deskew and blur check
- [ ] S1 understand with structured output and the verdict field
- [ ] S2 ground, four SAM calls at a time
- [ ] S3 reconcile: dedupe, containment, numbered overlay mapping
- [ ] Unit tests for overlap rules

## Day 4: Oct 29

- [ ] S4 layout: polygons, gap enforcement, textures, point symbols
- [ ] liblouis wrapper, braille placement, key fallback
- [ ] S5 render: SVG, print PDF with calibration bar, regions.json, validation report
- [ ] tactile-rules-check passes on the heart figure
- [ ] Print two copies. Trace with puffy paint. Leave to dry overnight

## Day 5: Oct 30. Gate C

- [ ] /api/register with OpenCV first and SAM fallback, four rotation check
- [ ] Region engine and state machine with vitest coverage
- [ ] Earcons, dwell labels, exit tick, "more"
- [ ] Offline mode: labels work with the network off
- [ ] Gate C: the heart figure works end to end on the real sheet

## Day 6: Oct 31

- [ ] AudioWorklet capture, /api/voice proxy, keyword hints from labels
- [ ] Local intent parser
- [ ] /api/ask with grounded prompt, streaming, first sentence spoken early
- [ ] Barge-in with Space
- [ ] Guidance mode

## Day 7: Nov 1

- [ ] Review screen: edit, merge, delete, add by name, publish
- [ ] accessibility-pass skill
- [ ] Tester session. Record tasks, times, quotes, with consent

## Day 8: Nov 2

- [ ] Fix the top three issues from the session
- [ ] Author 3 more figure types (skill: add-figure-type)
- [ ] run-eval on all suites

## Day 9: Nov 3. Gate D

- [ ] Feature freeze at noon
- [ ] demo-readiness skill
- [ ] Record the demo video. Two takes minimum
- [ ] README with measured numbers, setup, Meta models used and why

## Day 10: Nov 4

- [ ] Fresh clone test
- [ ] Submit by 3 PM ET. Deadline is 9 PM ET

## Decisions needed

(write conflicts with RULES.md here)

## Budget misses

(write any performance budget miss here with the measured number)
