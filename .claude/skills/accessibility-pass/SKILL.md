---
name: accessibility-pass
description: Check the Explore mode for keyboard-only use, screen reader behavior and audio onboarding. Use after any change to Explore UI, audio or settings.
---

# Accessibility pass

1. Unplug the mouse. Complete onboarding, calibration, exploring and a question using only the keys listed in RULES.md section 6.
2. Turn on the system screen reader. Set "who speaks" to screen reader. Confirm every spoken line appears once, not twice.
3. Switch to app voice. Confirm the screen reader stays quiet for live updates.
4. Press Escape during speech. It must stop within 200 ms.
5. Cover the camera. The app must say it cannot see the sheet within 2 seconds.
6. Write results in `eval/a11y.md` with date and browser.
