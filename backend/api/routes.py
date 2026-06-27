"""HTTP routes wrapping the engine into a guided, wizard-friendly API."""

from __future__ import annotations

import io
from typing import Any

import pandas as pd
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from studio import analysis, engine, preflight, profile
from studio.export import (
    bambi_script,
    brms_script,
    design_to_json,
    reproducibility_report,
)
from studio.formula import brms_family, brms_formula, build_formula
from studio.preprocess import hampel_filter
from studio.spec import OutcomeFamily, SpecError, StudyDesign
from studio.templates import TEMPLATES, get_template

from . import jobs, previews, store
from .schemas import (
    ColumnMapping,
    CreateProject,
    FitRequest,
    GenerateRequest,
    OutcomeImplicationRequest,
    PriorImplicationRequest,
    UpdateDesign,
    ValidateResponse,
)

router = APIRouter(prefix="/api")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _design_or_400(d: dict[str, Any]) -> StudyDesign:
    try:
        design = StudyDesign.from_dict(d)
        design.validate()
        return design
    except (SpecError, KeyError, ValueError) as exc:
        raise HTTPException(400, f"Invalid design: {exc}") from exc


def _project_or_404(project_id: str) -> dict[str, Any]:
    proj = store.get_project(project_id)
    if not proj:
        raise HTTPException(404, "Project not found")
    return proj


def _formulas(design: StudyDesign) -> dict[str, dict[str, str]]:
    out = {}
    for o in design.outcomes:
        parts = build_formula(design, o)
        out[o.name] = {
            "bambi": parts.bambi_formula,
            "brms": brms_formula(design, o),
            "brms_family": brms_family(o),
            "fit_note": ("Fit as gaussian on log(%s); brms uses native lognormal()."
                         % o.name) if parts.needs_log_transform else "",
        }
    return out


# --------------------------------------------------------------------------- #
# Templates & design helpers
# --------------------------------------------------------------------------- #
@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/templates")
def templates() -> list[dict[str, Any]]:
    out = []
    for key in TEMPLATES:
        d = get_template(key)
        out.append({"key": key, "name": d.name, "description": d.description,
                    "n_cells": d.n_cells(),
                    "n_factors": len(d.factors), "n_outcomes": len(d.outcomes)})
    return out


@router.get("/templates/{key}")
def template(key: str) -> dict[str, Any]:
    try:
        return get_template(key).to_dict()
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/designs/validate", response_model=ValidateResponse)
def validate_design(body: UpdateDesign) -> ValidateResponse:
    try:
        design = StudyDesign.from_dict(body.design)
        design.validate()
    except (SpecError, KeyError, ValueError) as exc:
        return ValidateResponse(valid=False, error=str(exc))
    return ValidateResponse(valid=True, n_cells=design.n_cells(),
                            formulas=_formulas(design))


@router.post("/designs/preview-outcome")
def preview_outcome(body: OutcomeImplicationRequest) -> dict[str, Any]:
    return previews.outcome_implications(
        body.family, body.guess_rate, body.mean, body.between_sd)


@router.post("/designs/preview-prior")
def preview_prior(body: PriorImplicationRequest) -> dict[str, Any]:
    return previews.prior_implications(
        body.family, body.guess_rate, body.prior_mean, body.prior_sd)


# --------------------------------------------------------------------------- #
# Projects
# --------------------------------------------------------------------------- #
def _detail(proj: dict[str, Any]) -> dict[str, Any]:
    design = StudyDesign.from_dict(proj["design"])
    n_cells = None
    try:
        design.validate()
        n_cells = design.n_cells()
    except Exception:
        pass
    return {**proj, "n_cells": n_cells}


@router.post("/projects")
def create_project(body: CreateProject) -> dict[str, Any]:
    if body.design is not None:
        design = _design_or_400(body.design)
    elif body.template:
        try:
            design = get_template(body.template)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
    else:
        design = get_template("blank")
    pid = store.create_project(body.name, design.to_dict())
    return _detail(_project_or_404(pid))


@router.get("/projects")
def list_projects() -> list[dict[str, Any]]:
    return [_detail(p) for p in store.list_projects()]


