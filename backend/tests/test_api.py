"""API tests using FastAPI's TestClient.

The fast tests cover every endpoint reachable without MCMC, including the full
assumptions-path generation flow and artifact downloads. A slow test exercises
the data path: upload -> commit -> fit -> generate from the posterior.
"""

import io

import pandas as pd
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("STUDIO_DATA_DIR", str(tmp_path))
    from api import store
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "studio.db")
    store.init_db()
    from api.main import app
    return TestClient(app)


# --------------------------------------------------------------------------- #
# Templates, design validation, previews
# --------------------------------------------------------------------------- #
def test_templates_and_validation(client):
    assert client.get("/api/health").json() == {"status": "ok"}

    keys = {t["key"] for t in client.get("/api/templates").json()}
    assert {"paper", "blank"} <= keys

    paper = client.get("/api/templates/paper").json()
    assert paper["grouping"] == "participant"

    v = client.post("/api/designs/validate", json={"design": paper}).json()
    assert v["valid"] and v["n_cells"] == 100
    assert v["formulas"]["accuracy"]["bambi"].startswith("accuracy ~ 0 + ")
    assert v["formulas"]["time"]["brms_family"] == "lognormal()"

    bad = client.post("/api/designs/validate",
                      json={"design": {"name": "x", "factors": [], "outcomes": []}}).json()
    assert bad["valid"] is False and bad["error"]


def test_previews(client):
    r = client.post("/api/designs/preview-outcome", json={
        "family": "bernoulli", "guess_rate": 0.25, "mean": 0.7, "between_sd": 0.5}).json()
    assert r["percentiles"]["p50"] == pytest.approx(0.7, abs=1e-6)
    assert r["percentiles"]["p2.5"] >= 0.25  # chance floor respected
    assert len(r["samples"]) > 0 and "95%" in r["explanation"]

    p = client.post("/api/designs/preview-prior", json={
        "family": "lognormal", "prior_mean": 3.4, "prior_sd": 1.0}).json()
    # exp(3.4) ~ 30s median, broad range -- mirrors the paper's time prior
    assert p["percentiles"]["p50"] == pytest.approx(29.96, rel=0.01)


# --------------------------------------------------------------------------- #
# Project lifecycle + assumptions-path generation (no MCMC)
# --------------------------------------------------------------------------- #
def test_project_and_assumptions_generation(client):
    # smaller design keeps the trial expansion quick
    design = {
        "name": "API test",
        "grouping": "participant",
        "factors": [
            {"name": "vis", "role": "within", "levels": ["Bar", "Line", "Table"]},
            {"name": "age", "role": "between", "levels": ["YA", "PLA"]},
        ],
        "outcomes": [
            {"name": "accuracy", "family": "bernoulli", "guess_rate": 0.25,
             "trials_per_cell": 2},
            {"name": "time", "family": "lognormal", "trials_per_cell": 2},
        ],
    }
    proj = client.post("/api/projects", json={"name": "API test", "design": design}).json()
    pid = proj["id"]
    assert proj["n_cells"] == 6 and proj["status"] == "draft"

    assert any(p["id"] == pid for p in client.get("/api/projects").json())

    # build assumptions for all 6 cells
    cell_means_acc, cell_means_time = {}, {}
    for vis in ["Bar", "Line", "Table"]:
        for age in ["YA", "PLA"]:
            key = f"vis={vis}|age={age}"
            cell_means_acc[key] = 0.9 if vis == "Table" else 0.6
            cell_means_time[key] = 15.0 if age == "YA" else 25.0

    body = {
        "source": "assumptions",
        "n_participants": 40,
        "seed": 1,
        "assumptions": {
            "cell_means": {"accuracy": cell_means_acc, "time": cell_means_time},
            "between_sd": {"accuracy": 0.4, "time": 0.2},
            "residual_sd": {"time": 0.3},
        },
    }
    gen = client.post(f"/api/projects/{pid}/generate", json=body).json()
    assert gen["source"] == "assumptions"
    assert gen["n_trials"] == 40 * 6 * 2
    assert gen["summary"]["outcomes"]["accuracy"]["overall"]["p2.5"] >= 0.25
    assert "cell_means.csv" in gen["artifacts"]
    assert gen["cell_means_preview"], "preview rows for the results table"

    # the contract the Results charts depend on: by_factor rows with percentiles
    by_factor = gen["summary"]["outcomes"]["accuracy"]["by_factor"]
    assert set(by_factor) == {"vis", "age"}
    vis_rows = by_factor["vis"]
    assert {r["level"] for r in vis_rows} == {"Bar", "Line", "Table"}
    for r in vis_rows:
        assert {"p2.5", "p25", "p50", "p75", "p97.5"} <= set(r)
    # sorted best-first for accuracy -> Table (0.9) leads
    assert vis_rows[0]["level"] == "Table"

    # download artifacts
    cm = client.get(f"/api/projects/{pid}/download/cell_means.csv")
    assert cm.status_code == 200 and b"participant" in cm.content
    rep = client.get(f"/api/projects/{pid}/download/reproducibility_report.md")
    assert rep.status_code == 200 and b"Reproducibility report" in rep.content
    rscript = client.get(f"/api/projects/{pid}/download/brms_fit.R")
    assert b"lognormal()" in rscript.content

    # path traversal guard
    assert client.get(f"/api/projects/{pid}/download/..%2Fstudio.db").status_code in (400, 404)

    # generating from posterior without a fit is a clear error
    err = client.post(f"/api/projects/{pid}/generate",
                      json={"source": "posterior", "n_participants": 10})
    assert err.status_code == 400


