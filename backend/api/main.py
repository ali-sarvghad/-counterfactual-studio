"""FastAPI application entry point.

Run locally with:  uvicorn api.main:app --reload  (from the backend/ directory)
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import store
from .routes import router

app = FastAPI(
    title="Counterfactual Participant Studio",
    description="Generate simulated study participants using the Bayesian "
                "approach of While & Sarvghad (CHI '25).",
    version="0.1.0",
)

# During development the React app runs on the Vite dev server.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    store.init_db()


app.include_router(router)

# Serve the built frontend (Phase 3) if present, so the whole app can run from
# a single process in production.
_FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=_FRONTEND_DIST, html=True), name="frontend")
