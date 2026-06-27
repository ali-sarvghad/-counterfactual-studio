"""Automatic profiling of an uploaded dataset.

The hardest decision for a researcher without a statistics background is which
*likelihood family* fits each measured outcome -- yet that choice is fully
determined by the shape of the data they already have. This module reads a raw
long-format CSV and proposes, for every column, a role (participant /
categorical factor / measured outcome) and, for outcomes, the most appropriate
:class:`~studio.spec.OutcomeFamily`, together with a small sample of the values
so the UI can draw the distribution's shape.

Everything here is a *suggestion*: the wizard pre-fills the design from it and
lets the researcher confirm or override every field before fitting. The logic is
deliberately transparent (each guess carries a plain-language ``reason``) so the
tool teaches rather than hides the modeling choice.
"""

from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from .spec import (
    Factor,
    FactorKind,
    FactorRole,
    Outcome,
    OutcomeFamily,
    StudyDesign,
)

# A column with at most this many distinct values is treated as categorical
# (a factor) rather than a continuous measurement.
_MAX_FACTOR_LEVELS = 20
# Cap the per-column value sample handed to the UI for drawing a histogram.
_SAMPLE_CAP = 500

_PARTICIPANT_RE = re.compile(
    r"(?i)(particip|subject|\bsubj\b|respond|person|\buser\b|^id$|_id$|\bpid\b)"
)
_OUTCOME_NAME_RE = re.compile(
    r"(?i)(accuracy|correct|score|rating|\brt\b|reaction|response.?time|"
    r"\btime\b|duration|latency|count|\berror|clicks?|fixation)"
)


def _sanitize_ident(name: str) -> str:
    """Turn an arbitrary column header into a valid model-variable identifier."""
    s = re.sub(r"\W+", "_", str(name).strip()).strip("_")
    if not s or not s[0].isalpha():
        s = "v_" + s
    return s


def _unique_ident(name: str, taken: set[str]) -> str:
    base = _sanitize_ident(name)
    cand = base
    i = 2
    while cand in taken:
        cand = f"{base}_{i}"
        i += 1
    taken.add(cand)
    return cand


def _samples(values: np.ndarray) -> list[float]:
    """A bounded, deterministic sample of a numeric column for the UI histogram."""
    if values.size <= _SAMPLE_CAP:
        return [float(v) for v in values]
    rng = np.random.default_rng(0)
    idx = rng.choice(values.size, size=_SAMPLE_CAP, replace=False)
    return [float(v) for v in values[idx]]


def _detect_family(values: np.ndarray) -> tuple[OutcomeFamily, str]:
    """Pick the likelihood family that best matches a numeric column's shape."""
    uniq = np.unique(values)
    all_int = bool(np.allclose(values, np.round(values)))
    mn, mx = float(values.min()), float(values.max())
    skew = float(stats.skew(values)) if values.size >= 3 else 0.0

    if set(uniq.tolist()) <= {0.0, 1.0}:
        return (
            OutcomeFamily.BERNOULLI,
            "Only two values (0/1) — looks like correct/incorrect or yes/no.",
        )
    if all_int and mn >= 0 and (mx <= 50 or mn == 0) and skew > 0.4:
        return (
            OutcomeFamily.POISSON,
            "Non-negative whole numbers, bunched near zero — looks like counts "
            "(clicks, errors).",
        )
    if mn > 0 and skew > 0.7:
        return (
            OutcomeFamily.LOGNORMAL,
            "Positive values with a long right tail — typical of response/"
            "completion times.",
        )
    return (
        OutcomeFamily.GAUSSIAN,
        "Roughly symmetric continuous values — modeled as a Normal (ratings, "
        "scores).",
    )


def _classify(df: pd.DataFrame, col: str) -> dict[str, Any]:
    """First-pass description of one column (role decided later, globally)."""
    s = df[col]
    non_na = s.dropna()
    n = int(len(non_na))
    n_unique = int(non_na.nunique())
    numeric = bool(pd.api.types.is_numeric_dtype(s)) and n > 0
    info: dict[str, Any] = {
        "original": col,
        "n_unique": n_unique,
        "n_missing": int(s.isna().sum()),
        "numeric": numeric,
        "samples": None,
    }
    if numeric:
        vals = non_na.to_numpy(dtype=float)
        info["values"] = vals
        info["all_int"] = bool(np.allclose(vals, np.round(vals)))
        info["repeat"] = (n / n_unique) if n_unique else 0.0
    else:
        info["values"] = None
        info["all_int"] = False
        info["repeat"] = (n / n_unique) if n_unique else 0.0
        info["levels"] = [str(v) for v in non_na.unique().tolist()]
    return info


