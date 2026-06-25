import React, { useState } from "react";
import { api } from "../api.js";
import { Explainer } from "../components/ui.jsx";

export function Concept({ path, setPath, setProject, patchShared, next }) {
  const [name, setName] = useState("My simulation");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  async function begin() {
    setBusy(true);
    setErr(null);
    try {
      // The data path builds its design from the uploaded CSV, so it starts
      // blank; the assumptions path starts from the worked paper example.
      const template = path === "posterior" ? "blank" : "paper";
      const proj = await api.createProject({ name, template });
      setProject(proj);
      patchShared({ generation: null, fitDiagnostics: null, committed: false });
      next();
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="panel">
      <h2>Generate simulated study participants</h2>
      <p className="lead">
        This tool recreates the modeling approach from <i>“Toward Filling a
        Critical Knowledge Gap”</i> (While &amp; Sarvghad, CHI&nbsp;’25): it builds a
        Bayesian model of an experiment and samples <b>counterfactual
        participants</b> — simulated people who have data for <i>every</i>
        task × visualization (or whatever factors you define), even ones a real
        participant never saw.
      </p>

      <Explainer>
        In the paper, a model fit to real data was sampled to create 12,000
        counterfactual participants, making the analysis far more robust. You can
        do the same here — either from your own pilot data, or purely from
        assumptions when you have no data yet.
      </Explainer>

      <h3 style={{ marginTop: 22 }}>1. Where will your numbers come from?</h3>
      <div className="choices">
        <div className={`choice ${path === "posterior" ? "sel" : ""}`}
          onClick={() => setPath("posterior")}>
          <h3>I have pilot / study data</h3>
          <p>Upload a CSV. We fit a Bayesian model and sample counterfactual
            participants from the posterior — the paper’s exact approach.</p>
        </div>
        <div className={`choice ${path === "assumptions" ? "sel" : ""}`}
          onClick={() => setPath("assumptions")}>
          <h3>I’m designing from assumptions</h3>
          <p>No data needed. State the effects you expect and a spread, and we
            simulate participants from the same generative model — great for
            power analysis, pre-registration, or teaching.</p>
        </div>
      </div>

      <p className="hint" style={{ marginTop: 14 }}>
        {path === "posterior"
          ? "Next you’ll upload your CSV — we read it and set up the variables and "
            + "their distributions for you automatically."
          : "Next you’ll start from the paper’s worked example and adjust the "
            + "expected effects to match your assumptions."}
      </p>

      <div className="field" style={{ marginTop: 18, maxWidth: 360 }}>
        <label>Project name</label>
        <input type="text" value={name} onChange={(e) => setName(e.target.value)} />
      </div>

      {err && <div className="err">{err}</div>}
      <div className="actions">
        <span />
        <button className="primary" onClick={begin} disabled={busy}>
          {busy ? "Creating…" : "Begin →"}
        </button>
      </div>
    </div>
  );
}
