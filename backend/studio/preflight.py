"""Pre-fit sanity checks that catch the failures non-experts can't diagnose.

Fitting a Bayesian model can fail or mislead for reasons that have nothing to do
with the wizard's flow and everything to do with the *shape* of the data versus
the *complexity* of the model -- most commonly an **empty cell**: the model asks
for a separate effect for a factor combination that never occurs in the data, so
the sampler can't even start (PyMC's "Initial evaluation ... failed").

This module inspects a committed design + dataset and returns plain-language
issues with concrete, one-click-fixable suggestions, so the UI can warn (and
offer to fix) *before* burning minutes on a fit that was doomed from the start.
"""

from __future__ import annotations

from itertools import combinations, product
from typing import Any

import pandas as pd

from .spec import FactorKind, StudyDesign

# A categorical level with fewer rows than this is too thin to estimate well.
_MIN_LEVEL_OBS = 3


def _categorical(design: StudyDesign) -> list:
    return [f for f in design.factors if f.kind == FactorKind.CATEGORICAL]


def _levels(factor, df: pd.DataFrame) -> list[str]:
    if factor.levels:
        return [str(x) for x in factor.levels]
    if factor.name in df.columns:
        return [str(x) for x in df[factor.name].dropna().unique().tolist()]
    return []


def _highest_order_termsets(names: list[str], order) -> list[tuple[str, ...]]:
    """The factor groups whose full crossing the model will try to estimate."""
    n = len(names)
    if n < 2:
        return []
    if order is None or order >= n:
        return [tuple(names)]                 # full interaction = one big crossing
    order = max(int(order), 0)
    if order < 2:
        return []                             # main effects only -> no crossing
    return [tuple(c) for c in combinations(names, order)]


def _empty_cells(cats, df: pd.DataFrame, order) -> tuple[int, list[str]]:
    """Count factor combinations the model needs but the data never shows."""
    names = [f.name for f in cats]
    by_name = {f.name: f for f in cats}
    n_empty = 0
    examples: list[str] = []
    for ts in _highest_order_termsets(names, order):
        cols = list(ts)
        if not all(c in df.columns for c in cols):
            continue
        observed = df.groupby(cols).size() if len(cols) > 1 else df[cols[0]].value_counts()
        level_lists = [[(c, lv) for lv in _levels(by_name[c], df)] for c in cols]
        for combo in product(*level_lists):
            key = tuple(str(lv) for (_, lv) in combo)
            lookup = key if len(key) > 1 else key[0]
            try:
                count = int(observed.get(lookup, 0))
            except (KeyError, TypeError):
                count = 0
            if count == 0:
                n_empty += 1
                if len(examples) < 5:
                    examples.append(", ".join(f"{c}={lv}" for (c, lv) in combo))
    return n_empty, examples


def _fixed_coeff_estimate(cats, df: pd.DataFrame, order) -> int:
    """Rough number of fixed-effect coefficients for the current interaction."""
    names = [f.name for f in cats]
    n = len(names)
    if n == 0:
        return 0
    lv = {f.name: max(len(_levels(f, df)), 1) for f in cats}
    if order is None or order >= n:
        p = 1
        for nm in names:
            p *= lv[nm]
        return p
    order = max(int(order), 0)
    if order == 0:
        return 1 + sum(lv[nm] - 1 for nm in names)
    total = 0
    for k in range(1, order + 1):
        for combo in combinations(names, k):
            term = 1
            for nm in combo:
                term *= lv[nm] if k == 1 else max(lv[nm] - 1, 1)
            total += term
    return total


def preflight(design: StudyDesign, df: pd.DataFrame) -> dict[str, Any]:
    """Check a design against its data; return issues + a recommended setting."""
    cats = _categorical(design)
    n_obs = int(len(df))
    order = design.interaction_order
    issues: list[dict[str, Any]] = []
    recommended_order = order

    # 1. Empty cells in the interaction the model will estimate (blocking).
    n_empty, examples = _empty_cells(cats, df, order)
    if n_empty:
        issues.append({
            "id": "empty_cells",
            "severity": "error",
            "title": (f"{n_empty} factor combination never occurs in your data"
                      if n_empty == 1
                      else f"{n_empty} factor combinations never occur in your data"),
            "detail": (
                "Your model estimates a separate effect for every combination of "
                "the interacting factors, but some combinations have no rows "
                f"(for example: {'; '.join(examples)}). The fit can't start until "
                "every needed combination has at least one observation."),
            "suggestions": [
                "Switch to main effects only — model each factor on its own, "
                "with no interaction. This is the simplest fix and almost always "
                "what you want with limited data.",
                "Or remove one of the interacting factors.",
                "Or merge small categories so every combination is covered.",
            ],
            "fix": {"type": "set_interaction_order", "value": 0,
                    "label": "Switch to main effects only"},
        })
        recommended_order = 0

    # 2. Categories with too few rows to estimate (warning).
    sparse: list[str] = []
    for f in cats:
        if f.name not in df.columns:
            continue
        vc = df[f.name].value_counts()
        for lv, c in vc.items():
            if int(c) < _MIN_LEVEL_OBS:
                sparse.append(f"{f.name}={lv} ({int(c)} row{'s' if int(c) != 1 else ''})")
    if sparse:
        issues.append({
            "id": "sparse_levels",
            "severity": "warning",
            "title": "Some categories have very few observations",
            "detail": ("These categories have fewer than 3 rows, so their "
                       "estimates will be shaky: " + "; ".join(sparse[:8])
                       + ("; …" if len(sparse) > 8 else "") + "."),
            "suggestions": [
                "Merge a rare category into a similar one.",
                "Collect more data for these categories if you can.",
            ],
        })

    # 3. More parameters than data points (warning), independent of empty cells.
    n_fixed = _fixed_coeff_estimate(cats, df, order)
    if n_fixed and n_obs and n_fixed >= n_obs and not n_empty:
        issues.append({
            "id": "overparameterized",
            "severity": "warning",
            "title": "The model has about as many parameters as data points",
            "detail": (f"Your design implies roughly {n_fixed} effects to "
                       f"estimate from {n_obs} rows. The fit may run but will be "
                       "very uncertain and prone to divergences."),
            "suggestions": [
                "Use main effects only, or fewer factors.",
                "Combine categories, or collect more data.",
            ],
            "fix": {"type": "set_interaction_order", "value": 0,
                    "label": "Switch to main effects only"},
        })
        if recommended_order not in (0,):
            recommended_order = 0

    has_error = any(i["severity"] == "error" for i in issues)
    return {
        "ok": not has_error,
        "issues": issues,
        "recommended_interaction_order": recommended_order,
        "n_obs": n_obs,
        "n_fixed": n_fixed,
    }