def _pick_grouping(infos: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Choose the participant/grouping column: by name first, else most repeated."""
    named = [i for i in infos if _PARTICIPANT_RE.search(i["original"])]
    if named:
        # the id-like column with the most distinct values among name matches
        return max(named, key=lambda i: i["n_unique"])
    # fall back to a column whose values repeat across rows (each participant
    # contributes several trials) and that isn't a binary outcome
    cands = [
        i for i in infos
        if i["n_unique"] > 1 and i["repeat"] >= 2 and i["n_unique"] > 2
    ]
    if not cands:
        return None
    return max(cands, key=lambda i: i["repeat"])


def profile_dataframe(df: pd.DataFrame) -> dict[str, Any]:
    """Profile a long-format dataframe into a suggested design + per-column report.

    Returns a dict with:
      * ``columns``: one entry per column with its suggested role, family,
        levels, a value ``samples`` array (numeric columns), and a ``reason``;
      * ``suggested_design``: a :class:`StudyDesign` dict ready to pre-fill the
        wizard;
      * ``mapping``: design canonical-name -> original CSV column.
    """
    infos = [_classify(df, c) for c in df.columns]
    grouping_info = _pick_grouping(infos)
    grouping_col = grouping_info["original"] if grouping_info else None

    taken: set[str] = set()
    columns: list[dict[str, Any]] = []
    factors: list[Factor] = []
    outcomes: list[Outcome] = []
    mapping: dict[str, str] = {}

    grouping_name = None
    if grouping_col is not None:
        grouping_name = _unique_ident(grouping_col, taken)
        mapping[grouping_name] = grouping_col

    for info in infos:
        col = info["original"]
        # Attach the histogram sample (numeric) and candidate levels (low
        # cardinality) to every column, so the UI can offer factor<->outcome
        # switches with the underlying data already on hand.
        col_levels = None
        if info["n_unique"] <= _MAX_FACTOR_LEVELS and info["n_unique"] >= 1:
            if info["numeric"]:
                col_levels = [
                    str(int(v)) if float(v).is_integer() else str(v)
                    for v in sorted(np.unique(info["values"]).tolist())
                ]
            else:
                col_levels = info["levels"]
        entry: dict[str, Any] = {
            "original": col,
            "n_unique": info["n_unique"],
            "n_missing": info["n_missing"],
            "numeric": info["numeric"],
            "samples": _samples(info["values"]) if info["numeric"] else None,
            "candidate_levels": col_levels,
            "levels": None,
            "family": None,
        }

        if col == grouping_col:
            entry["role"] = "participant"
            entry["name"] = grouping_name
            entry["reason"] = (
                "Repeated values across rows — used as the participant/grouping "
                "unit."
            )
            columns.append(entry)
            continue

        is_categorical = (
            not info["numeric"] and 2 <= info["n_unique"] <= _MAX_FACTOR_LEVELS
        ) or (
            info["numeric"] and info["all_int"] and 2 <= info["n_unique"] <= 6
            and not _OUTCOME_NAME_RE.search(col)
        )

        if is_categorical:
            name = _unique_ident(col, taken)
            mapping[name] = col
            if info["numeric"]:
                levels = [
                    str(int(v)) if float(v).is_integer() else str(v)
                    for v in sorted(np.unique(info["values"]).tolist())
                ]
                reason = (
                    f"A small set of {info['n_unique']} repeated values — treated "
                    "as a categorical factor (you can switch it to a measured "
                    "outcome)."
                )
            else:
                levels = info["levels"]
                reason = (
                    f"Text with {info['n_unique']} distinct values — a categorical "
                    "factor."
                )
            factors.append(Factor(
                name=name, label=col, kind=FactorKind.CATEGORICAL,
                role=FactorRole.WITHIN, levels=levels,
            ))
            entry.update(role="factor", name=name, levels=levels, reason=reason)
            columns.append(entry)
            continue

        if info["numeric"]:
            name = _unique_ident(col, taken)
            mapping[name] = col
            family, reason = _detect_family(info["values"])
            outcomes.append(Outcome(
                name=name, family=family, label=col,
                guess_rate=0.0, trials_per_cell=1,
            ))
            entry.update(
                role="outcome", name=name, family=family.value,
                samples=_samples(info["values"]), reason=reason,
            )
            columns.append(entry)
            continue

        # high-cardinality free text (e.g. a notes column) — ignore by default
        entry.update(
            role="ignore", name=_sanitize_ident(col),
            reason="High-cardinality text with no clear role — ignored (you can "
                   "assign it a role).",
        )
        columns.append(entry)

    design = StudyDesign(
        name="Detected from your data",
        factors=factors,
        outcomes=outcomes,
        grouping=grouping_name or "participant",
        # Start with main effects only: it fits for almost any data (no empty-cell
        # failures), and the user can opt into interactions on the Design screen,
        # where a pre-fit check guards against combinations with no data.
        interaction_order=0,
        drop_intercept=True,
        description="Design inferred from the uploaded CSV; confirm or edit below.",
    )
    return {
        "columns": columns,
        "suggested_design": design.to_dict(),
        "mapping": mapping,
    }
