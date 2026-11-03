"""Replays whose recorded request holds a PNG encoded on macOS, where the recordings were made.
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

mac_png = pytest.mark.skipif(
    sys.platform != "darwin",
    reason="the recorded request holds a PNG encoded on macOS; Linux encodes other bytes",
)
