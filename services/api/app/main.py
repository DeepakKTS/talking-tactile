"""FastAPI application factory for the Talking Tactile backend."""

from pathlib import Path

from fastapi import FastAPI

from app.config import load_explore, load_tactile_rules
from app.paths import EXPLORE_YAML, TACTILE_RULES_YAML


def create_app(
    tactile_rules_path: Path = TACTILE_RULES_YAML, explore_path: Path = EXPLORE_YAML
) -> FastAPI:
    # Config is loaded and validated before the app exists, so a bad value stops startup.
    tactile_rules = load_tactile_rules(tactile_rules_path)
    explore = load_explore(explore_path)

    app = FastAPI(title="Talking Tactile API", version="0.1.0")
    app.state.tactile_rules = tactile_rules
    app.state.explore = explore

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
