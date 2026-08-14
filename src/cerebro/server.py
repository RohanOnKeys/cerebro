"""FastAPI ASGI app for everything Cerebro serves over HTTP.

There was previously no assembled FastAPI app in this repo — github/webhook.py
defined an APIRouter but nothing ever instantiated FastAPI() and mounted it,
so there was no `uvicorn cerebro.server:app` to run in production. This file
is that missing piece.

Run locally:
    uvicorn cerebro.server:app --reload --port 8000

Run in production (see the deployment guide for the full command, workers,
and process manager):
    uvicorn cerebro.server:app --host 0.0.0.0 --port 8000 --workers 2
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from cerebro.admin.router import router as admin_router
from cerebro.config import settings
from cerebro.github.webhook import router as github_webhook_router

app = FastAPI(
    title="Cerebro HTTP API",
    description="GitHub webhook receiver and the Admin/Read API for the team dashboard.",
    version="1.0.0",
    # Hide interactive docs outside development — the admin routes are
    # token-gated, but there's no reason to advertise the schema publicly.
    docs_url="/docs" if settings.environment == "development" else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    # Comma-separated list of exact origins, e.g.
    # "https://cerebro.yourcompany.com,http://localhost:3000" — see
    # settings.cors_allowed_origins. Never "*" once ADMIN_API_TOKEN-gated
    # routes exist behind it.
    allow_origins=settings.cors_allowed_origins_list,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(github_webhook_router)
app.include_router(admin_router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness/readiness probe for whatever's running this (Docker,
    Kubernetes, a PaaS health check, etc.)."""
    return {"status": "ok"}


def run_server() -> None:
    """Run the app under uvicorn (entrypoint: `cerebro-webhook`)."""
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    run_server()
