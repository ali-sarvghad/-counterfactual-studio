"""Optional data preprocessing, mirroring the paper's pipeline.

The paper applied a Hampel filter (median +/- k * MAD) to the time data within
each age x task x visualization cell, removing 1.6% of trials with extreme
response times before modeling. We generalize that: filter any continuous /
lognormal outcome within each combination of categorical factor levels.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .spec import OutcomeFamily, StudyDesign

_MAD_TO_STD = 1.4826  # makes MAD a consistent estimator of the std for normals


def hampel_filter(design: StudyDesign, df: pd.DataFrame,
                  n_mad: float = 3.0) -> tuple[pd.DataFrame, dict]:
    """Drop rows whose continuous outcome is > ``n_mad`` MADs from the cell median.

    Returns the filtered frame and a small report (counts per outcome).
    """
    cont = [o for o in design.outcomes
            if o.family in (OutcomeFamily.LOGNORMAL, OutcomeFamily.GAUSSIAN, OutcomeFamily.POISSON)]
    if not cont:
        return df, {"removed": 0, "per_outcome": {}}

    group_cols = [f.name for f in design.categorical_factors if f.name in df.columns]
    keep = pd.Series(True, index=df.index)
    per_outcome: dict[str, int] = {}
    for o in cont:
        if o.name not in df.columns:
            continue
        vals = pd.to_numeric(df[o.name], errors="coerce")
        flagged = pd.Series(False, index=df.index)
        groups = (df.groupby(group_cols, observed=True).indices
                  if group_cols else {None: df.index.to_numpy()})
        for idx in groups.values():
            v = vals.iloc[idx] if group_cols else vals
            med = v.median()
            mad = (v - med).abs().median() * _MAD_TO_STD
            if mad == 0 or np.isnan(mad):
                continue
            flagged.iloc[idx if group_cols else slice(None)] = \
                ((v - med).abs() > n_mad * mad).to_numpy()
        per_outcome[o.name] = int(flagged.sum())
        keep &= ~flagged
    filtered = df[keep].reset_index(drop=True)
    return filtered, {"removed": int((~keep).sum()), "per_outcome": per_outcome,
                      "n_mad": n_mad, "remaining": int(len(filtered))}
