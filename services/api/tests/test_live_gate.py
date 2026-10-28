"""Live Meta calls happen only with LIVE=1. Without it, every test runs with the network
guard on: a lookup or connection to any host but loopback raises, and is recorded so a test
that swallows the error still fails."""

import asyncio
import contextlib
import socket
from pathlib import Path

import httpx
import pytest

from app.config import load_tactile_rules
from app.meta.client import LiveClientUnavailableError, make_client
from app.meta.live import live_enabled
from tests import network_guard

RULES = load_tactile_rules()
HOOK = Path(__file__).resolve().parents[3] / "scripts" / "hooks" / "pre-commit"


def test_live_is_off_unless_live_is_exactly_1(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LIVE", raising=False)
    assert not live_enabled()
    for value in ("0", "", "true", "yes", " 1"):
        monkeypatch.setenv("LIVE", value)
        assert not live_enabled(), value
    monkeypatch.setenv("LIVE", "1")
    assert live_enabled()


def test_the_live_client_needs_live_1(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LIVE", raising=False)
    with pytest.raises(LiveClientUnavailableError, match="LIVE=1"):
        make_client(mock=False, rules=RULES.meta)


def test_the_guard_refuses_a_connection_to_a_public_host() -> None:
    with pytest.raises(network_guard.OutboundRequestError):
        socket.create_connection(("93.184.216.34", 443), timeout=1)
    assert network_guard.take_attempts() == ["connect 93.184.216.34:443"]


def test_the_guard_refuses_a_lookup_of_the_meta_api() -> None:
    with pytest.raises(network_guard.OutboundRequestError):
        socket.getaddrinfo("api.meta.ai", 443)
    assert network_guard.take_attempts() == ["resolve api.meta.ai"]


def test_the_guard_stops_an_httpx_request_to_the_meta_api() -> None:
    async def go() -> None:
        async with httpx.AsyncClient() as http:
            with pytest.raises(httpx.HTTPError):
                await http.get("https://api.meta.ai/v1/models")

    asyncio.run(go())
    assert network_guard.take_attempts() == ["resolve api.meta.ai"]


def test_a_swallowed_attempt_still_fails_the_test() -> None:
    with contextlib.suppress(network_guard.OutboundRequestError):
        socket.getaddrinfo("example.com", 80)
    attempts = network_guard.take_attempts()
    with pytest.raises(AssertionError, match=r"example\.com"):
        network_guard.assert_none(attempts)


def test_loopback_still_works() -> None:
    with socket.create_server(("127.0.0.1", 0)) as server:
        port = server.getsockname()[1]
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            pass
        with socket.create_connection(("localhost", port), timeout=1):
            pass
    assert network_guard.take_attempts() == []


def test_the_pre_commit_hook_never_runs_live() -> None:
    text = HOOK.read_text()
    assert "unset LIVE" in text
    assert "LIVE=1" not in text
