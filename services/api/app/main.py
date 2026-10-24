"""FastAPI application factory for the Talking Tactile backend."""

from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="Talking Tactile API", version="0.1.0")

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
