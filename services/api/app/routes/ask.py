"""POST /api/ask: a question about a published figure (app/ask.py).

JSON for a typed question: {figure_id, version?, question, region_id, recent_region_ids,
session_id}. A spoken one is multipart: a `request` part with the same JSON, question left
out, and an `audio` part, a WAV of mono 16-bit PCM at 16 or 24 kHz.

The answer comes back with the transcript and the time each step took. Every message in an
error is written to be spoken: Explore says it as it is."""

import asyncio
import json
from typing import Any

import httpx
from fastapi import APIRouter, Request
from pydantic import ValidationError
from starlette.datastructures import UploadFile

from app import ask as asking
from app.ask import FAILED, AskRequest, QuestionCapError, WavError
from app.errors import ApiError
from app.meta.live import LiveCallCapError, LiveCallError, MalformedResponseError
from app.meta.mock import MockFixtureMissingError

router = APIRouter(prefix="/api")
_CALL_ERRORS = (
    LiveCallError,
    LiveCallCapError,
    MalformedResponseError,
    httpx.HTTPError,
    MockFixtureMissingError,
)


async def _read(request: Request) -> tuple[AskRequest, bytes | None]:
    ctype = request.headers.get("content-type", "")
    try:
        if ctype.startswith("multipart/form-data"):
            async with request.form() as form:  # closes the uploaded file
                audio = form.get("audio")
                raw = form.get("request")
                if not isinstance(audio, UploadFile) or not isinstance(raw, str):
                    raise ApiError(422, "invalid_request", "Send a request part and an audio part.")
                return AskRequest.model_validate(json.loads(raw)), await audio.read()
        if not ctype.startswith("application/json"):
            raise ApiError(415, "invalid_request", "Send the question as JSON.")
        body: Any = await request.json()
        req = AskRequest.model_validate(body)
    except (ValidationError, json.JSONDecodeError) as exc:
        raise ApiError(422, "invalid_request", "The question request is not valid.") from exc
    if not req.question:
        raise ApiError(422, "invalid_request", "Type a question, or hold the screen to ask.")
    return req, None


@router.post("/transcribe")
async def transcribe(request: Request) -> dict[str, Any]:
    """A held question's words, for Explore to parse on the device before asking (multipart,
    as a spoken /api/ask: a request part and an audio part)."""
    service = request.app.state.figure_service()
    req, audio = await _read(request)
    if audio is None:
        raise ApiError(422, "invalid_request", "Send a request part and an audio part.")
    try:
        heard = await asyncio.wait_for(service.asker().transcribe(req, audio), asking.DEADLINE_S)
    except WavError as exc:
        raise ApiError(
            422, "audio_invalid", "That recording could not be read. Ask again."
        ) from exc
    except QuestionCapError as exc:
        raise ApiError(429, "question_cap", str(exc)) from exc
    except (*_CALL_ERRORS, TimeoutError) as exc:
        raise ApiError(502, "answer_failed", FAILED, True) from exc
    out: dict[str, Any] = heard.model_dump(mode="json")
    return out


@router.post("/ask")
async def ask(request: Request) -> dict[str, Any]:
    service = request.app.state.figure_service()
    req, audio = await _read(request)
    try:
        answer = await asyncio.wait_for(service.asker().ask(req, audio), asking.DEADLINE_S)
    except WavError as exc:
        raise ApiError(
            422, "audio_invalid", "That recording could not be read. Ask again."
        ) from exc
    except QuestionCapError as exc:
        raise ApiError(429, "question_cap", str(exc)) from exc
    except (*_CALL_ERRORS, TimeoutError) as exc:  # TimeoutError: past DEADLINE_S
        raise ApiError(502, "answer_failed", FAILED, True) from exc
    out: dict[str, Any] = answer.model_dump(mode="json")
    return out
