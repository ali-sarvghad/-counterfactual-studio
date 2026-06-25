"""Turn a :class:`StudyDesign` into model formulas.

We produce two things from one design:

* a **Bambi** (Python) formula, used to actually build and fit the model, and
* a **brms** (R) formula string, emitted in the reproducibility report so the
  method is transparent and re-runnable in the ecosystem the paper used.

The fixed-effect part follows the paper's "+ 0" one-hot / cell-means style
(after Davis et al.), and the random-effect part places participant-level
varying slopes on the *within*-participant factors -- exactly the
``(vis + 0 | pt | user.id)`` structure from the paper, generalized.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from .spec import Factor, FactorKind, Outcome, OutcomeFamily, StudyDesign


@dataclass
class FormulaParts:
    """The pieces needed to build a model for one outcome."""

    outcome: Outcome
    response_term: str          # LHS, e.g. "accuracy" or "log(time)"
    fixed: str                  # RHS fixed-effect part, e.g. "0 + vis*task*age"
    random: str                 # RHS random-effect part, e.g. "(0 + vis | participant)"
    bambi_family: str           # family name to pass to bambi.Model
    needs_log_transform: bool   # True when we fit gaussian on log(outcome)

    @property
    def bambi_formula(self) -> str:
        rhs = self.fixed if not self.random else f"{self.fixed} + {self.random}"
        return f"{self._bambi_lhs} ~ {rhs}"

    @property
    def _bambi_lhs(self) -> str:
        # Bambi has no lognormal family, so we fit a gaussian on a pre-computed
        # log column named log_<outcome> (created by the engine).
        if self.needs_log_transform:
            return f"log_{self.outcome.name}"
        return self.outcome.name


def _fixed_terms(design: StudyDesign) -> list[str]:
    """Build the list of fixed-effect terms honoring ``interaction_order``."""
    names = [f.name for f in design.factors]
    n = len(names)
    order = design.interaction_order
    if order is None or order >= n:
        # Full interaction. We use the pure cell-means form ("vis:task:age")
        # rather than the crossed form ("vis*task*age"): with the dropped
        # intercept both fit identical cell means (this is the paper's "unique
        # coefficient per cell" coding), but the crossed form also emits a
        # reduced-coded standalone main effect for each factor, whose ArviZ
        # coordinate (e.g. vis_dim, length n-1) collides with the full-coded
        # participant random slope on the same factor (length n). The pure
        # interaction has no standalone main effect, so there is no collision.
        return [":".join(names)] if n else []
    order = max(order, 1)
    terms: list[str] = []
    for k in range(1, order + 1):
        for combo in combinations(names, k):
            terms.append(":".join(combo))
    return terms


def _fixed_part(design: StudyDesign) -> str:
    terms = _fixed_terms(design)
    body = " + ".join(terms) if terms else "1"
    if design.drop_intercept:
        return f"0 + {body}"
    return body


def _random_part(design: StudyDesign, *, intercept_fallback: bool = True) -> str:
    """Participant-level varying effects on the within-participant factors."""
    within = [f.name for f in design.within_factors]
    if not within:
        # No within factor to vary; a varying intercept still captures
        # participant-to-participant differences if the group is observed
        # repeatedly. With purely between designs there is nothing to vary.
        if intercept_fallback and _has_repeated_measures(design):
            return f"(1 | {design.grouping})"
        return ""
    slopes = " + ".join(within)
    return f"(0 + {slopes} | {design.grouping})"


def _has_repeated_measures(design: StudyDesign) -> bool:
    """Does a participant contribute more than one row? True if any within
    factor has multiple levels or any outcome has trials_per_cell > 1."""
    if any(f.n_levels > 1 for f in design.within_factors):
        return True
    return any(o.trials_per_cell > 1 for o in design.outcomes)


def build_formula(design: StudyDesign, outcome: Outcome) -> FormulaParts:
    needs_log = outcome.family == OutcomeFamily.LOGNORMAL
    family = "gaussian" if needs_log else outcome.family.value
    return FormulaParts(
        outcome=outcome,
        response_term=f"log({outcome.name})" if needs_log else outcome.name,
        fixed=_fixed_part(design),
        random=_random_part(design),
        bambi_family=family,
        needs_log_transform=needs_log,
    )


def brms_formula(design: StudyDesign, outcome: Outcome) -> str:
    """The brms (R) formula string for the emitted reproducibility script.

    brms supports a true ``lognormal()`` family, so unlike Bambi we keep the
    response on its natural scale and let brms handle the log link, matching
    the paper exactly.
    """
    parts = build_formula(design, outcome)
    rhs = parts.fixed if not parts.random else f"{parts.fixed} + {parts.random}"
    # brms uses the same Wilkinson syntax for the structural part.
    return f"{outcome.name} ~ {rhs}"


def brms_family(outcome: Outcome) -> str:
    return {
        OutcomeFamily.BERNOULLI: "bernoulli()",
        OutcomeFamily.LOGNORMAL: "lognormal()",
        OutcomeFamily.GAUSSIAN: "gaussian()",
        OutcomeFamily.POISSON: "poisson()",
    }[outcome.family]
