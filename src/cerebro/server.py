"""HTTP entrypoint: the FastAPI app that actually serves the GitHub webhook.

`github/webhook.py` only defines an `APIRouter`. Nothing else in the
codebase runs a web server, so that router was never reachable over HTTP.
This module is what mounts it and serves it, via `uvicorn`.
"""

from __future__ import annotations

from fastapi import FastAPI

from cerebro.github.webhook import router as github_webhook_router

app = FastAPI(title="Cerebro", version="0.1.0")
app.include_router(github_webhook_router)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness check, useful for confirming the process is up before wiring GitHub."""
    return {"status": "ok"}


def run_server() -> None:
    """Run the app under uvicorn (entrypoint: `cerebro-webhook`)."""
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    run_server()
