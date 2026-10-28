"""Live Meta calls. They happen only when the environment has LIVE=1, exactly.

LIVE is read from the process environment only, never from services/api/.env, so the file
that holds the key cannot turn spending on by itself. The pre-commit hook unsets it.

Every live call goes through LiveCaller. It refuses the real network without LIVE=1, stops
the run at meta.live_call_cap calls, appends one line per call to eval/live/ledger.jsonl with
the usage object exactly as the response returned it, prices the call on the cost meter, and
keeps the key out of every error and ledger line. An injected httpx.MockTransport (tests, and
replay of recorded responses) never reaches the network, so it needs no LIVE=1."""

import datetime as dt
import json
import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from app.config import Meta
from app.meta.cost import CostMeter
from app.meta.record import Files, Recorder
from app.paths import ENV_FILE, LEDGER

LIVE_ENV = "LIVE"
KEY_NAME = "MODEL_API_KEY"
DEFAULT_BASE = "https://api.meta.ai/v1"
REDACTED = "<redacted>"
_ERROR_CHARS = 2000
_TIMEOUT = httpx.Timeout(120.0, connect=10.0)

# Maps a response's usage object to cost meter units, or None when it cannot be priced.
Units = Callable[[Any], Mapping[str, float] | None]


class LiveDisabledError(Exception):
    """A live call without LIVE=1."""


class LiveCallCapError(Exception):
    """The run has made its allowed number of live calls."""


class LiveConfigError(Exception):
    """services/api/.env is missing the key. The message never holds a value."""


class LiveCallError(Exception):
    """A non-200 answer. The body is redacted and cut to a readable length."""

    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"HTTP {status}: {body}")
        self.status = status
        self.body = body


def live_enabled() -> bool:
    return os.environ.get(LIVE_ENV) == "1"


def read_env(env_file: Path = ENV_FILE) -> dict[str, str]:
    env: dict[str, str] = {}
    if not env_file.is_file():
        return env
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        env[name.strip()] = value.strip().strip('"').strip("'")
    return env


def load_key(env_file: Path = ENV_FILE) -> str:
    env = read_env(env_file)
    if KEY_NAME not in env:
        raise LiveConfigError(f"No {KEY_NAME} line in {env_file}.")
    if not env[KEY_NAME]:
        raise LiveConfigError(f"{KEY_NAME} is empty in {env_file}.")
    return env[KEY_NAME]


def spark_units(usage: Any) -> dict[str, float] | None:
    """Chat completions usage, with the field names the docs give (spikes/muse-spark.md):
    prompt_tokens (cached ones included), prompt_tokens_details.cached_tokens and
    completion_tokens. Anything else is left unpriced rather than guessed."""
    if not isinstance(usage, dict):
        return None
    prompt, completion = usage.get("prompt_tokens"), usage.get("completion_tokens")
    if not isinstance(prompt, int) or not isinstance(completion, int):
        return None
    details = usage.get("prompt_tokens_details")
    cached = details.get("cached_tokens", 0) if isinstance(details, dict) else 0
    return {
        "input_tokens": prompt,
        "cached_tokens": cached if isinstance(cached, int) else 0,
        "output_tokens": completion,
    }


def completed_usage(events: list[Any]) -> Any:
    """The usage object on a Responses stream's response.completed event, as returned."""
    for ev in reversed(events):
        if isinstance(ev, dict) and ev.get("type") == "response.completed":
            response = ev.get("response")
            return response.get("usage") if isinstance(response, dict) else None
    return None


