# Example datasets

## `sample_study.csv`

A small, synthetic long-format dataset (120 rows) for trying the **data path**
of the [Counterfactual Participant Studio](https://huggingface.co/spaces/ali-sarvghad/counterfactual-studio).
One row per participant × visualization.

| Column | Role | What the tool should detect |
| --- | --- | --- |
| `participant` | grouping | Participant |
| `visualization` | factor | Categorical factor (`Bar, Line, Pie, Table`) |
| `age_group` | factor | Categorical factor (`Younger, Older`) |
| `accuracy` | outcome | **Binary (Bernoulli)** — values are 0/1 |
| `response_time` | outcome | **Positive & skewed (Lognormal)** |
| `errors` | outcome | **Counts (Poisson)** |

The data is generated (not from real participants), so it's safe to share and
only meant to exercise the auto-detection, fitting, and generation flow.

> Tip: `age_group` is a **between**-participant factor here (each person is in one
> group), but auto-detection can't know that from the data — set it on the Design
> screen.
