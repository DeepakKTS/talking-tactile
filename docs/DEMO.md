# Filming the demo

A runbook for recording the demo video on the Mac and the demo iPhone. Target: under 3
minutes, planned at 2:50. The exact limit: **check the submission form**.

Rule from the demo-readiness checklist: never record a step that only works sometimes. If a
step fails twice, fix it or cut it.

## Start

Every command starts at the repo root (the folder you cloned).

```
make preflight     # OK or FAIL per check; fix every FAIL first (PREFLIGHT=--live adds a live smoke)
make demo-live     # or make demo-mock
```

`make demo-live` (or `make demo-mock`) starts the three servers under `caffeinate -i`: the API
on 127.0.0.1:8000 (live, or mock with no Meta calls), the web app for the phone over HTTPS on
:5173, and the Gate B touch-test page on :8443. It refuses to start while one of those ports is
in use, and prints the iPhone URLs, the `.local` name first. Ctrl-C stops all three. Keep the
display awake in another terminal with `caffeinate -dimsu`.

`make preflight` checks the key file (never printing it), the phone certificate against this
Mac's LAN address and `.local` name, what holds ports 8000, 5173 and 8443, the heart and the
Commons brain version 4 through the API and through the phone's web server, CI on HEAD, that the
tree is clean and pushed, and the credits left in the ledger. It exits non-zero on any FAIL.

The sections below start the same servers one terminal at a time.

### If iPhone Safari breaks on the security headers

Signs: the device check's hand tracker row fails or never finishes, Start does nothing, or a
page stays blank where it worked before Nov 3. Stop the servers (Ctrl-C), then run:

```
TT_CSP=off make demo-live      # or TT_CSP=off make demo-mock
```

Every page is then served without the Content-Security-Policy, as before commit c41ecdf
(nosniff and no-referrer stay). Reload the page on the phone. Terminal by terminal, put
`TT_CSP=off` before `npm run dev:phone` and before `python3 spikes/tracking/serve.py`. Do not
`git revert c41ecdf`: it also removes `spikes/tracking/serve.py`, which `make demo-live` starts.

Checked on Nov 3 in WebKit 26.6 (Playwright) through dev:phone and :8443 with the real headers:
no policy violation on the device check, the heart's version 4 in Explore or the Gate B page;
MediaPipe's wasm and worker ran on the GPU in all three. iPhone Safari itself is checked in the
morning's device check.

### Mock mode (no network, no Meta calls, costs nothing)

Author's upload and pipeline replay the live recordings in `fixtures/recorded/replays.json`
(the heart and the Commons brain). Explore labels, earcons and guidance need no network.

Terminal 1, the API:
```
cd services/api
MOCK_META=1 uv run uvicorn app.main:app --port 8000
```

Terminal 2, the web app for the phone (HTTPS on the LAN; the API is proxied):
```
cd apps/web
npm run cert:phone      # only when the Mac's LAN address changed
npm run dev:phone
```

On the Mac alone, `MOCK_META=1 make dev` runs both on http://localhost:5173.

Questions in mock mode: a typed question is answered from the live eval's recordings
(answer prompt v2, Nov 3, `fixtures/recorded/qa7_*`) when the eval asked it with no part
under the finger; then it is answered wherever the finger is. Any other question, and any
held (spoken) question but the recorded clips, says "Questions are not working right now.
Labels still work."

### Live mode (Spark, SAM, Voice; costs credits)

Terminal 1, the API, under `caffeinate -i` so the Mac cannot sleep mid-call:
```
cd services/api
caffeinate -i env LIVE=1 uv run uvicorn app.main:app --port 8000
```

Terminal 2: as in mock mode (`npm run dev:phone`).

Terminal 3, the Mac's display awake for the whole take:
```
caffeinate -dimsu
```

### URLs on the iPhone

Use the `.local` name first; the IP is the address `npm run cert:phone` printed.

