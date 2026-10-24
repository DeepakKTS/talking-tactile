# What to put in the application

Form: cerebralvalley.ai/e/meta-ai-developer-hackathon/apply
Closes Oct 25, 11:59 PM ET, or earlier if 20,000 people are accepted. Submit on Saturday.

Only two answers decide selection, weighted equally: the project idea and the AI project you built. Spend your time there.

## Quick fields

| Field | Fill in |
|---|---|
| Track | Indie developer |
| LinkedIn | linkedin.com/in/deepak-kumaran-ts |
| GitHub (optional, add it) | github.com/DeepakKTS |
| Where you live | Your current city, state, country |
| Where you study or work | Northeastern University, M.S. Information Systems (graduating December 2026). AI engineering co-op at Twin AI |
| X / Twitter | Optional. Skip if not active |
| Questions 13 to 16 | Feedback only, not scored. Answer honestly |
| Marketing consent | Your choice |

## Theme to name: Push the Frontier

Build for Your World asks for a problem you know firsthand. You do not have firsthand experience with blindness or tactile graphics, and the application should not imply it. Push the Frontier fits honestly: the project gives an ordinary camera a new capability, knowing what a finger is touching on a physical object, with no markers.

## Answer 1: What do you want to build? (full version, about 210 words)

Talking Tactile: textbook figures that a blind student can touch, and that talk back.

Science textbooks can have images on half their pages. Making tactile versions by hand takes 1 to 5 hours per image, or 200 to 1,000 hours per book, according to a University of Washington study. Earlier talking tactile systems needed QR codes, color tags or special tablets on every sheet, which kept them rare.

I will build two loops on Meta's models.

Authoring: Muse Spark reads a figure and lists its parts as short phrases. SAM 3.1 segments each part zero-shot. My code applies the BANA tactile spacing and texture rules and exports a print-ready sheet plus a map of every region.

Exploring: a phone camera watches the sheet. A hand tracker finds the fingertip, a homography maps it onto the sheet, and the app speaks the name of the part under the finger. The student asks questions by voice through Muse Voice Transcribe, with the figure's labels as keyword hints, and Muse Spark answers only from that figure.

Theme: Push the Frontier. An ordinary camera learns what a finger is touching on a physical object, with no markers. Today a phone, later the camera in Meta's glasses.

By Nov 4: one figure working end to end, measured touch accuracy and latency, and feedback from a blind student or teacher I am arranging now.

## Answer 1: short version (about 95 words)

Talking Tactile turns any STEM textbook figure into a raised graphic a blind student explores by touch and asks questions about by voice. Hand-made tactile figures take 1 to 5 hours each, and earlier talking systems needed QR codes or special tablets. Muse Spark lists a figure's parts, SAM 3.1 segments each one zero-shot, and my code applies BANA tactile rules to export a print-ready sheet. While exploring, a phone camera tracks the fingertip, the app speaks the part under it, and questions go through Muse Voice Transcribe to Muse Spark. Theme: Push the Frontier.

## Answer 2: An AI project you recently built (full version, about 200 words)

Weavory, an MCP memory server for multi-agent systems. Live on npm as @weavory/mcp, source at github.com/DeepakKTS/weavory.ai. Built for NandaHack 2026 at MIT Media Lab.

The problem: when several agents share memory, any agent can write a false fact and the others will trust it.

What I built: a strict TypeScript server exposing five MCP tools over stdio: believe, recall, subscribe, attest and forget. Every belief is signed with Ed25519 and appended to a BLAKE3 hash-chained audit log, so tampering is detectable. Agents attest to each other, and a trust score per signer and predicate, from -1 to 1, gates what recall returns. Bi-temporal replay with as_of shows what was believed at any past moment. Storage is JSONL by default with DuckDB as an option, and it ships as a multi-arch Docker image.

Results: 232 of 232 automated tests pass across unit, integration and performance suites. CI is green on Ubuntu and macOS. A fresh npx start reaches its first belief in under 30 seconds. In the demo, four agents triage a $42,000 insurance claim, and a forged approval from an unknown signer is quarantined by the trust floor.

At my Twin AI co-op I also build RAG pipelines and an LLM evaluation and prompt regression harness across Azure OpenAI and AWS Bedrock.

## Answer 2: short version (about 90 words)

Weavory (@weavory/mcp on npm, github.com/DeepakKTS/weavory.ai), built for NandaHack 2026 at MIT Media Lab. An MCP memory server where agents share beliefs they can verify. Five MCP tools over stdio. Every belief is Ed25519-signed into a BLAKE3 hash-chained audit log, a per-signer trust score gates recall, and as_of replay shows past state. 232 of 232 tests pass, CI is green on Ubuntu and macOS, and first belief arrives in under 30 seconds from a fresh npx start. In the demo, a forged approval on a $42,000 claim is quarantined.

## Before you press submit

- Every number above is from your own repo notes. Do not add any that are not.
- Do not claim accessibility experience. The plan relies on published guidelines and a tester, and says so.
- One application only. Duplicates are disqualified.
