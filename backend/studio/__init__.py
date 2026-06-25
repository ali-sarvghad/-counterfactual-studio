"""Counterfactual Participant Studio -- core engine.

A guided tool for generating simulated ("counterfactual") study participants
using the Bayesian approach of While & Sarvghad (CHI '25). The pure-python
pieces (spec, templates, formula, export) import with no heavy dependencies;
the engine module additionally needs bambi/pymc.
"""

from .spec import (  # noqa: F401
    Factor,
    FactorKind,
    FactorRole,
    Outcome,
    OutcomeFamily,
    StudyDesign,
    SpecError,
    FAMILY_INFO,
)
from .templates import get_template, paper_design, blank_design, TEMPLATES  # noqa: F401
from .formula import build_formula, brms_formula, brms_family, FormulaParts  # noqa: F401

__version__ = "0.1.0"
