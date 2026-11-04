# Voice questions: transcribe and end-to-end latency (live, Oct 30)

## Transcribe path

Three synthetic clips (fixtures/audio, macOS `say`, 16 kHz mono), each sent to the file transcribe endpoint, push to talk, without and with the heart's 16 part, line and group names as `keywords`. Recorded as fixtures/recorded/qa_ask_transcribe_*.

| Clip | Keywords | Transcript | Words right | ms |
|---|---|---|---|---|
| question_left_ventricle | no | What does the left ventricle do? | 6/6 | 1486 |
| question_left_ventricle | yes | What does the the left ventricle do? | 6/6 | 1094 |
| question_superior_vena_cava | no | Where is the superior vena cava? | 6/6 | 1275 |
| question_superior_vena_cava | yes | where is the superior vena cava? | 6/6 | 1176 |
| question_left_pulmonary_veins | no | what is next to the left pulmonary veins?. | 8/8 | 1145 |
| question_left_pulmonary_veins | yes | What is next to the left pulmonary veins? | 8/8 | 842 |

Every word right without and with keywords; with keywords one transcript repeats "the". Clean synthetic speech is at the ceiling, so these clips cannot show what the hints add; recordings of a real voice through the app come next.

## Release to first spoken word

Headless Chrome on this Mac, against the API with live calls, on the published heart (version 3). Chrome's fake microphone plays each clip in a loop; the mouse is held for the clip's length plus 0.6 s, four times a clip, 12 questions. The first spoken word is the app voice's start event. Times from Explore's metrics (window.__tt.metrics): transcribe and Spark as the server timed them; network is the round trip less those; the device time is the WAV encoding plus the gap from the answer being handed to speech to its start event. Because the fake microphone loops, a hold can begin mid-sentence (the last one heard "the left ventricle do? What does the left").

| Part | Runs | p50 ms | p95 ms |
|---|---|---|---|
| Release to first spoken word | 12 | 4138 | 5104 |
| Transcribe (server) | 12 | 941 | 1355 |
| Spark (server) | 12 | 3258 | 4078 |
| Network and server code | 12 | 13 | 15 |
| WAV encoding (device) | 12 | 1 | 4 |
| On the device: encoding, then speech starting | 12 | 6 | 10 |

Spark is most of it. The phone, VoiceOver and a real network are for the iPhone test.

## Latency experiment: the answer prompt without the figure image (Oct 30)

The full eval (61 questions, published version 4) run live twice: (a) ask_answer.v1 with the figure image, as /api/ask did then (written to eval/qa/RESULTS.md at the time; that file now holds the later ask_answer.v2 run); (b) ask_answer_text.v1, the same rules without the image, and no image sent (eval/qa/RESULTS_no_image.md, recorded as qa3_ask_*, not replayed).

| Variant, figure | Source correct | Citations correct | Outside words | Spark p50 ms | Spark p95 ms |
|---|---|---|---|---|---|
| (a) with image, heart | 30 of 32 | 28 | 0 | 3314 | 5288 |
| (a) with image, brain_lobes | 29 of 29 | 28 | 0 | 2923 | 4688 |
| (b) no image, heart | 31 of 32 | 30 | 0 | 2409 | 4286 |
| (b) no image, brain_lobes | 29 of 29 | 28 | 0 | 2374 | 3824 |

