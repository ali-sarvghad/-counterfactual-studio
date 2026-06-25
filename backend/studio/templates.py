"""Built-in design templates.

The flagship template reproduces the design of While & Sarvghad (CHI '25) so a
researcher can load a known-good, fully-worked example, see every field
pre-filled, and learn the tool by modifying something familiar rather than
starting from a blank page.
"""

from __future__ import annotations

from .spec import (
    Factor,
    FactorKind,
    FactorRole,
    Outcome,
    OutcomeFamily,
    StudyDesign,
)

# Amar et al.'s ten low-level analysis tasks, as used in the paper.
PAPER_TASKS = [
    "FindAnomalies",
    "FindClusters",
    "FindCorrelation",
    "ComputeDerivedValue",
    "CharacterizeDistribution",
    "FindExtremum",
    "Filter",
    "Order",
    "DetermineRange",
    "RetrieveValue",
]

PAPER_VISUALIZATIONS = ["Bar", "Line", "Pie", "Scatterplot", "Table"]


def paper_design() -> StudyDesign:
    """The Age x Task x Visualization design from the CHI '25 paper."""
    return StudyDesign(
        name="While & Sarvghad (CHI '25): Age x Task x Visualization",
        description=(
            "Conceptual replication comparing younger adults (YA) and people in "
            "late adulthood (PLA) across ten low-level analysis tasks and five "
            "basic visualizations. Accuracy is a 4-alternative forced choice "
            "(chance = 25%); time is a positive, right-skewed response time."
        ),
        grouping="participant",
        interaction_order=None,  # full vis * task * age interaction
        drop_intercept=True,
        factors=[
            Factor(
                name="vis",
                label="Visualization",
                kind=FactorKind.CATEGORICAL,
                role=FactorRole.WITHIN,
                levels=PAPER_VISUALIZATIONS,
                description=(
                    "The chart type shown. Within-participant: each person saw "
                    "all five visualizations."
                ),
            ),
            Factor(
                name="task",
                label="Analysis task",
                kind=FactorKind.CATEGORICAL,
                role=FactorRole.BETWEEN,
                levels=PAPER_TASKS,
                description=(
                    "The low-level analysis task (Amar et al.). Between-"
                    "participant: each person was assigned exactly one task."
                ),
            ),
            Factor(
                name="age",
                label="Age group",
                kind=FactorKind.CATEGORICAL,
                role=FactorRole.BETWEEN,
                levels=["YA", "PLA"],
                description=(
                    "Younger adults (25-40) vs people in late adulthood (60+). "
                    "Between-participant: a person belongs to one age group."
                ),
            ),
        ],
        outcomes=[
            Outcome(
                name="accuracy",
                label="Accuracy",
                family=OutcomeFamily.BERNOULLI,
                guess_rate=0.25,
                trials_per_cell=6,
                description=(
                    "Correct (1) or incorrect (0). Modeled with a 25% floor for "
                    "the chance of a correct guess in a 4-option question."
                ),
            ),
            Outcome(
                name="time",
                label="Completion time (s)",
                family=OutcomeFamily.LOGNORMAL,
                trials_per_cell=6,
                description=(
                    "Seconds to answer a question. Right-skewed, so modeled with "
                    "a lognormal likelihood."
                ),
            ),
        ],
    )


# A minimal starting point for the "from scratch" path.
def blank_design() -> StudyDesign:
    return StudyDesign(
        name="Untitled design",
        grouping="participant",
        factors=[
            Factor(
                name="condition",
                label="Condition",
                kind=FactorKind.CATEGORICAL,
                role=FactorRole.WITHIN,
                levels=["A", "B"],
            )
        ],
        outcomes=[
            Outcome(name="response", family=OutcomeFamily.GAUSSIAN, trials_per_cell=1)
        ],
    )


TEMPLATES = {
    "paper": paper_design,
    "blank": blank_design,
}


def get_template(key: str) -> StudyDesign:
    if key not in TEMPLATES:
        raise KeyError(f"Unknown template {key!r}. Available: {sorted(TEMPLATES)}")
    return TEMPLATES[key]()
