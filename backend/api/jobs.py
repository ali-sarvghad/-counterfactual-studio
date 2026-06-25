"""Background job runner for the slow step: fitting Bayesian models.

MCMC can take minutes, so fits run on a small thread pool and report progress
through the project's ``status`` field (``fitting`` -> ``fitted`` / ``failed``),
which the frontend polls. The fitted model is not kept alive: we extract and
persist the posterior cell-mean draws (``draws.npz``) so generation later needs
only NumPy.
"""

from __future__ import annotations

import json
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from studio import engine
from studio.spec import StudyDesign

from . import store

_EXECUTOR = ThreadPoolExecutor(max_workers=2)


# --------------------------------------------------------------------------- #
# Draws cache (de)serialization
# --------------------------------------------------------------------------- #
def save_draws(path: Path, draws: dict[str, Any]) -> None:
    arrays: dict[str, np.ndarray] = {}
    meta: dict[str, Any] = {"grouping": draws["grouping"], "outcomes": {}}
    for name, o in draws["outcomes"].items():
        arrays[f"{name}__raw"] = np.asarray(o["raw"])
        if o["sigma"] is not None:
            arrays[f"{name}__sigma"] = np.asarray(o["sigma"])
        meta["outcomes"][name] = {
            "family": o["family"], "guess_rate": o["guess_rate"],
            "trials_per_cell": o["trials_per_cell"],
            "has_sigma": o["sigma"] is not None,
        }
    np.savez_compressed(path, **arrays)
    path.with_suffix(".meta.json").write_text(json.dumps(meta))


def load_draws(path: Path) -> dict[str, Any]:
    meta = json.loads(path.with_suffix(".meta.json").read_text())
    npz = np.load(path)
    out: dict[str, Any] = {"grouping": meta["grouping"], "outcomes": {}}
    for name, m in meta["outcomes"].items():
        out["outcomes"][name] = {
            "family": m["family"], "guess_rate": m["guess_rate"],
            "trials_per_cell": m["trials_per_cell"],
            "raw": npz[f"{name}__raw"],
            "sigma": npz[f"{name}__sigma"] if m["has_sigma"] else None,
        }
    return out


# --------------------------------------------------------------------------- #
# Fit job
# --------------------------------------------------------------------------- #
def submit_fit(project_id: str, fit_kwargs: dict[str, Any]) -> None:
    store.set_status(project_id, "fitting")
    _EXECUTOR.submit(_run_fit, project_id, fit_kwargs)


def _run_fit(project_id: str, fit_kwargs: dict[str, Any]) -> None:
    try:
        proj = store.get_project(project_id)
        design = StudyDesign.from_dict(proj["design"])
        df = pd.read_csv(store.data_csv(project_id))
        priors = fit_kwargs.pop("priors", None)
        bundle = engine.fit(design, df, priors=priors, **fit_kwargs)
        draws = engine.posterior_draws(bundle)
        save_draws(store.draws_npz(project_id), draws)
        diagnostics = {n: f.diagnostics for n, f in bundle.fits.items()}
        store.set_fit_result(project_id, diagnostics)
    except Exception as exc:  # noqa: BLE001 - report any failure back to the user
        store.set_status(project_id, "failed",
                         fit_error=f"{type(exc).__name__}: {exc}\n"
                                   + traceback.format_exc(limit=3))
