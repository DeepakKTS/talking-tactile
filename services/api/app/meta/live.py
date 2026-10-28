"""Live Meta calls. They happen only when the environment has LIVE=1, exactly.

LIVE is read from the process environment only, never from services/api/.env, so the file
that holds the key cannot turn spending on by itself. The pre-commit hook unsets it."""

import os

LIVE_ENV = "LIVE"


def live_enabled() -> bool:
    return os.environ.get(LIVE_ENV) == "1"