def test_posterior_requires_data_before_fit(client):
    proj = client.post("/api/projects", json={"template": "paper"}).json()
    r = client.post(f"/api/projects/{proj['id']}/fit", json={})
    assert r.status_code == 400  # no data committed yet


# --------------------------------------------------------------------------- #
# Slow: full data path through the API
# --------------------------------------------------------------------------- #
@pytest.mark.slow
def test_data_path_upload_fit_generate(client):
    import numpy as np
    import time as _time

    pytest.importorskip("bambi")
    design = {
        "name": "data path",
        "grouping": "participant",
        "factors": [
            {"name": "vis", "role": "within", "levels": ["Bar", "Table"]},
            {"name": "age", "role": "between", "levels": ["YA", "PLA"]},
        ],
        "outcomes": [
            {"name": "accuracy", "family": "bernoulli", "guess_rate": 0.25,
             "trials_per_cell": 2},
        ],
    }
    pid = client.post("/api/projects", json={"design": design}).json()["id"]

    rng = np.random.default_rng(0)
    rows = []
    for p in range(16):
        age = ["YA", "PLA"][p % 2]
        for vis in ["Bar", "Table"]:
            for _ in range(2):
                rows.append(dict(participant=f"u{p}", vis=vis, age=age,
                                 accuracy=int(rng.random() < (0.7 if vis == "Table" else 0.55))))
    csv = pd.DataFrame(rows).to_csv(index=False).encode()

    up = client.post(f"/api/projects/{pid}/data/upload",
                     files={"file": ("d.csv", io.BytesIO(csv), "text/csv")}).json()
    assert up["n_rows"] == 64 and up["suggested_mapping"]["vis"] == "vis"

    commit = client.post(f"/api/projects/{pid}/data/commit",
                         json={"mapping": up["suggested_mapping"], "apply_hampel": False})
    assert commit.status_code == 200

    assert client.post(f"/api/projects/{pid}/fit",
                       json={"draws": 100, "tune": 100, "chains": 2}).json()["status"] == "fitting"
    for _ in range(120):
        st = client.get(f"/api/projects/{pid}/status").json()
        if st["status"] in ("fitted", "failed"):
            break
        _time.sleep(1)
    assert st["status"] == "fitted", st.get("error")
    assert st["diagnostics"]["accuracy"]["status"] in ("good", "warn", "bad")

    gen = client.post(f"/api/projects/{pid}/generate",
                      json={"source": "posterior", "n_participants": 30}).json()
    assert gen["source"] == "posterior"
    assert gen["summary"]["outcomes"]["accuracy"]["overall"]["p2.5"] >= 0.25
