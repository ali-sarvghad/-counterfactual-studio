"""Summaries of generated counterfactual data.

Produces the aggregates the paper reports -- distributions of per-participant
cell means by factor and by factor-combination, with the 50th/66th/95th
percentiles -- in a compact JSON-friendly form the frontend can chart (cf.
Figures 2, 4, 6, 7).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .spec import StudyDesign

_PCTS = [2.5, 25, 50, 66, 75, 95, 97.5]


def _pct_block(series: pd.Series) -> dict[str, float]:
    arr = series.to_numpy(dtype=float)
    out = {f"p{p:g}": float(np.percentile(arr, p)) for p in _PCTS}
    out["mean"] = float(arr.mean())
    out["n"] = int(arr.size)
    return out


def summarize(design: StudyDesign, cell_means: pd.DataFrame) -> dict[str, Any]:
    """Per-outcome summaries: overall, by each factor, and by full cell."""
    summary: dict[str, Any] = {"outcomes": {}}
    factor_names = [f.name for f in design.categorical_factors]
    for o in design.outcomes:
        if o.name not in cell_means.columns:
            continue
        block: dict[str, Any] = {"overall": _pct_block(cell_means[o.name])}
        by_factor: dict[str, Any] = {}
        for fn in factor_names:
            rows = []
            for level, grp in cell_means.groupby(fn, observed=True):
                rows.append({"level": str(level), **_pct_block(grp[o.name])})
            rows.sort(key=lambda r: r["p50"],
                      reverse=(o.name == "accuracy"))  # best-first heuristic
            by_factor[fn] = rows
        block["by_factor"] = by_factor

        # full-cell medians (one number per factor combination)
        cell_rows = []
        for keys, grp in cell_means.groupby(factor_names, observed=True):
            keys = keys if isinstance(keys, tuple) else (keys,)
            cell_rows.append({**{fn: str(k) for fn, k in zip(factor_names, keys)},
                              "median": float(grp[o.name].median())})
        block["by_cell"] = cell_rows
        summary["outcomes"][o.name] = block
    return summary
