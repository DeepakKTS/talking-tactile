"""Replays whose recorded request holds a PNG encoded on macOS, where the recordings were made.
Since Nov 3, fixtures/recorded/png_pixels.json maps a PNG's decoded pixels to the digest the
recordings hold (app/meta/record.py), so on Linux the heart's replays run too; mac_png skips
only when that file is missing. The notes below are from before it.
ReplayTransport matches a request on the sha256 of its PNG (app/meta/record.py). The figure's
pixels are the same on Linux, but Pillow's Linux build compresses them to other bytes (checked
Nov 2 in a Linux container on the heart: pixels f12b36d0 on both, PNG fae9b099 on macOS and
983aacf9 on Linux), so there the request finds no recording. The question replays
(test_ask_replay.py) too: on Linux the 63 asked with no part under the finger still pass,
through mock mode's fallback, which compares the prompt text only; the 10 asked with a finger
on a part do not (Nov 3). These run on the Mac, in the
pre-commit hook; CI on Linux skips them."""

import sys

import pytest

from app.meta.record import PNG_PIXELS

mac_png = pytest.mark.skipif(
    sys.platform != "darwin" and not PNG_PIXELS.exists(),
    reason="the recorded request holds a PNG encoded on macOS; Linux encodes other bytes, and "
    "fixtures/recorded/png_pixels.json (which maps them by pixels) is missing",
)
# The Commons brain's normalized image itself comes out with other pixels on Linux (checked
# Nov 3 in a python:3.11-slim container: its figure id is 589f2a96 there, 046e94d4 on the Mac),
# so no recording of it matches there, mapped or not. The heart's pixels are the same.
mac_pixels = pytest.mark.skipif(
    sys.platform != "darwin",
    reason="the brain's normalized pixels differ on Linux, so its figure id and recordings do",
)
