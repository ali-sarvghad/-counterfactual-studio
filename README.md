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
  sampling for both paths, Hampel outlier filter, exporters (datasets, report,
  scripts).
- [x] **Phase 2 — FastAPI backend** (`backend/api/`): project CRUD, templates,
  design validation + live "what does this imply?" previews, CSV upload with
  column mapping, async fit jobs with status polling, counterfactual generation
  for both paths, summaries, and artifact downloads.
- [ ] Phase 3 — React wizard UI with explainers and live previews.
- [ ] Phase 4 — paper-style result visualizations.

## Layout

```
participant-studio/
  backend/
    requirements.txt
    pytest.ini
    studio/                # engine (no web deps)
      spec.py              # StudyDesign / Factor / Outcome data model
      templates.py         # the CHI '25 design as a ready-to-load template
      formula.py           # design -> Bambi & brms formulas
      engine.py            # fit, posterior + assumptions counterfactual generation
      preprocess.py        # Hampel outlier filter (paper section 4.1)
      analysis.py          # per-cell distribution summaries for charts
      export.py            # datasets, reproducibility report, emitted scripts
    api/                   # FastAPI layer
      main.py              # app + CORS + static frontend mount
      routes.py            # all endpoints
      schemas.py           # request/response models
      store.py             # SQLite metadata + on-disk artifacts
      jobs.py              # async fit runner + draws cache (de)serialization
      previews.py          # analytic "what does this choice imply?" helpers
    tests/                 # fast unit/API tests + slow MCMC integration tests
```

## Running the backend

```bash
cd participant-studio/backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn api.main:app --reload          # http://localhost:8000  (docs at /docs)
pytest                                  # fast tests
pytest --run-slow                       # also fit real Bayesian models
```

### Key endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/templates` | list built-in designs (incl. the paper) |
| POST | `/api/designs/validate` | validate a design, return Bambi/brms formulas |
| POST | `/api/designs/preview-outcome` | implied participant spread for a target mean |
| POST | `/api/designs/preview-prior` | what a prior implies for the outcome |
| POST | `/api/projects` | create a project (from a template or design) |
| POST | `/api/projects/{id}/data/upload` | upload a CSV, get a suggested column mapping |
| POST | `/api/projects/{id}/data/commit` | map columns, optional Hampel filter |
| POST | `/api/projects/{id}/fit` | start an async Bayesian fit |
| GET | `/api/projects/{id}/status` | poll fit status + diagnostics |
| POST | `/api/projects/{id}/generate` | generate counterfactuals (posterior or assumptions) |
| GET | `/api/projects/{id}/download/{name}` | download an artifact |

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
