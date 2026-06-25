"""Tests for the core engine.

The fast tests (spec, formula, templates, assumptions-path generation, and the
exporters) need no MCMC and run in well under a second. The single integration
test that fits a real model is marked ``slow`` and is skipped unless bambi is
installed and ``--run-slow`` is passed.
"""

import math

import numpy as np
import pandas as pd
import pytest

from studio import engine
from studio.engine import Assumptions, cell_grid, cell_key
from studio.export import (
    bambi_script,
    brms_script,
    design_to_json,
    reproducibility_report,
)
from studio.formula import build_formula, brms_formula
from studio.spec import (
    Factor,
    FactorKind,
    FactorRole,
    Outcome,
    OutcomeFamily,
    SpecError,
    StudyDesign,
)
from studio.templates import get_template, paper_design


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
def small_design() -> StudyDesign:
    return StudyDesign(
        name="Small",
        grouping="participant",
        factors=[
            Factor("vis", role=FactorRole.WITHIN, levels=["Bar", "Line", "Table"]),
            Factor("task", role=FactorRole.BETWEEN, levels=["Filter", "Order"]),
            Factor("age", role=FactorRole.BETWEEN, levels=["YA", "PLA"]),
        ],
        outcomes=[
            Outcome("accuracy", family=OutcomeFamily.BERNOULLI, guess_rate=0.25,
                    trials_per_cell=3),
            Outcome("time", family=OutcomeFamily.LOGNORMAL, trials_per_cell=3),
        ],
    )


# --------------------------------------------------------------------------- #
# Spec
# --------------------------------------------------------------------------- #
def test_spec_validates_and_counts_cells():
    d = small_design()
    d.validate()
    assert d.n_cells() == 3 * 2 * 2
    assert [f.name for f in d.within_factors] == ["vis"]
    assert {f.name for f in d.between_factors} == {"task", "age"}


def test_spec_rejects_bad_names_and_levels():
    with pytest.raises(SpecError):
        Factor("2bad", levels=["a", "b"]).validate()
    with pytest.raises(SpecError):
        Factor("x", levels=["only"]).validate()
    with pytest.raises(SpecError):
        Outcome("acc", family=OutcomeFamily.GAUSSIAN, guess_rate=0.25).validate()


def test_spec_json_roundtrip():
    d = paper_design()
    d2 = StudyDesign.from_dict(d.to_dict())
    assert d2.to_dict() == d.to_dict()
    assert d2.n_cells() == 5 * 10 * 2


# --------------------------------------------------------------------------- #
# Formula
# --------------------------------------------------------------------------- #
def test_formula_full_interaction_is_cell_means():
    d = small_design()
    acc = build_formula(d, d.outcomes[0])
    assert acc.bambi_formula == "accuracy ~ 0 + vis:task:age + (0 + vis | participant)"
    # lognormal fits gaussian on log_<name>
    tim = build_formula(d, d.outcomes[1])
    assert tim.bambi_formula.startswith("log_time ~ 0 + vis:task:age")
    assert tim.needs_log_transform and tim.bambi_family == "gaussian"


def test_formula_interaction_order_and_brms():
    d = small_design()
    d.interaction_order = 1  # main effects only
    f = build_formula(d, d.outcomes[0]).fixed
    assert f == "0 + vis + task + age"
    assert brms_formula(d, d.outcomes[1]) == \
        "time ~ 0 + vis + task + age + (0 + vis | participant)"


def test_between_only_design_uses_intercept_or_none():
    d = StudyDesign(
        name="b", grouping="p",
        factors=[Factor("g", role=FactorRole.BETWEEN, levels=["a", "b"])],
        outcomes=[Outcome("y", family=OutcomeFamily.GAUSSIAN, trials_per_cell=4)],
    )
    # repeated measures (trials>1) -> varying intercept
    assert "(1 | p)" in build_formula(d, d.outcomes[0]).bambi_formula


# --------------------------------------------------------------------------- #
# Templates
# --------------------------------------------------------------------------- #
def test_paper_template_matches_paper():
    d = get_template("paper")
    assert d.n_cells() == 100
    acc = next(o for o in d.outcomes if o.name == "accuracy")
    assert acc.guess_rate == 0.25 and acc.trials_per_cell == 6
    assert {f.name: f.role.value for f in d.factors} == {
        "vis": "within", "task": "between", "age": "between"}


