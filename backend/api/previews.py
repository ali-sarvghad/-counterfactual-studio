"""Cheap, analytic "what does this choice imply?" previews for the wizard.

These let the UI show, in real time and without any MCMC, the consequence of a
researcher's decisions -- mirroring the paper's own reasoning (e.g. a Normal(0,1)
prior on the logit implies 95% of mean accuracies fall in [0.34, 0.91]).
"""

from __future__ import annotations

import numpy as np
from scipy.special import expit, logit

from studio.spec import OutcomeFamily


_Z = {"p2.5": -1.959964, "p25": -0.674490, "p50": 0.0,
      "p75": 0.674490, "p97.5": 1.959964}


def _natural_from_eta(family: str, guess: float, eta: np.ndarray) -> np.ndarray:
    fam = OutcomeFamily(family)
    if fam == OutcomeFamily.BERNOULLI:
        return guess + (1 - guess) * expit(eta) if guess else expit(eta)
    if fam in (OutcomeFamily.LOGNORMAL, OutcomeFamily.POISSON):
        return np.exp(eta)
    return eta


def _eta_from_mean(family: str, guess: float, mean: float) -> float:
    fam = OutcomeFamily(family)
    if fam == OutcomeFamily.BERNOULLI:
        m = (mean - guess) / (1 - guess) if guess else mean
        return float(logit(np.clip(m, 1e-6, 1 - 1e-6)))
    if fam in (OutcomeFamily.LOGNORMAL, OutcomeFamily.POISSON):
        return float(np.log(max(mean, 1e-9)))
    return float(mean)


def _fmt(family: str, x: float) -> str:
    fam = OutcomeFamily(family)
    if fam == OutcomeFamily.BERNOULLI:
        return f"{x:.0%}"
    if fam == OutcomeFamily.LOGNORMAL:
        return f"{x:.1f}s"
    return f"{x:.2f}"


def outcome_implications(family: str, guess_rate: float, mean: float,
                         between_sd: float, n_samples: int = 400) -> dict:
    """How a target cell mean + between-participant SD spreads across people.

    The spread (``between_sd``) lives on the model's link scale; we map the
    Normal(eta0, sd) of participant effects through the inverse link to show the
    implied distribution of *participant* cell means in natural units.
    """
    eta0 = _eta_from_mean(family, guess_rate, mean)
    pct = {name: float(_natural_from_eta(family, guess_rate, eta0 + z * between_sd))
           for name, z in _Z.items()}
    rng = np.random.default_rng(0)
    samples = _natural_from_eta(
        family, guess_rate, rng.normal(eta0, between_sd, size=n_samples))
    lo, hi = pct["p2.5"], pct["p97.5"]
    explanation = (
        f"With a target of {_fmt(family, mean)} and a between-participant spread "
        f"of {between_sd:g} (link scale), about 95% of simulated participants "
        f"land between {_fmt(family, lo)} and {_fmt(family, hi)}. "
        "Larger spread = more heterogeneous participants."
    )
    return {"percentiles": pct, "samples": samples.tolist(),
            "explanation": explanation}


def prior_implications(family: str, guess_rate: float, prior_mean: float,
                       prior_sd: float, n_samples: int = 400) -> dict:
    """What a prior on the (link-scale) coefficient implies for the outcome.

    This reproduces the paper's prior-justification reasoning so a researcher can
    feel out a weakly-informed prior before committing to a fit.
    """
    pct = {name: float(_natural_from_eta(family, guess_rate, prior_mean + z * prior_sd))
           for name, z in _Z.items()}
    rng = np.random.default_rng(1)
    samples = _natural_from_eta(
        family, guess_rate, rng.normal(prior_mean, prior_sd, size=n_samples))
    lo, hi = pct["p2.5"], pct["p97.5"]
    fam = OutcomeFamily(family)
    link = "logit" if fam == OutcomeFamily.BERNOULLI else (
        "log" if fam in (OutcomeFamily.LOGNORMAL, OutcomeFamily.POISSON) else "identity")
    explanation = (
        f"A Normal({prior_mean:g}, {prior_sd:g}) prior on the {link}-scale "
        f"coefficient implies that 95% of plausible mean values fall between "
        f"{_fmt(family, lo)} and {_fmt(family, hi)} before seeing any data. "
        "Weakly-informed priors keep this range broad so the data dominates."
    )
    return {"percentiles": pct, "samples": samples.tolist(),
            "explanation": explanation}