(b) is about 0.9 s faster at p50 and 1 s at p95, and scores better on the heart, not the same: its misses differ (h01 "What is this?" on the right atrium answered from its teacher description, source teacher_description where figure was expected; h20 and h60 right, h30 deflected where (a) answered it from the left ventricle's description). The rule was to keep (b) only if its scores equal (a)'s, so (a) stays; the comparison is the user's to decide.

### Release to first spoken word, the kept variant (a)

As above (headless Chrome, fake microphone, live API), on published version 4, with the 250 ms post-roll: 12 holds.

| Part | Runs | p50 ms | p95 ms |
|---|---|---|---|
| Release to first spoken word (with the 250 ms post-roll) | 12 | 4510 | 5935 |
| Transcribe (server) | 12 | 974 | 1244 |
| Spark (server) | 12 | 3052 | 4441 |
| Network and server code | 12 | 15 | 23 |
| WAV encoding (device) | 12 | 3 | 5 |
| On the device: encoding, then speech starting | 12 | 8 | 10 |

### Release to first spoken word, answer prompt v2 (Nov 3)

As above (headless Chrome on the Mac, Chrome's fake microphone playing the three clips, four
holds each, live API, published version 4, 250 ms post-roll), with answer prompt v2 and its
strict per-figure schema: 12 holds.

| Part | Runs | p50 ms | p95 ms |
|---|---|---|---|
| Release to first spoken word (with the 250 ms post-roll) | 12 | 8496 | 9641 |
| Transcribe (server) | 12 | 969 | 1098 |
| Spark (server) | 12 | 7189 | 8491 |
| Network and server code | 12 | 13 | 15 |
| WAV encoding (device) | 12 | 2 | 3 |
| On the device: encoding, then speech starting | 12 | 6 | 8 |

Spark is about 4 s slower at p50 than on Oct 30 (3052 ms with prompt v1). The question eval
of the same evening (the qa6 run, 73 questions, since replaced in eval/qa/scores.json by the
minimal-effort rerun) has Spark at p50 7657 ms on the heart
and 6692 ms on the brain, slowest 18693 ms. One run cannot tell how much is the v2 prompt and
schema and how much is the service that evening. The iPhone figure is still to be measured.


## Answer latency variants (Nov 3, night)

Live, in-process through the same Asker as POST /api/ask (no browser): the three clips, the
heart's published version 4, 12 held questions a variant, interleaved A B C D so they share
the service's load. Server time is transcribe plus Spark; the browser adds about 0.3 s (the
250 ms post-roll, network, speech start; tables above). Not recorded.

| Variant | Errors | Server p50 ms | Server p95 ms | Spark p50 ms | Spark p95 ms |
|---|---|---|---|---|---|
| A: prompt v2, strict schema, full image, effort "low" (shipped until now) | 0 | 9064 | 10338 | 7698 | 9628 |
| B: as A without strict (measurement only, never shipped) | 0 | 10248 | 13869 | 9453 | 12927 |
| C: as A, image downscaled to 768 px on its longest side | 0 | 8453 | 10863 | 7455 | 9167 |
| D: as A, effort "minimal", max_completion_tokens 400 | 3 of 12 | 4762 | 7010 | 3953 | 6041 |

D's three errors are answers with no JSON: the cap counts reasoning tokens ("counting both
visible output and reasoning tokens", dev.meta.ai chat completions schemas), and minimal
reasoning still passed 400. "minimal" is the lowest effort Muse Spark takes ("Muse Spark
always reasons, so reasoning_effort: "none" returns HTTP 400", dev.meta.ai/docs/protocols/
chat-completions). A fifth variant, run interleaved with A once more:

| Variant | Errors | Server p50 ms | Server p95 ms | Spark p50 ms | Spark p95 ms |
|---|---|---|---|---|---|
| A (again, a lighter-loaded run) | 0 | 5924 | 7602 | 4979 | 6809 |
| E: as A, effort "minimal", max_completion_tokens 2000 | 0 | 4557 | 5518 | 3722 | 4710 |

E shipped: the full eval at E (eval/qa/scores.json, recorded as qa7) scores no worse than at A:
heart source 36 of 38 (citations 35, was 32; outside-word flags 3, was 5), Commons brain 35 of
35 (citations 34, flags 5), the picture questions the same (heart 5 of 6, brain 6 of 6).

### Release to first spoken word, effort "minimal" (shipped)

Headless Chrome, fake microphone, the three clips four times each, live API, version 4.

| Part | Runs | p50 ms | p95 ms |
|---|---|---|---|
| Release to first spoken word (with the 250 ms post-roll) | 12 | 5010 | 13780 |
| Transcribe (server) | 12 | 964 | 1190 |
| Spark (server) | 12 | 3700 | 12300 |

Ten of the 12 took 4.3 to 6.0 s; two took 13.8 and 14.7 s (Spark 12.3 and 13.5 s). With 12
runs the p95 is the slower of those two.
