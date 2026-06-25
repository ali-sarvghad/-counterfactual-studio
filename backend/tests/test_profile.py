"""Tests for automatic dataset profiling (upload-first flow)."""

import numpy as np
import pandas as pd

from studio.profile import profile_dataframe
from studio.spec import StudyDesign


def _sample_df(n_participants: int = 40) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    rows = []
    for p in range(n_participants):
        for vis in ["Bar", "Line", "Pie"]:
            rows.append({
                "participant": f"P{p:03d}",
                "vis": vis,
                "correct": int(rng.random() < 0.7),
                "rt": float(np.exp(rng.normal(0.5, 0.4))),  # positive, skewed
                "errors": int(rng.poisson(1.5)),
            })
    return pd.DataFrame(rows)


def _roles(profile):
    return {c["original"]: c["role"] for c in profile["columns"]}


def test_detects_participant_factor_and_outcomes():
    prof = profile_dataframe(_sample_df())
    roles = _roles(prof)
    assert roles["participant"] == "participant"
    assert roles["vis"] == "factor"
    assert roles["correct"] == "outcome"
    assert roles["rt"] == "outcome"


def test_detects_families_from_shape():
    prof = profile_dataframe(_sample_df())
    fam = {c["original"]: c.get("family") for c in prof["columns"]}
    assert fam["correct"] == "bernoulli"   # only 0/1
    assert fam["rt"] == "lognormal"        # positive & right-skewed
    assert fam["errors"] == "poisson"      # small non-negative counts


def test_suggested_design_is_valid_and_round_trips():
    prof = profile_dataframe(_sample_df())
    design = StudyDesign.from_dict(prof["suggested_design"])
    design.validate()  # raises if the inferred design is internally inconsistent
    assert design.grouping == "participant"
    assert {f.name for f in design.factors} == {"vis"}
    assert {o.name for o in design.outcomes} == {"correct", "rt", "errors"}


def test_mapping_covers_every_design_name():
    prof = profile_dataframe(_sample_df())
    design = StudyDesign.from_dict(prof["suggested_design"])
    names = [design.grouping] + [f.name for f in design.factors] + \
            [o.name for o in design.outcomes]
    for n in names:
        assert n in prof["mapping"]


def test_sanitizes_non_identifier_column_names():
    df = pd.DataFrame({
        "Subject ID": ["a", "a", "b", "b"],
        "Chart Type": ["Bar", "Pie", "Bar", "Pie"],
        "Response Time (s)": [1.2, 2.3, 0.9, 3.1],
    })
    prof = profile_dataframe(df)
    design = StudyDesign.from_dict(prof["suggested_design"])
    design.validate()
    # canonical names are valid identifiers, mapped back to the raw headers
    assert all(name.isidentifier() for name in prof["mapping"])
    assert set(prof["mapping"].values()) <= set(df.columns)