# --------------------------------------------------------------------------- #
# Assumptions path (no MCMC)
# --------------------------------------------------------------------------- #
def test_generate_from_assumptions_shapes_and_floor():
    d = small_design()
    grid = cell_grid(d)
    keys = [cell_key(d, grid.iloc[i].to_dict()) for i in range(len(grid))]
    acc = {k: (0.9 if "Table" in k else 0.6) for k in keys}
    tim = {k: (15.0 if "YA" in k else 25.0) for k in keys}
    a = Assumptions(cell_means={"accuracy": acc, "time": tim},
                    between_sd={"accuracy": 0.4, "time": 0.2},
                    residual_sd={"time": 0.3})
    res = engine.generate_from_assumptions(d, a, n_participants=30, seed=1)

    assert res.source == "assumptions"
    assert len(res.cell_means) == 30 * d.n_cells()
    assert len(res.trials) == 30 * d.n_cells() * 3  # k_max
    # chance floor respected
    assert res.cell_means["accuracy"].min() >= 0.25 - 1e-9
    # both outcomes present on every trial row, no stray NaN
    assert res.trials[["accuracy", "time"]].notna().all().all()
    assert set(res.trials["accuracy"].unique()) <= {0, 1}
    assert (res.trials["time"] > 0).all()
    # Table cells should average higher accuracy than non-Table
    cm = res.cell_means
    table_acc = cm[cm["vis"] == "Table"]["accuracy"].mean()
    other_acc = cm[cm["vis"] != "Table"]["accuracy"].mean()
    assert table_acc > other_acc


def test_link_inversion_roundtrip():
    o = Outcome("acc", family=OutcomeFamily.BERNOULLI, guess_rate=0.25)
    for p in (0.3, 0.5, 0.8):
        eta = engine._link_to_eta(o, p)
        back = float(engine._eta_to_natural(o, np.array([eta]))[0])
        assert math.isclose(back, p, rel_tol=1e-6)


# --------------------------------------------------------------------------- #
# Exporters
# --------------------------------------------------------------------------- #
def test_exporters_emit_expected_content():
    d = paper_design()
    rep = reproducibility_report(d, source="assumptions", n_participants=12000, seed=7)
    assert "Reproducibility report" in rep and "brms formula" in rep
    bs = bambi_script(d)
    assert "bmb.Model" in bs and "chance_bernoulli" in bs  # guess-rate snippet
    rs = brms_script(d)
    assert "lognormal()" in rs and "brm(" in rs
    import json
    parsed = json.loads(design_to_json(d))  # valid, round-trippable JSON
    assert parsed["grouping"] == "participant"
    assert any(o["family"] == "bernoulli" for o in parsed["outcomes"])


# --------------------------------------------------------------------------- #
# Integration (slow): real fit + posterior counterfactuals
# --------------------------------------------------------------------------- #
@pytest.mark.slow
def test_fit_and_generate_from_posterior():
    bmb = pytest.importorskip("bambi")
    d = small_design()
    rng = np.random.default_rng(0)
    rows = []
    for p in range(24):
        ag = ["YA", "PLA"][p % 2]
        tk = ["Filter", "Order"][(p // 2) % 2]
        for v in ["Bar", "Line", "Table"]:
            for _ in range(3):
                bonus = 0.2 if v == "Table" else 0.0
                rows.append(dict(participant=f"u{p}", vis=v, task=tk, age=ag,
                                 accuracy=int(rng.random() < 0.55 + bonus),
                                 time=float(np.exp(2 + rng.normal(0, 0.3)))))
    df = pd.DataFrame(rows)
    bundle = engine.fit(d, df, draws=150, tune=150, chains=2, seed=1)
    assert set(bundle.fits) == {"accuracy", "time"}
    res = engine.generate_from_fit(bundle, n_participants=25, seed=2)
    assert len(res.cell_means) == 25 * d.n_cells()
    assert res.cell_means["accuracy"].min() >= 0.25 - 1e-9
    assert (res.cell_means["time"] > 0).all()
    assert res.trials[["accuracy", "time"]].notna().all().all()
