"""Pydantic request/response models for the HTTP API.

The study design itself is accepted as a raw dict and validated through the
dataclass model in :mod:`studio.spec` (the single source of truth), so the
schema is never duplicated.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Projects & design
# --------------------------------------------------------------------------- #
class CreateProject(BaseModel):
    name: str = Field(default="Untitled project")
    template: Optional[str] = Field(
        default=None, description="Optional template key, e.g. 'paper' or 'blank'."
    )
    design: Optional[dict[str, Any]] = Field(
        default=None, description="A full design dict (overrides template)."
    )


class UpdateDesign(BaseModel):
    design: dict[str, Any]


class ProjectSummary(BaseModel):
    id: str
    name: str
    status: str
    created_at: str
    updated_at: str
    n_cells: Optional[int] = None
    data_rows: Optional[int] = None


class ProjectDetail(ProjectSummary):
    design: dict[str, Any]
    column_mapping: Optional[dict[str, str]] = None
    fit_diagnostics: Optional[dict[str, Any]] = None
    fit_error: Optional[str] = None
    generation: Optional[dict[str, Any]] = None


# --------------------------------------------------------------------------- #
# Design validation / formula preview
# --------------------------------------------------------------------------- #
class ValidateResponse(BaseModel):
    valid: bool
    error: Optional[str] = None
    n_cells: Optional[int] = None
    formulas: Optional[dict[str, dict[str, str]]] = None


# --------------------------------------------------------------------------- #
# Data upload
# --------------------------------------------------------------------------- #
class ColumnMapping(BaseModel):
    mapping: dict[str, str] = Field(
        description="Maps design roles (factor/outcome/grouping names) to CSV columns."
    )
    apply_hampel: bool = Field(
        default=False, description="Apply a Hampel outlier filter to continuous outcomes."
    )


class DataPreview(BaseModel):
    columns: list[str]
    rows: list[dict[str, Any]]
    n_rows: int
    suggested_mapping: dict[str, str]


# --------------------------------------------------------------------------- #
# Fitting
# --------------------------------------------------------------------------- #
class FitRequest(BaseModel):
    draws: int = 1000
    tune: int = 1000
    chains: int = 4
    seed: int = 1234
    target_accept: float = 0.9
    priors: Optional[dict[str, Any]] = None


# --------------------------------------------------------------------------- #
# Generation
# --------------------------------------------------------------------------- #
class CellMean(BaseModel):
    # cell identified by factor levels -> natural-unit mean per outcome
    pass


class Assumptions(BaseModel):
    cell_means: dict[str, dict[str, float]]
    between_sd: dict[str, float] = Field(default_factory=dict)
    residual_sd: dict[str, float] = Field(default_factory=dict)


class GenerateRequest(BaseModel):
    source: str = Field(default="posterior", description="'posterior' or 'assumptions'.")
    n_participants: int = 2000
    seed: int = 7
    assumptions: Optional[Assumptions] = None


class GenerateResponse(BaseModel):
    n_participants: int
    source: str
    n_cells: int
    n_trials: int
    cell_means_preview: list[dict[str, Any]]
    summary: dict[str, Any]
    artifacts: list[str]


# --------------------------------------------------------------------------- #
# Live previews (no sampling required)
# --------------------------------------------------------------------------- #
class OutcomeImplicationRequest(BaseModel):
    family: str
    guess_rate: float = 0.0
    mean: float
    between_sd: float = 0.3


class PriorImplicationRequest(BaseModel):
    family: str
    guess_rate: float = 0.0
    prior_mean: float = 0.0
    prior_sd: float = 1.0


class ImplicationResponse(BaseModel):
    percentiles: dict[str, float]
    samples: list[float]
    explanation: str