| Page | URL |
|---|---|
| Device check | `https://Zedlers-MacBook-Pro.local:5173/explore?check=1` |
| Heart, version 4 | `https://Zedlers-MacBook-Pro.local:5173/explore?figure=913ba16a635188097dbb235741e05e376d23cca17bdb1789aec79a1497a67ada&version=4` |
| Commons brain, version 4 | `https://Zedlers-MacBook-Pro.local:5173/explore?figure=046e94d4f0b53298900ab96754caeb348dbc624b35841512d4e5b1198a36a699&version=4` |
| Author | `https://Zedlers-MacBook-Pro.local:5173/author` (film on the Mac at `http://localhost:5173/author`) |

Published versions live in `data/published/` on this Mac (git-ignored). A fresh clone has
none: upload and publish first (README quickstart).

## Pre-flight

Do these in order, the day of filming.

1. **Code**: on the commit you will film, `make preflight` says ALL OK, `make check` passes,
   and so do `uv run apps/web/e2e/explore_e2e.py` and `uv run apps/web/e2e/plan_e2e.py`.
2. **Fresh clone**: `git clone`, `make install`, `MOCK_META=1 make dev` starts with no step
   beyond `services/api/.env`.
3. **Mock run, network off**: the whole shot list. Everything but questions works.
4. **Live run, twice in a row, no restart**: the whole shot list, with questions.
5. **Power**: Mac on its charger; phone charged or on a cable that does not pull the mount.
6. **Mac awake**: `caffeinate -dimsu` running (terminal 3); the API under `caffeinate -i`.
7. **Phone awake**: the device check's Screen Wake Lock row says "Held and released". If it
   fails, Settings > Display & Brightness > Auto-Lock > Never.
8. **Phone sound**: silent switch off (Safari mutes Web Audio earcons in silent mode; needs
   device to confirm), volume near full, Bluetooth off so sound stays on the phone.
9. **Device check**: `/explore?check=1` on the phone, every row ok: secure page, rear
   camera, hand tracker at 10 frames a second or more, a local voice, wake lock,
   microphone.
10. **Sheet**: the heart's print PDF (version 4) printed at 100 percent ("Actual size"), the
    100 mm bar measured with a ruler, the sheet traced or swelled, taped flat at two corners.
11. **Mount**: the phone fixed above the sheet, all four corner marks in view; it does not
    move during a take. After Start, the corners are set and the outline is checked against
    the printed marks.
12. **Light**: overhead light on, no window glare on the sheet; the device check's camera
    row is ok and Explore never says "The camera cannot see the sheet."
13. **Credits**: note the credits left (`make preflight`, last line) before and after;
    `python3 scripts/tracker.py spend` records the spend in the tracker.
14. **Numbers**: every number said or shown comes from a committed result file (below) and
    matches it on the day.
15. **Audio levels**: the app voice is audible over any narration track.

## Figures

| Figure | Version | Source and license | Credit line to show |
|---|---|---|---|
| Heart (`fixtures/heart.png`) | 4: every part checked, descriptions on the left ventricle and the right atrium | Heart diagram-en.svg by ZooFari, Wikimedia Commons, CC BY-SA 3.0 | "Heart diagram-en.svg by ZooFari, CC BY-SA 3.0, via Wikimedia Commons. Resized and placed on a white background." |
| Commons brain (`fixtures/eval/brain_lobes.png`) | 4: every part checked, two descriptions | Blausen 0111 BrainLobes.png by BruceBlaus, Wikimedia Commons, CC BY 3.0 | "Blausen 0111 BrainLobes.png by BruceBlaus (Blausen.com staff, Medical gallery of Blausen Medical 2014), CC BY 3.0, via Wikimedia Commons." |

Share-alike: the tactile sheet, its PDF and the heart as it appears in the video are
adaptations of a CC BY-SA 3.0 figure, so they carry that license and the credit line
(ATTRIBUTION.md). Show both credit lines on screen whenever the figure is shown, or in an end
card covering every shot it appears in.

## Shots

Planned at 2:50, leaving 10 s under 3 minutes. The narration, captions and the criterion each
shot serves are in `docs/submission/VIDEO_SCRIPT.md`. If the form's limit is shorter, cut shot 9
first, then shot 6. Words to say are a suggestion; keep them plain, with no claim the result
files do not back. Pipeline and question waits are real: cut them in the edit, and say on
screen when a wait was shortened.