@router.get("/projects/{project_id}")
def get_project(project_id: str) -> dict[str, Any]:
    return _detail(_project_or_404(project_id))


@router.put("/projects/{project_id}/design")
def update_design(project_id: str, body: UpdateDesign) -> dict[str, Any]:
    _project_or_404(project_id)
    design = _design_or_400(body.design)
    store.update_design(project_id, design.to_dict())
    return _detail(_project_or_404(project_id))


@router.delete("/projects/{project_id}")
def delete_project(project_id: str) -> dict[str, str]:
    _project_or_404(project_id)
    store.delete_project(project_id)
    return {"status": "deleted"}


# --------------------------------------------------------------------------- #
# Data upload (data path)
# --------------------------------------------------------------------------- #
def _suggest_mapping(design: StudyDesign, columns: list[str]) -> dict[str, str]:
    lower = {c.lower(): c for c in columns}
    mapping: dict[str, str] = {}
    roles = [design.grouping] + [f.name for f in design.factors] + \
            [o.name for o in design.outcomes]
    for role in roles:
        if role in columns:
            mapping[role] = role
        elif role.lower() in lower:
            mapping[role] = lower[role.lower()]
    return mapping


@router.post("/projects/{project_id}/data/upload")
async def upload_data(project_id: str, file: UploadFile = File(...)) -> dict[str, Any]:
    proj = _project_or_404(project_id)
    design = StudyDesign.from_dict(proj["design"])
    raw = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(raw))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"Could not parse CSV: {exc}") from exc
    # stash the raw upload so a later commit can re-map columns
    (store.project_dir(project_id) / "upload.csv").write_bytes(raw)
    return {
        "columns": list(df.columns),
        "rows": df.head(8).where(pd.notna(df.head(8)), None).to_dict("records"),
        "n_rows": int(len(df)),
        "suggested_mapping": _suggest_mapping(design, list(df.columns)),
    }


def _commit_mapped(project_id: str, design: StudyDesign,
                   mapping: dict[str, str], apply_hampel: bool) -> dict[str, Any]:
    """Shared commit: rename CSV columns to the design's names, optionally filter."""
    upload = store.project_dir(project_id) / "upload.csv"
    if not upload.exists():
        raise HTTPException(400, "No uploaded file to commit; upload first.")
    df = pd.read_csv(upload)
    # rename selected columns to the design's canonical names
    rename = {src: role for role, src in mapping.items() if src in df.columns}
    df = df.rename(columns=rename)
    needed = [design.grouping] + [f.name for f in design.factors] + \
             [o.name for o in design.outcomes]
    missing = [n for n in needed if n not in df.columns]
    if missing:
        raise HTTPException(400, f"Mapping is missing required fields: {missing}")
    df = df[needed]

    report = {}
    if apply_hampel:
        df, report = hampel_filter(design, df)
    df.to_csv(store.data_csv(project_id), index=False)
    store.set_data(project_id, len(df), mapping)
    return {"n_rows": int(len(df)), "hampel": report,
            "project": _detail(_project_or_404(project_id))}


@router.post("/projects/{project_id}/data/commit")
def commit_data(project_id: str, body: ColumnMapping) -> dict[str, Any]:
    proj = _project_or_404(project_id)
    design = StudyDesign.from_dict(proj["design"])
    return _commit_mapped(project_id, design, body.mapping, body.apply_hampel)


@router.post("/projects/{project_id}/data/profile")
def profile_data(project_id: str) -> dict[str, Any]:
    """Auto-detect roles + distribution families from the uploaded CSV."""
    _project_or_404(project_id)
    upload = store.project_dir(project_id) / "upload.csv"
    if not upload.exists():
        raise HTTPException(400, "No uploaded file to profile; upload first.")
    df = pd.read_csv(upload)
    return profile.profile_dataframe(df)