class Ledger:
    def __init__(self, path: Path = LEDGER) -> None:
        self.path = path

    def append(self, line: Mapping[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")

    def read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(x) for x in self.path.read_text(encoding="utf-8").splitlines() if x]


@dataclass(frozen=True)
class LiveResult:
    status: int
    latency_ms: float
    body: Any  # the JSON body, or the list of stream events
    usage: Any  # exactly as returned, or None
    ledger_line: dict[str, Any]


class LiveCaller:
    def __init__(
        self,
        *,
        key: str,
        base_url: str,
        ledger: Ledger,
        meter: CostMeter,
        cap: int,
        transport: httpx.MockTransport | None = None,
        recorder: Recorder | None = None,
    ) -> None:
        self._key = key
        self.base_url = base_url
        self.ledger = ledger
        self.meter = meter
        self.cap = cap
        self._transport = transport
        self.recorder = recorder
        self.calls = 0

    @classmethod
    def from_env(
        cls,
        rules: Meta,
        *,
        env_file: Path = ENV_FILE,
        ledger_path: Path = LEDGER,
        transport: httpx.MockTransport | None = None,
        recorder: Recorder | None = None,
    ) -> "LiveCaller":
        env = read_env(env_file)
        return cls(
            key=load_key(env_file),
            base_url=env.get("META_API_BASE") or DEFAULT_BASE,
            ledger=Ledger(ledger_path),
            meter=CostMeter(rules),
            cap=rules.live_call_cap,
            transport=transport,
            recorder=recorder,
        )

    def redact(self, text: str) -> str:
        return text.replace(self._key, REDACTED) if self._key else text

    def _admit(self, record_as: str | None) -> None:
        if record_as is not None:
            if self.recorder is None:
                raise ValueError("record_as needs a LiveCaller with a recorder")
            self.recorder.check_free(record_as)
        if self._transport is None and not live_enabled():
            raise LiveDisabledError("Live Meta calls need LIVE=1 in the environment.")
        if self.calls >= self.cap:
            raise LiveCallCapError(
                f"This run reached its cap of {self.cap} live calls and stopped."
            )
        self.calls += 1

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self._key}"},
            timeout=_TIMEOUT,
            transport=self._transport,
        )

    def _line(
        self, caller: str, model: str, describe: str, status: int | None, t0: float
    ) -> dict[str, Any]:
        return {
            "ts": dt.datetime.now(dt.UTC).isoformat(timespec="milliseconds"),
            "caller": caller,
            "model": model,
            "input": describe,
            "cache": "miss",
            "status": status,
            "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
        }

    def _fail(self, line: dict[str, Any], status: int, text: str) -> LiveCallError:
        body = self.redact(text)[:_ERROR_CHARS]
        self.ledger.append({**line, "usage": None, "cost_usd": None, "error": body})
        return LiveCallError(status, body)

    def _done(
        self, line: dict[str, Any], model: str, body: Any, usage: Any, units: Units | None
    ) -> LiveResult:
        priced = units(usage) if units is not None else None
        cost = self.meter.record(model, **priced) if priced is not None else None
        full = {**line, "usage": usage, "cost_usd": cost}
        self.ledger.append(full)
        return LiveResult(line["status"], line["latency_ms"], body, usage, full)

    def _record(
        self,
        name: str | None,
        model: str,
        request: httpx.Request,
        path: str,
        response: dict[str, Any],
    ) -> None:
        if name is not None and self.recorder is not None:
            request.read()
            self.recorder.save(
                name,
                model=model,
                request=request,
                path=path,
                response=response,
                redact=self.redact,
            )

    def _broken(self, line: dict[str, Any], exc: httpx.HTTPError) -> None:
        """A call that got no answer, such as a timeout, still counts and is logged."""
        error = self.redact(f"{type(exc).__name__}: {exc}")[:_ERROR_CHARS]
        self.ledger.append({**line, "usage": None, "cost_usd": None, "error": error})

    async def post_json(
        self,
        path: str,
        body: Any,
        *,
        caller: str,
        model: str,
        describe: str,
        units: Units | None = None,
        record_as: str | None = None,
    ) -> LiveResult:
        self._admit(record_as)
        t0 = time.perf_counter()
        try:
            async with self._client() as http:
                r = await http.post(path, json=body)
        except httpx.HTTPError as exc:
            self._broken(self._line(caller, model, describe, None, t0), exc)
            raise
        line = self._line(caller, model, describe, r.status_code, t0)
        if r.status_code != httpx.codes.OK:
            raise self._fail(line, r.status_code, r.text)
        data = r.json()
        usage = data.get("usage") if isinstance(data, dict) else None
        result = self._done(line, model, data, usage, units)  # the ledger line comes first
        self._record(record_as, model, r.request, path, {"status": r.status_code, "json": data})
        return result

    async def post_sse(
        self,
        path: str,
        body: Any,
        *,
        caller: str,
        model: str,
        describe: str,
        units: Units | None = None,
        record_as: str | None = None,
    ) -> LiveResult:
        """A streamed Responses call. The result body is the list of events in order."""
        self._admit(record_as)
        t0 = time.perf_counter()
        events: list[Any] = []
        try:
            async with (
                self._client() as http,
                http.stream("POST", path, json=body, headers={"Accept": "text/event-stream"}) as r,
            ):
                if r.status_code != httpx.codes.OK:
                    text = (await r.aread()).decode(errors="replace")
                    line = self._line(caller, model, describe, r.status_code, t0)
                    raise self._fail(line, r.status_code, text)
                async for raw in r.aiter_lines():
                    if not raw.startswith("data: "):
                        continue
                    data = raw.removeprefix("data: ")
                    if data == "[DONE]":
                        break
                    events.append(json.loads(data))
                request = r.request
        except httpx.HTTPError as exc:
            self._broken(self._line(caller, model, describe, None, t0), exc)
            raise
        line = self._line(caller, model, describe, httpx.codes.OK, t0)
        result = self._done(line, model, events, completed_usage(events), units)
        self._record(record_as, model, request, path, {"status": httpx.codes.OK, "events": events})
        return result

    async def post_multipart(
        self,
        path: str,
        files: Files,
        *,
        caller: str,
        model: str,
        describe: str,
        units: Units | None = None,
        record_as: str | None = None,
    ) -> LiveResult:
        self._admit(record_as)
        t0 = time.perf_counter()
        try:
            async with self._client() as http:
                r = await http.post(path, files=files, headers={"Accept": "application/json"})
        except httpx.HTTPError as exc:
            self._broken(self._line(caller, model, describe, None, t0), exc)
            raise
        line = self._line(caller, model, describe, r.status_code, t0)
        if r.status_code != httpx.codes.OK:
            raise self._fail(line, r.status_code, r.text)
        data = r.json()
        usage = data.get("usage") if isinstance(data, dict) else None
        result = self._done(line, model, data, usage, units)  # the ledger line comes first
        self._record(record_as, model, r.request, path, {"status": r.status_code, "json": data})
        return result