| # | Time | Secs | Show | Say | Needs |
|---|---|---|---|---|---|
| 1 | 0:00 to 0:12 | 12 | The printed textbook heart beside the raised sheet | Who it is for: a blind student, and the teacher who makes the sheet | Nothing |
| 2 | 0:12 to 0:40 | 28 | Author on the Mac: upload heart.png, the parts Spark lists, SAM's outlines, the "Needs you" list, the aortic arch merge in one press (the pipeline wait cut) | Spark reads the figure and plans the parts; SAM outlines each one; code decides geometry; the teacher confirms | Network in live mode; mock replays the same recorded answers |
| 3 | 0:40 to 0:55 | 15 | Check the parts, describe the left ventricle, Publish; the print PDF with the 100 mm bar | Nothing is touchable until the teacher checks it; publish refuses a sheet with nothing checked or a broken tactile rule | Mock or live |
| 4 | 0:55 to 1:07 | 12 | The phone in its mount over the sheet; Start; a helper sets the corners | The phone camera watches the sheet; the outline is checked against the printed marks | No network (the app is served from the Mac on the LAN) |
| 5 | 1:07 to 1:30 | 23 | A finger enters parts: an earcon on entry, the name after a rest; on the left ventricle, hold and say "tell me more" (M on a keyboard) | Labels and earcons come from the sheet's file, with no network | No network for earcons and names; a spoken command needs the network |
| 6 | 1:30 to 1:42 | 12 | "Where is the aorta?": guidance beeps toward it | Directions come from code, never from the language model | The guidance needs no network; the spoken words do (Voice Transcribe) |
| 7 | 1:42 to 2:12 | 30 | Hold to talk: "What does the left ventricle do?"; the answer from the teacher's description. Then "What does the right ventricle do?": the deflection to the teacher. Each answer takes about 5 s live (p50 5.0 s), now and then near 15 s: keep one wait whole, cut the other | Muse Voice Transcribe with the figure's part names as hints; Spark answers from the figure's data under a strict schema | Network, live |
| 8 | 2:12 to 2:24 | 12 | Wi-Fi off on the phone: touch still speaks; a question says "Questions need the network. Labels still work." | It still works offline, and says what does not | No network |
| 9 | 2:24 to 2:36 | 12 | The Commons brain sheet, a few touches | The same pipeline on a second figure | No network for touch |
| 10 | 2:36 to 2:50 | 14 | End card: the three Meta models and what each does, both credit lines | | Nothing |

## When the network is not there

| Step | Fallback |
|---|---|
| Upload and pipeline (shot 2) | Mock mode: the same live recordings, replayed, for the heart and the Commons brain. Say on screen that this take replays recorded model answers |
| Publish and print (shot 3) | Needs no Meta call; works in either mode |
| MediaPipe hand model (shots 4 to 9) | Served by the app from the Mac (`/models/hand_landmarker.task`), so it needs the LAN, not the internet |
| Opening a sheet (shots 4, 9) | Explore keeps the last good copy of each version on the phone; with the Mac unreachable it says "Opened the saved copy; the network is down." |
| Questions (shot 7) | If dev.meta.ai is unreachable (university Wi-Fi blocks it), use the phone's hotspot for the Mac. With no network at all, run mock mode and type both questions instead of holding: they were recorded with no part under the finger, so mock mode answers them wherever the finger is. Say on screen that the answers are replayed recordings |
| Device check rows | Needs no Meta call |

## Numbers for the script

Only these, from committed files, re-read on the day:

- Question answers: `eval/qa/RESULTS.md` (live, answer prompt v2 at minimal effort, Nov 3:
  heart source right 36 of 38, Commons brain 35 of 35).
- Release to first spoken word: `eval/qa/VOICE.md` (p50 5.0 s, two of 12 near 14 s, headless
  Chrome on the Mac; the iPhone figure is item "device latency film").
- Part plan on the eval figures: `eval/plan/RESULTS.md`.
- Spend: `python3 scripts/tracker.py spend`.