# --------------------------------------------------------------------------- #
# Fitting (data path)
# --------------------------------------------------------------------------- #
@router.post("/projects/{project_id}/preflight")
def preflight_check(project_id: str) -> dict[str, Any]:
    """Check the committed data against the design for fit-blocking problems."""
    proj = _project_or_404(project_id)
    design = StudyDesign.from_dict(proj["design"])
    csv = store.data_csv(project_id)
    if not csv.exists():
        return {"ok": True, "issues": [], "n_obs": 0,
                "recommended_interaction_order": design.interaction_order}
    return preflight.preflight(design, pd.read_csv(csv))


@router.post("/projects/{project_id}/fit")
def start_fit(project_id: str, body: FitRequest) -> dict[str, Any]:
    proj = _project_or_404(project_id)
    if not store.data_csv(project_id).exists():
        raise HTTPException(400, "Upload and commit data before fitting.")
    if proj["status"] == "fitting":
        raise HTTPException(409, "A fit is already running for this project.")
    jobs.submit_fit(project_id, body.model_dump())
    return {"status": "fitting"}


@router.get("/projects/{project_id}/status")
def fit_status(project_id: str) -> dict[str, Any]:
    proj = _project_or_404(project_id)
    return {"status": proj["status"],
            "diagnostics": proj.get("fit_diagnostics"),
            "error": proj.get("fit_error")}


# --------------------------------------------------------------------------- #
# Generation (both paths)
# --------------------------------------------------------------------------- #
@router.post("/projects/{project_id}/generate")
def generate(project_id: str, body: GenerateRequest) -> dict[str, Any]:
    proj = _project_or_404(project_id)
    design = StudyDesign.from_dict(proj["design"])
    design.validate()

    if body.source == "posterior":
        if not store.draws_npz(project_id).exists():
            raise HTTPException(400, "No fitted model yet; fit before generating "
                                     "from the posterior (or use the assumptions path).")
        draws = jobs.load_draws(store.draws_npz(project_id))
        result = engine.generate_from_draws(design, draws, body.n_participants, body.seed)
        sample_kwargs = {"n_participants": body.n_participants, "seed": body.seed}
    elif body.source == "assumptions":
        if body.assumptions is None:
            raise HTTPException(400, "Assumptions are required for the assumptions path.")
        a = engine.Assumptions(
            cell_means=body.assumptions.cell_means,
            between_sd=body.assumptions.between_sd,
            residual_sd=body.assumptions.residual_sd,
        )
        result = engine.generate_from_assumptions(design, a, body.n_participants, body.seed)
        sample_kwargs = {"n_participants": body.n_participants, "seed": body.seed}
    else:
        raise HTTPException(400, "source must be 'posterior' or 'assumptions'.")

    # write artifacts
    pdir = store.project_dir(project_id)
    result.cell_means.to_csv(pdir / "cell_means.csv", index=False)
    result.trials.to_csv(pdir / "trials.csv", index=False)
    (pdir / "design.json").write_text(design_to_json(design))
    (pdir / "bambi_fit.py").write_text(bambi_script(design))
    (pdir / "brms_fit.R").write_text(brms_script(design))
    (pdir / "reproducibility_report.md").write_text(
        reproducibility_report(
            design, source=result.source, n_participants=result.n_participants,
            seed=body.seed,
            diagnostics=proj.get("fit_diagnostics") if body.source == "posterior" else None,
            sample_kwargs=sample_kwargs,
        )
    )
    summary = analysis.summarize(design, result.cell_means)

    artifacts = ["cell_means.csv", "trials.csv", "design.json",
                 "bambi_fit.py", "brms_fit.R", "reproducibility_report.md"]
    gen_meta = {"source": result.source, "n_participants": result.n_participants,
                "n_cells": design.n_cells(), "n_trials": int(len(result.trials)),
                "artifacts": artifacts}
    store.set_generation(project_id, gen_meta)

    preview = result.cell_means.head(12).to_dict("records")
    return {**gen_meta, "summary": summary, "cell_means_preview": preview}


@router.get("/projects/{project_id}/download/{name}")
def download(project_id: str, name: str) -> FileResponse:
    _project_or_404(project_id)
    if "/" in name or ".." in name:
        raise HTTPException(400, "Invalid artifact name.")
    path = store.artifact(project_id, name)
    if not path.exists():
        raise HTTPException(404, "Artifact not found.")
    return FileResponse(path, filename=name)
