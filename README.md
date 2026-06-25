# Counterfactual Participant Studio

A guided web application that lets researchers generate **simulated
("counterfactual") study participants** using the Bayesian approach from:

> Zack While and Ali Sarvghad. 2025. *Toward Filling a Critical Knowledge Gap:
> Charting the Interactions of Age with Task and Visualization.* CHI '25.
> https://doi.org/10.1145/3706598.3714229

In the paper, a Bayesian model was fit to real study data and then sampled to
produce 12,000 counterfactual participants, each with performance data across
*every* task × visualization combination. That modeling step is powerful but
hard to do without Stan/brms expertise. This tool walks a researcher through
each decision, explains the trade-offs, runs the model, and hands back the data.

## Two paths, one engine

- **I have pilot/study data** → fit a Bayesian model (Bambi/PyMC, the Python
  analogue of brms) and sample counterfactual participants from the *posterior*.
- **I'm designing from assumptions** → state expected effects and a
  between-participant spread; simulate from the same generative structure with
  no data (for power analysis, pre-registration, or teaching).

Both paths produce the same outputs: **trial-level data** (one row per simulated
response, like Table 3 in the paper) and **per-participant cell means** (what the
paper analyzed), plus a reproducibility report and runnable Bambi/brms scripts.

## Status

Under active development.

- [x] **Phase 1 — core engine** (`backend/studio/`): design spec, the paper as a
  built-in template, Wilkinson/brms formula builder, fit + counterfactual
  sampling for both paths, exporters (datasets, report, scripts).
- [ ] Phase 2 — FastAPI backend (projects, upload, async fit jobs, downloads).
- [ ] Phase 3 — React wizard UI with explainers and live previews.
- [ ] Phase 4 — paper-style result visualizations.

## Layout

```
participant-studio/
  backend/
    requirements.txt
    studio/
      spec.py        # StudyDesign / Factor / Outcome data model
      templates.py   # the CHI '25 design as a ready-to-load template
      formula.py     # design -> Bambi & brms formulas
      engine.py      # fit, posterior + assumptions counterfactual generation
      export.py      # datasets, reproducibility report, emitted scripts
```

## Core concepts

- **Factor** — an independent variable (e.g. `vis`, `task`, `age`), categorical
  or continuous, marked **within**- or **between**-participant. That role
  determines the random-effect structure and which combinations a real
  participant could be observed at.
- **Outcome** — a dependent variable with a likelihood family: `bernoulli`
  (binary accuracy, with an optional chance-correction floor for forced-choice),
  `lognormal` (response time), `gaussian`, or `poisson`.
- **Counterfactual participant** — a simulated person with data for *all* factor
  combinations, drawn either from the fitted posterior or from stated
  assumptions.

## Development

```bash
cd participant-studio/backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
```

The faithful Bayesian fitting requires the full stats stack (Bambi/PyMC); the
spec/template/formula/export modules import without it.
