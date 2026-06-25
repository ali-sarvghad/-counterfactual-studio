---
title: Counterfactual Participant Studio
emoji: 📊
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# Counterfactual Participant Studio

**▶ Use the tool here (no install):
[huggingface.co/spaces/ali-sarvghad/counterfactual-studio](https://huggingface.co/spaces/ali-sarvghad/counterfactual-studio)**

A guided web app that generates **simulated ("counterfactual") study
participants** — and walks you through every decision in plain language, so you
do not need Bayesian-statistics or Stan/brms expertise to use it. It implements
the modeling approach from:

> Zack While and Ali Sarvghad. 2025. *Toward Filling a Critical Knowledge Gap:
> Charting the Interactions of Age with Task and Visualization.* CHI '25.
> https://doi.org/10.1145/3706598.3714229

In the paper, a Bayesian model was fit to real study data and then sampled to
produce 12,000 counterfactual participants — simulated people who have data for
*every* task × visualization combination, even ones a real participant never
saw. This tool reproduces that method behind a wizard: it sets up the model,
explains the trade-offs, runs it, and hands back the data and runnable scripts.

---

## Table of contents

- [What it does](#what-it-does)
- [What it can and cannot do](#what-it-can-and-cannot-do)
- [Quick start](#quick-start-hosted-app)
- [The two paths](#the-two-paths)
- [Step-by-step walkthrough](#step-by-step-walkthrough)
- [Parameter reference](#parameter-reference) ← *meaning + suggested values for every setting*
- [What you get (outputs)](#what-you-get-outputs)
- [Reading the fit diagnostics](#reading-the-fit-diagnostics)
- [Tips & FAQ](#tips--faq)
- [Running locally / development](#running-locally--development)
- [Deploying your own copy](#deploying-your-own-copy)
- [Architecture](#architecture)

---

## What it does

You describe an experiment as a set of **factors** (things you vary — chart
type, task, age group) and **outcomes** (things you measure — accuracy,
response time, error count). The tool builds a Bayesian model of that design and
produces a population of **counterfactual participants**: simulated people who
each have a value for every combination of your factors.

You can drive it two ways:

- **From real data** — upload a CSV; the tool reads it, auto-detects the
  variables and the right probability distribution for each outcome, fits a
  Bayesian model, and samples new participants from the fitted **posterior**.
  This is the paper's exact approach.
- **From assumptions** — no data needed; you state the values you expect and how
  much individuals differ, and the tool simulates participants from the same
  generative structure. Good for **power analysis, pre-registration, and
  teaching**.

Both paths share one engine and produce the same kinds of output (trial-level
data, per-participant cell means, a reproducibility report, and runnable
Bambi/brms scripts).

## What it can and cannot do

**It can:**

- Auto-detect, from an uploaded CSV, which column is the participant, which are
  factors, which are measured outcomes, and the best-fitting distribution for
  each outcome — then let you confirm or override every guess.
- Model four outcome types: **binary** (Bernoulli, with optional chance
  correction for forced-choice), **positive & right-skewed** (Lognormal, e.g.
  response times), **symmetric continuous** (Normal), and **counts** (Poisson).
- Handle **within-** and **between-participant** factors and their interactions,
  with participant-level random effects (the paper's structure).
- Show, before any computation, what a chosen mean, spread, or prior *implies*
  for real outcome values (live previews and histograms).
- Fit with full MCMC (PyMC) and report convergence diagnostics (R̂, ESS,
  divergences) in plain language.
- Export both datasets, the design as JSON, a reproducibility report, and
  ready-to-run **Bambi (Python)** and **brms (R)** scripts.

**It cannot (by design / current scope):**

- It is **not a static website** — it runs real MCMC, so it needs a server with
  a few GB of RAM (that's why it's hosted on Hugging Face Spaces, not GitHub
  Pages).
- It models the **four families above only** — not ordinal, multinomial,
  censored, or zero-inflated outcomes.
- It assumes **one grouping unit** (the participant). It does not model nested or
  multiple crossed grouping levels (e.g. participants *and* items as separate
  random effects), time-series/autocorrelation, or missing-data imputation.
- Factors are treated as **categorical** in the generative grid; a continuous
  factor is supported in the design model but is not expanded into cells the way
  categorical factors are.
- **Auto-detection is a heuristic.** It is usually right, but you should confirm
  each role and distribution — especially **within vs between**, which the data
  alone cannot reveal.
- Simulated participants are **only as good as the model and your assumptions**.
  Counterfactual data is a tool for robustness, power analysis, and teaching —
  **not a substitute for collecting real data**, and not to be presented as real
  participants.
- Fitting needs **enough real data** to be meaningful; a handful of rows will
  fit but the posterior will be very uncertain.

## Quick start (hosted app)

1. Open **[the Space](https://huggingface.co/spaces/ali-sarvghad/counterfactual-studio)**.
   (If it shows "Building" or "Sleeping," give it a moment to wake up.)
2. Pick a path on the start screen: **I have data** or **I'm designing from
   assumptions**. (No dataset handy? Grab the sample below.)
3. Follow the wizard. Hover the small circled **?** next to any field for an
   explanation and suggested values.
4. At the end, preview the simulated participants and download the datasets and
   scripts.

> **Try it with the sample dataset.** Download
> [`examples/sample_study.csv`](examples/sample_study.csv) (120 rows, synthetic)
> and upload it on the data path. The tool should detect `accuracy` as **Binary**,
> `response_time` as **Positive & skewed**, and `errors` as **Counts** — see
> [`examples/README.md`](examples/README.md) for the full expected breakdown.

> **Privacy note.** On the data path, your CSV is uploaded to the server only to
> fit the model; the downloadable participants are *simulated*, not your raw
> rows. On the public demo Space, uploaded files and projects live in the
> container and reset when it restarts — treat it as transient and don't upload
> sensitive data. To keep data, run your own copy (see
> [Deploying](#deploying-your-own-copy)).

## The two paths

| | **I have data** | **I'm designing from assumptions** |
| --- | --- | --- |
| Need a dataset? | Yes (a CSV) | No |
| How outcomes are set | Auto-detected from the data, then confirmed | You pick the distribution for each outcome |
| Where numbers come from | The **fitted posterior** | The **values you state** |
| Wizard order | Start → **Upload** → Design → Fit → Generate → Results | Start → Design → **Assumptions** → Generate → Results |
| Best for | Reproducing the paper's method on your own pilot data | Power analysis, pre-registration, teaching |

## Step-by-step walkthrough

### Path A — I have data

1. **Start.** Choose "I have pilot / study data" and name the project.
2. **Upload & auto-detect.** Drop in a **long-format CSV** (one row per trial,
   with columns for the participant, each factor, and each outcome) — or use the
   ready-made [`examples/sample_study.csv`](examples/sample_study.csv). The tool
   immediately analyzes every column and proposes:
   - the **participant** column,
   - which columns are **factors** vs **measured outcomes**,
   - and the **distribution** for each outcome, with a small histogram showing
     the shape of your data.
   Confirm or adjust anything, optionally enable the **Hampel outlier filter**,
   then continue.
3. **Design.** The design arrives **pre-filled** from the detection. Review it —
   in particular set each factor's **within/between** role (the data can't tell
   this). You'll see the generated Bambi/brms formulas update live.
4. **Model & fit.** Inspect the formulas and priors (with prior-predictive
   previews), choose sampler settings, and fit. Read the convergence
   diagnostics.
5. **Generate.** Choose how many counterfactual participants and a random seed.
6. **Results.** Distribution charts, a data preview, and downloads.

### Path B — Designing from assumptions

1. **Start.** Choose "I'm designing from assumptions." You begin from the
   paper's worked example so nothing is blank.
2. **Design.** Edit factors (names, levels, within/between) and outcomes
   (distribution family) to match your study.
3. **Assumptions.** For each outcome, state the **expected value** in each factor
   combination (or quick-fill all cells at once) and the **between-participant
   spread**. A live preview shows the population your numbers imply.
4. **Generate** and **Results** — same as above.

## Parameter reference

Every setting below also has a hover **?** in the app. "Suggested" values are
sensible defaults, often from the paper.

### Design — factors

| Setting | Meaning | Suggested |
| --- | --- | --- |
| **Factor name** | A thing you varied (e.g. `vis`, `task`). Becomes a model variable, so use letters, numbers, or underscores — no spaces. | short, lowercase |
| **Type** | **Categorical** = a fixed set of named conditions (Bar, Line, Pie). **Continuous** = a smoothly varying number. | Categorical for most experiments |
| **Varies… (within / between)** | The most consequential choice. **Within** = every participant experiences all levels (each saw all chart types) → carries individual differences. **Between** = each participant is in only one level (one task, one age group). Sets the random-effect structure. | match your study design |
| **Levels** | The named conditions of a categorical factor, comma-separated. Need ≥ 2. Each counterfactual participant gets data at *every* level of a within factor. | e.g. `Bar, Line, Pie, Table` |

### Design — outcomes

| Setting | Meaning | Suggested |
| --- | --- | --- |
| **Outcome name** | A thing you measured (`accuracy`, `time`). Becomes a model variable. | short, lowercase |
| **Measurement type (family)** | The kind of number, which sets the likelihood: **Binary (Bernoulli)** for correct/incorrect; **Positive & skewed (Lognormal)** for response times; **Symmetric continuous (Normal)** for ratings/scores; **Counts (Poisson)** for errors/clicks. | pick what matches your measure |
| **Guessing floor** *(Binary only)* | Chance of being right by pure guessing; accuracy can never fall below it. | `0.25` for a 4-option question (the paper), `0.5` for true/false, `0` if guessing is impossible |
| **Trials per cell** | How many questions/observations each participant answers per factor combination. More trials = less noise per simulated participant. | `6` (the paper); `1` for a single value per cell |
| **Participant identifier** | Name of the unit you're simulating. Each counterfactual participant gets a full set of responses. | `participant` |

### Assumptions (no-data path)

| Setting | Meaning | Suggested |
| --- | --- | --- |
| **Expected value per cell** | The mean outcome you expect in each factor combination (e.g. 78% accuracy for Bar). Quick-fill sets them all at once, then fine-tune. | use pilot intuition or prior literature |
| **Between-participant spread** *(link scale)* | How much individuals differ. `0` = everyone identical; larger = a more varied, realistic population. It's on the model's internal scale, so the live preview shows what your value implies in real units. | `0.3–0.5` for moderate individual differences |

### Model & fit (data path)

| Setting | Meaning | Suggested |
| --- | --- | --- |
| **Priors** | What's plausible *before* seeing data, shown on the model's link scale with a live preview. The fit uses weakly-informed defaults so the data dominates. | leave defaults unless you have strong prior knowledge |
| **draws** | Posterior samples kept **per chain** after warm-up. More = smoother estimates, slower. | `1000` (lower to ~`500` for a quick trial) |
| **tune** | Warm-up steps the sampler uses to calibrate, then discards. | `1000` |
| **chains** | Independent sampler runs; comparing them reveals convergence problems. | `4` (or `2` for a quick trial) |
| **seed** | Makes the fit reproducible. | any integer (e.g. `1234`) |
| **target_accept** *(API)* | Sampler step-size target; raising it reduces divergences at the cost of speed. | `0.9`; raise to `0.95–0.99` if you see divergences |

### Preprocessing & generation

| Setting | Meaning | Suggested |
| --- | --- | --- |
| **Hampel outlier filter** *(data path)* | Drops trials more than 3 MADs from their cell median (paper §4.1), for continuous outcomes. | on if you expect stray slow/fast trials |
| **Number of participants** | How many counterfactual participants to generate. | `2000` (the paper generated 12,000) |
| **Random seed (generate)** | Same seed ⇒ identical, reproducible output. | any integer (e.g. `7`) |

## What you get (outputs)

On the **Results** screen you can download:

- **Trial-level dataset** — one row per simulated response (like the paper's
  trial data).
- **Per-participant cell means** — the per-cell summary the paper analyzed.
- **Design JSON** — your full design, re-loadable and shareable.
- **Reproducibility report** — a plain-language record of every choice.
- **Bambi (Python)** and **brms (R)** scripts — runnable code that reproduces the
  model outside this tool.

## Reading the fit diagnostics

After a fit, each outcome shows three numbers and a plain-language verdict:

- **R̂ (R-hat)** — agreement across chains. **< 1.01 is good**; ≥ 1.05 means it
  hasn't converged — increase `tune`/`draws`.
- **ESS (effective sample size)** — how much independent information you have.
  **Higher is better**; a few hundred per parameter is usually fine.
- **Divergences** — **0 is ideal.** A handful suggests raising `target_accept`
  (or rethinking very tight priors).

If diagnostics look bad, increase `tune` and `draws`, add chains, or simplify the
design, then re-fit.

## Tips & FAQ

- **The app seems asleep / slow to load.** Free Spaces sleep when idle and take a
  few seconds to wake. The first model fit is also slowest while things warm up.
- **My CSV won't map.** Use **long format**: one row per trial, with a column for
  the participant, each factor, and each outcome. Wide formats (one row per
  participant with many outcome columns) won't auto-detect cleanly.
- **A distribution was detected wrong.** Just change it on the upload screen —
  detection is a starting point, not a verdict.
- **Within vs between?** Ask: did each participant experience *all* levels of this
  factor (within), or just *one* (between)? The data can't tell you; you must.
- **Reproducibility.** Fix the sampler seed and the generation seed to get
  identical output every run.

---

## Running locally / development

Useful if you want a fast edit/test loop or to keep your data on your own
machine. Requires Python 3.11+ and Node 18+.

**Backend:**

```bash
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn api.main:app --reload      # http://localhost:8000  (API docs at /docs)
pytest                              # fast tests
pytest --run-slow                   # also fit real Bayesian models (needs PyMC)
```

**Frontend:**

```bash
cd frontend
npm install
npm run dev      # http://localhost:5173 (proxies /api to :8000)
npm run build    # outputs frontend/dist, which the backend serves at /
```

In production the frontend is built and the backend serves it: `api/main.py`
mounts `frontend/dist` at `/`, so the whole app runs from one process.

## Deploying your own copy

The repo ships a root **`Dockerfile`** that builds the frontend and the Python
stack into a single image serving the API and UI on one port (`$PORT`, default
`7860`). See **[DEPLOY.md](DEPLOY.md)** for step-by-step instructions —
Hugging Face Spaces (recommended; the free CPU tier handles PyMC),
Render/Fly.io/Cloud Run, or a local `docker run`. To persist projects across
restarts, attach storage and set `STUDIO_DATA_DIR` (details in DEPLOY.md).

## Architecture

```
backend/
  studio/                # engine (no web dependencies)
    spec.py              # StudyDesign / Factor / Outcome data model
    templates.py         # the CHI '25 design as a ready-to-load template
    profile.py           # auto-detect roles + distributions from an uploaded CSV
    formula.py           # design -> Bambi & brms formulas
    engine.py            # fit, posterior + assumptions counterfactual generation
    preprocess.py        # Hampel outlier filter (paper §4.1)
    analysis.py          # per-cell distribution summaries for charts
    export.py            # datasets, reproducibility report, emitted scripts
  api/                   # FastAPI layer
    main.py              # app + static frontend mount
    routes.py            # all endpoints
    schemas.py           # request/response models
    store.py             # SQLite metadata + on-disk artifacts
    jobs.py              # async fit runner + draws cache
    previews.py          # analytic "what does this choice imply?" helpers
  tests/                 # fast unit/API tests + slow MCMC integration tests
frontend/                # React + Vite wizard UI
```

### Key API endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/templates` | list built-in designs (incl. the paper) |
| POST | `/api/designs/validate` | validate a design, return Bambi/brms formulas |
| POST | `/api/designs/preview-outcome` | implied participant spread for a target mean |
| POST | `/api/designs/preview-prior` | what a prior implies for the outcome |
| POST | `/api/projects` | create a project (from a template or design) |
| POST | `/api/projects/{id}/data/upload` | upload a CSV, get a column preview |
| POST | `/api/projects/{id}/data/profile` | auto-detect roles + distributions from the CSV |
| POST | `/api/projects/{id}/data/commit` | map columns, optional Hampel filter |
| POST | `/api/projects/{id}/fit` | start an async Bayesian fit |
| GET | `/api/projects/{id}/status` | poll fit status + diagnostics |
| POST | `/api/projects/{id}/generate` | generate counterfactuals (posterior or assumptions) |
| GET | `/api/projects/{id}/download/{name}` | download an artifact |
