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
