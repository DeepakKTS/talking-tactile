"""JSON logs: one object per line with the request id and any of the known extra fields
(stage, timing, cost, job). The request id is a context variable, so background pipeline
tasks started from a request log under that request's id."""

import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime

request_id: ContextVar[str | None] = ContextVar("request_id", default=None)

FIELDS = ("job_id", "figure_id", "stage", "outcome", "ms", "cost_usd", "method", "path", "status")
_MARK = "_talking_tactile_json"


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        obj: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
        }
        rid = record.__dict__.get("request_id", request_id.get())
        if rid is not None:
            obj["request_id"] = rid
        for field in FIELDS:
            if field in record.__dict__:
                obj[field] = record.__dict__[field]
        if record.exc_info:
            obj["exc"] = self.formatException(record.exc_info)
        return json.dumps(obj, default=str)


class RequestIdFilter(logging.Filter):
    """Stamps the request id on the record when it is logged, so handlers that format it
    later still see it."""

    def filter(self, record: logging.LogRecord) -> bool:
        if "request_id" not in record.__dict__:
            record.request_id = request_id.get()
        return True


def configure() -> None:
    """JSON lines on stderr for the app's loggers. Safe to call more than once."""
    logger = logging.getLogger("app")
    if any(getattr(h, _MARK, False) for h in logger.handlers):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RequestIdFilter())
    setattr(handler, _MARK, True)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
