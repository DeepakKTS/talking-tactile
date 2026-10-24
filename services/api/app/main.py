"""FastAPI application factory for the Talking Tactile backend."""

import os
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import errors, logs
from app.braille.louis import BrailleUnavailableError, Translator
from app.config import ExploreConfig, TactileRules, load_explore, load_tactile_rules
from app.errors import ApiError
from app.figures import FigureService, PublishStore
from app.meta.client import LiveClientUnavailableError, MetaClient, make_client
from app.middleware import RequestContext, UploadGuard
from app.paths import DATA_DIR, EXPLORE_YAML, TACTILE_RULES_YAML
from app.pipeline.edits import EditStore
from app.pipeline.jobs import JobStore
from app.pipeline.runner import Runner
from app.routes import figures

# The Vite dev server. In development the web app reaches the API through its proxy, so
# this matters only for direct calls; no other origin is allowed.
WEB_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")
_BYTES_PER_MB = 1024 * 1024


def _figure_service(
    rules: TactileRules, explore: ExploreConfig, data_dir: Path, client: MetaClient | None
) -> Callable[[], FigureService]:
    """Built on first use, so the app starts (and /api/health answers) without the Meta
    client or liblouis; a figure request then gets a 503 that says what is missing."""
    built: list[FigureService] = []

    def get() -> FigureService:
        if built:
            return built[0]
        try:
            meta = client or make_client(os.environ.get("MOCK_META") == "1", rules.meta)
            translator = Translator(rules.braille)
        except (LiveClientUnavailableError, BrailleUnavailableError) as exc:
            raise ApiError(503, "unavailable", str(exc)) from exc
        db_path = data_dir / "jobs.sqlite"
        runner = Runner(
            client=meta,
            rules=rules,
            explore=explore,
            translator=translator,
            jobs=JobStore(db_path),
            edits=EditStore(db_path),
            figures_dir=data_dir / "figures",
        )
        built.append(FigureService(runner, PublishStore(db_path, data_dir / "published")))
        return built[0]

    return get


def create_app(
    tactile_rules_path: Path = TACTILE_RULES_YAML,
    explore_path: Path = EXPLORE_YAML,
    *,
    data_dir: Path = DATA_DIR,
    client: MetaClient | None = None,
) -> FastAPI:
    # Config is loaded and validated before the app exists, so a bad value stops startup.
    tactile_rules = load_tactile_rules(tactile_rules_path)
    explore = load_explore(explore_path)
    logs.configure()

    app = FastAPI(title="Talking Tactile API", version="0.1.0")
    app.state.tactile_rules = tactile_rules
    app.state.explore = explore
    app.state.figure_service = _figure_service(tactile_rules, explore, data_dir, client)
    errors.install(app)
    app.include_router(figures.router)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    # The last one added runs first: request id, then CORS, then the upload guard.
    max_bytes = int(tactile_rules.pipeline.max_upload_mb * _BYTES_PER_MB)
    app.add_middleware(UploadGuard, max_bytes=max_bytes)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(WEB_ORIGINS),
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Content-Type", "If-None-Match", "X-Request-ID"],
        expose_headers=["ETag", "X-Request-ID"],
    )
    app.add_middleware(RequestContext)
    return app


app = create_app()
