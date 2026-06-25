"""Study-design specification: the data model that the whole tool revolves around.

A :class:`StudyDesign` is a declarative, JSON-serializable description of an
experiment in the style of While & Sarvghad (CHI '25): a set of categorical or
continuous *factors* (e.g. visualization, task, age group), one or more
*outcomes* (e.g. accuracy as a binary, time as a positive continuous), and a
*grouping unit* (the participant) for which we ultimately generate
counterfactual data.

Everything downstream -- the Wilkinson/brms-style formula, the Bambi/PyMC model,
the counterfactual sampler, and the exporters -- is derived from this object, so
it is deliberately plain (dataclasses + dicts) and free of any heavy imports so
it can be validated and round-tripped without a stats backend installed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


# --------------------------------------------------------------------------- #
# Enumerations
# --------------------------------------------------------------------------- #
class FactorKind(str, Enum):
    CATEGORICAL = "categorical"
    CONTINUOUS = "continuous"


class FactorRole(str, Enum):
    """Whether a factor varies *within* each participant or *between* them.

    This is the single most consequential modeling choice a researcher makes
    (hence the wizard explains it carefully): a within-participant factor can
    carry a participant-level random effect and every counterfactual
    participant gets data at *all* of its levels, whereas a between-participant
    factor partitions participants and each one is only ever observed at a
    single level (as age group was in the paper).
    """

    WITHIN = "within"
    BETWEEN = "between"


class OutcomeFamily(str, Enum):
    """Likelihood families. Names mirror brms/Bambi where possible."""

    BERNOULLI = "bernoulli"      # binary accuracy (optionally chance-corrected)
    LOGNORMAL = "lognormal"      # positive, right-skewed response time
    GAUSSIAN = "gaussian"        # symmetric continuous
    POISSON = "poisson"          # counts


# Per-family metadata used by the formula builder, priors, and explainers.
FAMILY_INFO: dict[OutcomeFamily, dict[str, Any]] = {
    OutcomeFamily.BERNOULLI: {
        "link": "logit",
        "label": "Binary (Bernoulli)",
        "good_for": "Correct/incorrect responses, yes/no, hit/miss.",
        "paper_use": "Accuracy, modeled as a 4-alternative forced choice.",
    },
    OutcomeFamily.LOGNORMAL: {
        "link": "log",
        "label": "Positive & right-skewed (Lognormal)",
        "good_for": "Response/completion times and other positive durations.",
        "paper_use": "Time taken to answer each question.",
    },
    OutcomeFamily.GAUSSIAN: {
        "link": "identity",
        "label": "Symmetric continuous (Normal)",
        "good_for": "Ratings, scores, or already-transformed values.",
        "paper_use": "Not used directly in the paper.",
    },
    OutcomeFamily.POISSON: {
        "link": "log",
        "label": "Counts (Poisson)",
        "good_for": "Number of events: clicks, errors, fixations.",
        "paper_use": "Not used directly in the paper.",
    },
}


_IDENT_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def _check_identifier(name: str, what: str) -> None:
    if not _IDENT_RE.match(name or ""):
        raise SpecError(
            f"{what} name {name!r} must start with a letter and contain only "
            "letters, digits, or underscores (it becomes a model variable)."
        )


class SpecError(ValueError):
    """Raised when a design specification is internally inconsistent."""


# --------------------------------------------------------------------------- #
# Components
# --------------------------------------------------------------------------- #
@dataclass
class Factor:
    """An experimental factor (independent variable)."""

    name: str
    kind: FactorKind = FactorKind.CATEGORICAL
    role: FactorRole = FactorRole.WITHIN
    levels: list[str] = field(default_factory=list)
    label: str = ""
    description: str = ""

    def validate(self) -> None:
        _check_identifier(self.name, "Factor")
        if self.kind == FactorKind.CATEGORICAL:
            if len(self.levels) < 2:
                raise SpecError(
                    f"Categorical factor {self.name!r} needs at least 2 levels "
                    f"(got {len(self.levels)})."
                )
            if len(set(self.levels)) != len(self.levels):
                raise SpecError(f"Factor {self.name!r} has duplicate levels.")

    @property
    def n_levels(self) -> int:
        return len(self.levels) if self.kind == FactorKind.CATEGORICAL else 1


@dataclass
class Outcome:
    """A measured dependent variable and the likelihood used to model it."""

    name: str
    family: OutcomeFamily = OutcomeFamily.GAUSSIAN
    label: str = ""
    description: str = ""
    # For Bernoulli 4AFC: the floor probability of a correct guess. The paper
    # used 0.25, modeling p = guess + (1 - guess) * inv_logit(eta) so accuracy
    # can never drop below chance. 0.0 recovers an ordinary Bernoulli GLM.
    guess_rate: float = 0.0
    # Number of trials per within-cell, used when expanding cell means into
    # trial-level data (the paper's K = 6 questions per visualization).
    trials_per_cell: int = 1

    def validate(self) -> None:
        _check_identifier(self.name, "Outcome")
        if not 0.0 <= self.guess_rate < 1.0:
            raise SpecError(
                f"guess_rate for {self.name!r} must be in [0, 1) (got {self.guess_rate})."
            )
        if self.guess_rate and self.family != OutcomeFamily.BERNOULLI:
            raise SpecError("guess_rate only applies to the Bernoulli family.")
        if self.trials_per_cell < 1:
            raise SpecError(f"trials_per_cell for {self.name!r} must be >= 1.")

    @property
    def link(self) -> str:
        return FAMILY_INFO[self.family]["link"]


@dataclass
class StudyDesign:
    """The complete declarative description of an experiment."""

    name: str
    factors: list[Factor] = field(default_factory=list)
    outcomes: list[Outcome] = field(default_factory=list)
    grouping: str = "participant"
    # Highest-order fixed-effect interaction to include, 0 = main effects only,
    # None = full interaction of every factor (the paper used a full 3-way
    # vis * task * age interaction). Capped at the number of factors.
    interaction_order: int | None = None
    # Drop the global intercept so each cell gets its own coefficient
    # (the "+ 0" one-hot coding from the paper, after Davis et al.).
    drop_intercept: bool = True
    description: str = ""

    # ---- validation ----------------------------------------------------- #
    def validate(self) -> None:
        _check_identifier(self.grouping, "Grouping")
        if not self.factors:
            raise SpecError("A design needs at least one factor.")
        if not self.outcomes:
            raise SpecError("A design needs at least one outcome.")
        names = [f.name for f in self.factors] + [o.name for o in self.outcomes]
        names.append(self.grouping)
        dupes = {n for n in names if names.count(n) > 1}
        if dupes:
            raise SpecError(f"Names must be unique across the design: {sorted(dupes)}.")
        for f in self.factors:
            f.validate()
        for o in self.outcomes:
            o.validate()
        if self.interaction_order is not None and self.interaction_order < 0:
            raise SpecError("interaction_order must be >= 0 or None.")

    # ---- convenience ---------------------------------------------------- #
    @property
    def within_factors(self) -> list[Factor]:
        return [f for f in self.factors if f.role == FactorRole.WITHIN]

    @property
    def between_factors(self) -> list[Factor]:
        return [f for f in self.factors if f.role == FactorRole.BETWEEN]

    def factor(self, name: str) -> Factor:
        for f in self.factors:
            if f.name == name:
                return f
        raise KeyError(name)

    @property
    def categorical_factors(self) -> list[Factor]:
        return [f for f in self.factors if f.kind == FactorKind.CATEGORICAL]

    def n_cells(self) -> int:
        """Number of distinct factor-level combinations (categorical only)."""
        n = 1
        for f in self.categorical_factors:
            n *= f.n_levels
        return n

    # ---- (de)serialization ---------------------------------------------- #
    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # asdict already stringifies Enums via their str base, but be explicit.
        for fac in d["factors"]:
            fac["kind"] = FactorKind(fac["kind"]).value
            fac["role"] = FactorRole(fac["role"]).value
        for out in d["outcomes"]:
            out["family"] = OutcomeFamily(out["family"]).value
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "StudyDesign":
        factors = [
            Factor(
                name=f["name"],
                kind=FactorKind(f.get("kind", "categorical")),
                role=FactorRole(f.get("role", "within")),
                levels=list(f.get("levels", [])),
                label=f.get("label", ""),
                description=f.get("description", ""),
            )
            for f in d.get("factors", [])
        ]
        outcomes = [
            Outcome(
                name=o["name"],
                family=OutcomeFamily(o.get("family", "gaussian")),
                label=o.get("label", ""),
                description=o.get("description", ""),
                guess_rate=float(o.get("guess_rate", 0.0)),
                trials_per_cell=int(o.get("trials_per_cell", 1)),
            )
            for o in d.get("outcomes", [])
        ]
        return cls(
            name=d["name"],
            factors=factors,
            outcomes=outcomes,
            grouping=d.get("grouping", "participant"),
            interaction_order=d.get("interaction_order", None),
            drop_intercept=bool(d.get("drop_intercept", True)),
            description=d.get("description", ""),
        )
