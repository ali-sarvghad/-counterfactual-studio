import React, { useState } from "react";
import { api } from "../api.js";
import { Explainer, Field, Spinner } from "../components/ui.jsx";

export function Generate({ project, path, shared, patchShared, next, back }) {
  const [n, setN] = useState(2000);
  const [seed, setSeed] = useState(7);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  async function run() {
    setBusy(true);
    setErr(null);
    try {
      const body = { source: path, n_participants: n, seed };
      if (path === "assumptions") {
        if (!shared.assumptions) throw new Error("Go back and set your assumptions first.");
        body.assumptions = shared.assumptions;
      }
      const res = await api.generate(project.id, body);
      patchShared({ generation: res });
      next();
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="panel">
      <h2>Generate counterfactual participants</h2>
      <p className="lead">
        {path === "posterior"
          ? "Each simulated participant is one draw from the fitted posterior, with a fresh individual effect — exactly the paper’s method."
          : "Each simulated participant is drawn from your stated generative model."}
      </p>

      <Explainer>
        You’ll get <b>two datasets</b>: per-participant <b>cell means</b> (one
        value per factor combination, what the paper analyzed) and <b>trial-level
        </b> rows (one per simulated question, like Table&nbsp;3). The paper
        generated 12,000 counterfactual participants; 2,000 is a fast, robust
        default here.
      </Explainer>

      <div className="grid2" style={{ maxWidth: 460 }}>
        <Field label="Number of counterfactual participants">
          <input type="number" min="10" max="20000" value={n}
            onChange={(e) => setN(parseInt(e.target.value) || 0)} />
        </Field>
        <Field label="Random seed" hint="Same seed ⇒ identical, reproducible output.">
          <input type="number" value={seed}
            onChange={(e) => setSeed(parseInt(e.target.value) || 0)} />
        </Field>
      </div>

      {err && <div className="err">{err}</div>}
      <div className="actions">
        <button onClick={back}>← Back</button>
        <button className="primary" onClick={run} disabled={busy}>
          {busy ? <Spinner label="Generating…" /> : "Generate →"}
        </button>
      </div>
    </div>
  );
}
