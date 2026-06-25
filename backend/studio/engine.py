"""The Bayesian engine: build models, fit data, and generate counterfactuals.

This module turns a :class:`~studio.spec.StudyDesign` into runnable Bambi/PyMC
models and implements the paper's counterfactual-participant approach.

Two paths converge on the same trial-level + cell-mean output:

* **Data path** -- fit the model to a researcher's pilot/study data, then read
  the posterior. With ``sample_new_groups=True`` each posterior draw yields one
  *new* participant whose cell means already include a freshly-sampled
  participant random effect; N draws give N heterogeneous counterfactuals,
  exactly as in the paper (12,000 draws -> 12,000 counterfactual participants).

* **Assumptions path** -- no data: the researcher states expected cell means (in
  natural units) plus a between-participant spread, and we forward-simulate the
  same generative structure directly with NumPy.

Lognormal outcomes are fit as a Gaussian on ``log(outcome)`` (Bambi has no
lognormal family); we exponentiate when generating. The emitted brms script
uses a native ``lognormal()`` family, which is mathematically equivalent.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from itertools import product
from typing import Any, Callable

import numpy as np
import pandas as pd

from .formula import build_formula, FormulaParts
from .spec import (
    Factor,
    FactorKind,
    Outcome,
    OutcomeFamily,
    StudyDesign,
)

# Bambi/PyMC are imported lazily so that the pure-python parts of the package
# (spec, templates, formula) stay usable without the heavy stats stack.

# The posterior data variable that holds the per-observation mean, by family.
_PARENT_PARAM = {
    OutcomeFamily.BERNOULLI: "p",
    OutcomeFamily.GAUSSIAN: "mu",
    OutcomeFamily.LOGNORMAL: "mu",   # fit as gaussian on log scale
    OutcomeFamily.POISSON: "mu",
}


# --------------------------------------------------------------------------- #
# Families & links
# --------------------------------------------------------------------------- #
def _chance_corrected_bernoulli(guess: float):
    """A Bernoulli family whose success probability cannot fall below ``guess``.

    Implements the paper's p = g + (1 - g) * inv_logit(eta), with g = 0.25 for a
    4-alternative forced choice, via a custom Bambi link.
    """
    import bambi as bmb
    import pytensor.tensor as pt
    from scipy.special import expit, logit

    g = float(guess)

    def linkinv(eta):
        return g + (1.0 - g) * expit(np.asarray(eta))

    def link(mu):
        mu = np.asarray(mu)
        return logit(np.clip((mu - g) / (1.0 - g), 1e-6, 1 - 1e-6))

    def linkinv_backend(eta):
        return g + (1.0 - g) * pt.sigmoid(eta)

    custom = bmb.Link(
        f"chance{int(round(g * 100))}",
        link=link,
        linkinv=linkinv,
        linkinv_backend=linkinv_backend,
    )
    return bmb.Family(
        "chance_bernoulli",
        likelihood=bmb.Likelihood("Bernoulli", parent="p"),
        link={"p": custom},
    )


def family_for(outcome: Outcome):
    """Return the Bambi family object (or family-name string) for an outcome."""
    if outcome.family == OutcomeFamily.BERNOULLI and outcome.guess_rate > 0:
        return _chance_corrected_bernoulli(outcome.guess_rate)
    # Lognormal is fit as gaussian on the log-transformed response.
    if outcome.family in (OutcomeFamily.LOGNORMAL, OutcomeFamily.GAUSSIAN):
        return "gaussian"
    return outcome.family.value


# --------------------------------------------------------------------------- #
# Data preparation
# --------------------------------------------------------------------------- #
def prepare_data(design: StudyDesign, df: pd.DataFrame) -> pd.DataFrame:
    """Cast factor columns to categoricals and add log columns for lognormal."""
    out = df.copy()
    for f in design.categorical_factors:
        if f.name in out.columns:
            out[f.name] = pd.Categorical(
                out[f.name].astype(str),
                categories=[str(l) for l in f.levels],
            )
    if design.grouping in out.columns:
        out[design.grouping] = pd.Categorical(out[design.grouping].astype(str))
    for o in design.outcomes:
        if o.family == OutcomeFamily.LOGNORMAL and o.name in out.columns:
            vals = pd.to_numeric(out[o.name], errors="coerce")
            if (vals <= 0).any():
                raise ValueError(
                    f"Lognormal outcome {o.name!r} requires strictly positive "
                    "values; found zero or negative entries."
                )
            out[f"log_{o.name}"] = np.log(vals)
    return out


def cell_grid(design: StudyDesign) -> pd.DataFrame:
    """Every combination of categorical factor levels (one row per cell).

    Counterfactual participants are given data for *all* cells, regardless of
    the within/between split that constrained the real study.
    """
    cats = design.categorical_factors
    combos = product(*[f.levels for f in cats])
    rows = [{f.name: lvl for f, lvl in zip(cats, combo)} for combo in combos]
    grid = pd.DataFrame(rows)
    for f in cats:
        grid[f.name] = pd.Categorical(grid[f.name].astype(str),
                                      categories=[str(l) for l in f.levels])
    return grid


# --------------------------------------------------------------------------- #
# Fitting (data path)
# --------------------------------------------------------------------------- #
@dataclass
class OutcomeFit:
    outcome: Outcome
    parts: FormulaParts
    model: Any                       # bambi.Model
    idata: Any                       # arviz.InferenceData
    diagnostics: dict[str, Any]


@dataclass
class FitBundle:
    design: StudyDesign
    data: pd.DataFrame
    fits: dict[str, OutcomeFit] = field(default_factory=dict)


def _diagnostics(idata) -> dict[str, Any]:
    import arviz as az

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        rhat = az.rhat(idata).to_array()
        ess = az.ess(idata).to_array()
    n_div = int(idata.sample_stats["diverging"].sum()) if "sample_stats" in idata else 0
    max_rhat = float(rhat.max())
    min_ess = float(ess.min())
    if max_rhat <= 1.01 and n_div == 0:
        status = "good"
    elif max_rhat <= 1.05:
        status = "warn"
    else:
        status = "bad"
    return {
        "max_rhat": max_rhat,
        "min_ess_bulk": min_ess,
        "n_divergences": n_div,
        "status": status,
        "interpretation": _diag_message(status, max_rhat, min_ess, n_div),
    }


def _diag_message(status, max_rhat, min_ess, n_div) -> str:
    if status == "good":
        return (
            f"Healthy: R-hat = {max_rhat:.3f} (<= 1.01) and no divergences. "
            "The chains converged and the estimates are trustworthy."
        )
    if status == "warn":
        return (
            f"Borderline: R-hat = {max_rhat:.3f} and {n_div} divergence(s). "
            "Consider more tuning/draws or tighter priors before relying on it."
        )
    return (
        f"Problematic: R-hat = {max_rhat:.3f} indicates the chains disagree. "
        "Increase draws/tuning, simplify the model, or use more informative priors."
    )


def build_model(design: StudyDesign, outcome: Outcome, data: pd.DataFrame,
                priors: dict | None = None):
    import bambi as bmb

    parts = build_formula(design, outcome)
    model = bmb.Model(
        parts.bambi_formula,
        data,
        family=family_for(outcome),
        priors=priors or None,
    )
    return model, parts


def fit(design: StudyDesign, df: pd.DataFrame, *,
        priors: dict | None = None,
        draws: int = 1000, tune: int = 1000, chains: int = 4,
        cores: int = 1, seed: int = 1234,
        target_accept: float = 0.9,
        progressbar: bool = False) -> FitBundle:
    """Fit one model per outcome to the supplied data."""
    design.validate()
    data = prepare_data(design, df)
    bundle = FitBundle(design=design, data=data)
    for outcome in design.outcomes:
        model, parts = build_model(design, outcome, data,
                                   (priors or {}).get(outcome.name))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            idata = model.fit(draws=draws, tune=tune, chains=chains, cores=cores,
                              random_seed=seed, target_accept=target_accept,
                              progressbar=progressbar)
        bundle.fits[outcome.name] = OutcomeFit(
            outcome=outcome, parts=parts, model=model, idata=idata,
            diagnostics=_diagnostics(idata),
        )
    return bundle


# --------------------------------------------------------------------------- #
# Counterfactual generation -- data path
# --------------------------------------------------------------------------- #
@dataclass
class GenerationResult:
    cell_means: pd.DataFrame       # one row per (participant, cell)
    trials: pd.DataFrame           # one row per simulated trial
    n_participants: int
    source: str                    # "posterior" or "assumptions"


def _posterior_cell_draws(fit: OutcomeFit, design: StudyDesign):
    """All posterior draws of the per-cell mean for a brand-new participant.

    Returns ``(means, sigma, cells_df)`` where ``means`` has shape
    (n_draws, n_cells) on the model's link scale (the parent parameter), and
    ``sigma`` is (n_draws,) for continuous families or ``None``. Each draw row
    is one heterogeneous counterfactual participant (population effect + a
    freshly-sampled participant random effect, via ``sample_new_groups``).
    """
    grid = cell_grid(design).copy()
    grid[design.grouping] = pd.Categorical(["__cf__"] * len(grid))
    param = _PARENT_PARAM[fit.outcome.family]

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fit.model.predict(fit.idata, data=grid, sample_new_groups=True,
                          kind="response_params", inplace=True)

    arr = fit.idata.posterior[param]              # (chain, draw, obs)
    stacked = arr.stack(sample=("chain", "draw")).transpose("sample", arr.dims[-1])
    means = np.asarray(stacked.values)            # (n_draws, n_cells)

    sigma = None
    if fit.outcome.family in (OutcomeFamily.LOGNORMAL, OutcomeFamily.GAUSSIAN):
        sigma = np.asarray(
            fit.idata.posterior["sigma"].stack(sample=("chain", "draw")).values
        )
    return means, sigma, grid.drop(columns=[design.grouping])


def posterior_draws(bundle: FitBundle) -> dict[str, Any]:
    """Extract a serializable cache of posterior cell-mean draws from a fit.

    This is computed once after fitting so that counterfactual generation needs
    only NumPy arrays -- the (heavy, version-sensitive) Bambi model and
    InferenceData can be discarded afterwards.
    """
    out: dict[str, Any] = {"grouping": bundle.design.grouping, "outcomes": {}}
    for name, fit in bundle.fits.items():
        means, sigma, _ = _posterior_cell_draws(fit, bundle.design)
        out["outcomes"][name] = {
            "family": fit.outcome.family.value,
            "guess_rate": fit.outcome.guess_rate,
            "trials_per_cell": fit.outcome.trials_per_cell,
            "raw": means,            # (n_draws, n_cells), link scale
            "sigma": sigma,          # (n_draws,) or None
        }
    return out


def _subsample(n_draws: int, n: int, rng: np.random.Generator) -> np.ndarray:
    if n == n_draws:
        return np.arange(n_draws)
    return rng.integers(0, n_draws, size=n)


def generate_from_draws(design: StudyDesign, draws: dict[str, Any],
                        n_participants: int = 2000, seed: int = 7
                        ) -> GenerationResult:
    """Generate counterfactuals from a cached posterior-draws dict.

    ``draws`` is the structure returned by :func:`posterior_draws`. Each
    counterfactual participant is one (sub)sampled posterior draw.
    """
    rng = np.random.default_rng(seed)
    base_grid = cell_grid(design)
    specs: list[dict] = []
    for outcome in design.outcomes:
        cache = draws["outcomes"][outcome.name]
        means_all = np.asarray(cache["raw"])
        sigma_all = cache["sigma"]
        sigma_all = None if sigma_all is None else np.asarray(sigma_all)
        idx = _subsample(means_all.shape[0], n_participants, rng)
        means = means_all[idx]
        sigma = None if sigma_all is None else sigma_all[idx]
        if outcome.family == OutcomeFamily.LOGNORMAL:
            s2 = (sigma ** 2)[:, None] if sigma is not None else 0.0
            natural = np.exp(means + s2 / 2.0)
        else:
            natural = means
        specs.append({"outcome": outcome, "raw": means,
                      "natural": natural, "sigma": sigma})

    cm = _cell_means_frame(design, base_grid, specs, n_participants)
    trials = _expand_trials_combined(design, specs, base_grid, n_participants, rng)
    return GenerationResult(cell_means=cm, trials=trials,
                            n_participants=n_participants, source="posterior")


def generate_from_fit(bundle: FitBundle, n_participants: int = 2000,
                      seed: int = 7) -> GenerationResult:
    """Convenience wrapper: extract posterior draws from a live fit and generate."""
    return generate_from_draws(bundle.design, posterior_draws(bundle),
                               n_participants, seed)


def _cell_means_frame(design, base_grid, specs, n_participants) -> pd.DataFrame:
    """One row per (participant, cell) with the natural-unit mean per outcome."""
    n_cells = len(base_grid)
    pid = np.repeat(np.arange(n_participants), n_cells)
    cm = pd.concat([base_grid] * n_participants, ignore_index=True)
    cm.insert(0, design.grouping, [f"cf{p:05d}" for p in pid])
    for s in specs:
        cm[s["outcome"].name] = s["natural"].reshape(-1)
    return cm


def _sigma_for(sigma, p):
    if sigma is None:
        return None
    return sigma[p] if hasattr(sigma, "__len__") else sigma


def _expand_trials_combined(design, specs, base_grid, n_participants,
                            rng) -> pd.DataFrame:
    """Trial-level data with *all* outcomes on the same row (as in Table 3).

    Each simulated trial (a question) yields a value for every outcome, drawn
    independently from its likelihood (the paper modeled accuracy and time with
    separate models, so independent draws are consistent with its method). When
    outcomes declare different ``trials_per_cell``, rows beyond a given outcome's
    count carry NaN for that outcome.
    """
    n_cells = len(base_grid)
    grid_rows = [base_grid.iloc[ci].to_dict() for ci in range(n_cells)]
    k_max = max(s["outcome"].trials_per_cell for s in specs)
    blocks = []
    for p in range(n_participants):
        pid = f"cf{p:05d}"
        for ci in range(n_cells):
            drawn = {}
            for s in specs:
                o = s["outcome"]
                drawn[o.name] = _draw_trials(
                    o, s["raw"][p, ci], s["natural"][p, ci],
                    _sigma_for(s["sigma"], p), o.trials_per_cell, rng)
            base = grid_rows[ci]
            for r in range(k_max):
                row = {design.grouping: pid, **base}
                for s in specs:
                    vals = drawn[s["outcome"].name]
                    row[s["outcome"].name] = vals[r] if r < len(vals) else float("nan")
                blocks.append(row)
    return pd.DataFrame(blocks)


def _draw_trials(outcome: Outcome, raw_mean: float, natural_mean: float,
                 sigma: float | None, k: int, rng: np.random.Generator):
    fam = outcome.family
    if fam == OutcomeFamily.BERNOULLI:
        p = float(np.clip(natural_mean, 0.0, 1.0))
        return rng.binomial(1, p, size=k).tolist()
    if fam == OutcomeFamily.LOGNORMAL:
        # raw_mean is mu on the log scale.
        return np.exp(rng.normal(raw_mean, sigma if sigma else 0.0, size=k)).tolist()
    if fam == OutcomeFamily.GAUSSIAN:
        return rng.normal(natural_mean, sigma if sigma else 0.0, size=k).tolist()
    if fam == OutcomeFamily.POISSON:
        return rng.poisson(max(natural_mean, 0.0), size=k).tolist()
    raise ValueError(f"Unsupported family {fam}")


# --------------------------------------------------------------------------- #
# Counterfactual generation -- assumptions path (no data, pure forward sim)
# --------------------------------------------------------------------------- #
def _link_to_eta(outcome: Outcome, mean: float) -> float:
    fam = outcome.family
    if fam == OutcomeFamily.BERNOULLI:
        from scipy.special import logit
        g = outcome.guess_rate
        m = np.clip((mean - g) / (1 - g), 1e-6, 1 - 1e-6) if g else np.clip(mean, 1e-6, 1 - 1e-6)
        return float(logit(m))
    if fam == OutcomeFamily.LOGNORMAL:
        return float(np.log(mean))      # eta on log scale = median
    if fam == OutcomeFamily.POISSON:
        return float(np.log(max(mean, 1e-9)))
    return float(mean)                  # gaussian identity


def _eta_to_natural(outcome: Outcome, eta: np.ndarray) -> np.ndarray:
    fam = outcome.family
    if fam == OutcomeFamily.BERNOULLI:
        from scipy.special import expit
        g = outcome.guess_rate
        return g + (1 - g) * expit(eta) if g else expit(eta)
    if fam in (OutcomeFamily.LOGNORMAL, OutcomeFamily.POISSON):
        return np.exp(eta)
    return eta


@dataclass
class Assumptions:
    """Researcher-supplied generative parameters for the no-data path.

    ``cell_means[outcome][cell_key]`` is the expected outcome in natural units
    (probability for Bernoulli, seconds for lognormal time, ...). ``between_sd``
    is the participant-to-participant spread on the link scale, and
    ``residual_sd`` is the within-participant noise scale (sigma) for continuous
    families.
    """

    cell_means: dict[str, dict[str, float]]
    between_sd: dict[str, float] = field(default_factory=dict)
    residual_sd: dict[str, float] = field(default_factory=dict)


def cell_key(design: StudyDesign, row: dict) -> str:
    return "|".join(f"{f.name}={row[f.name]}" for f in design.categorical_factors)


def generate_from_assumptions(design: StudyDesign, assumptions: Assumptions,
                              n_participants: int = 2000,
                              seed: int = 7) -> GenerationResult:
    design.validate()
    rng = np.random.default_rng(seed)
    grid = cell_grid(design)
    n_cells = len(grid)
    keys = [cell_key(design, grid.iloc[i].to_dict()) for i in range(n_cells)]

    specs: list[dict] = []
    for o in design.outcomes:
        means = assumptions.cell_means.get(o.name, {})
        eta0 = np.array([_link_to_eta(o, means.get(k, _default_mean(o))) for k in keys])
        bsd = float(assumptions.between_sd.get(o.name, 0.3))
        # One participant offset per participant, shared across cells (v1).
        offsets = rng.normal(0.0, bsd, size=n_participants)
        eta = eta0[None, :] + offsets[:, None]          # (n_participants, n_cells)
        natural = _eta_to_natural(o, eta)
        rsd = float(assumptions.residual_sd.get(o.name, 0.3))
        specs.append({"outcome": o, "raw": eta, "natural": natural, "sigma": rsd})

    cm = _cell_means_frame(design, grid, specs, n_participants)
    trials = _expand_trials_combined(design, specs, grid, n_participants, rng)
    return GenerationResult(
        cell_means=cm, trials=trials,
        n_participants=n_participants, source="assumptions",
    )


def _default_mean(outcome: Outcome) -> float:
    return {
        OutcomeFamily.BERNOULLI: 0.7,
        OutcomeFamily.LOGNORMAL: 20.0,
        OutcomeFamily.GAUSSIAN: 0.0,
        OutcomeFamily.POISSON: 5.0,
    }[outcome.family]
