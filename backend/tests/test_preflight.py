"""Tests for the pre-fit sanity checks."""

import pandas as pd

from studio.preflight import preflight
from studio.spec import Factor, FactorKind, FactorRole, Outcome, OutcomeFamily, StudyDesign


def _design(interaction_order):
    return StudyDesign(
        name="t",
        grouping="participant",
        interaction_order=interaction_order,
        factors=[
            Factor(name="age", kind=FactorKind.CATEGORICAL, role=FactorRole.BETWEEN,
                   levels=["young", "old"]),
            Factor(name="lit", kind=FactorKind.CATEGORICAL, role=FactorRole.BETWEEN,
                   levels=["low", "mid", "high"]),
        ],
        outcomes=[Outcome(name="count", family=OutcomeFamily.POISSON)],
    )


def _df_with_empty_cell():
    # every age x lit combo EXCEPT (old, high) -> one empty cell
    rows = []
    for age in ["young", "old"]:
        for lit in ["low", "mid", "high"]:
            if age == "old" and lit == "high":
                continue
            rows += [{"participant": f"{age}{lit}{i}", "age": age, "lit": lit,
                      "count": 3} for i in range(4)]
    return pd.DataFrame(rows)


def test_full_interaction_flags_empty_cell_as_error():
    res = preflight(_design(None), _df_with_empty_cell())
    assert res["ok"] is False
    err = [i for i in res["issues"] if i["id"] == "empty_cells"]
    assert err and err[0]["severity"] == "error"
    assert "old=old, lit=high" in err[0]["detail"] or "lit=high" in err[0]["detail"]
    # recommends and offers a one-click switch to main effects
    assert res["recommended_interaction_order"] == 0
    assert err[0]["fix"]["value"] == 0


def test_main_effects_has_no_empty_cell_error():
    res = preflight(_design(0), _df_with_empty_cell())
    assert res["ok"] is True
    assert not any(i["id"] == "empty_cells" for i in res["issues"])


def test_sparse_level_warns():
    rows = [{"participant": f"p{i}", "age": "young", "lit": "low", "count": 2}
            for i in range(10)]
    rows.append({"participant": "solo", "age": "old", "lit": "mid", "count": 1})
    res = preflight(_design(0), pd.DataFrame(rows))
    assert any(i["id"] == "sparse_levels" and i["severity"] == "warning"
               for i in res["issues"])
