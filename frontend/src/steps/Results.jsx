import React from "react";
import { api } from "../api.js";
import { DistRow, Explainer, fmtByFamily } from "../components/ui.jsx";

const ARTIFACT_LABELS = {
  "cell_means.csv": "Per-participant cell means (CSV)",
  "trials.csv": "Trial-level data (CSV)",
  "design.json": "Study design (JSON)",
  "bambi_fit.py": "Reproduce in Python (Bambi)",
  "brms_fit.R": "Reproduce in R (brms)",
  "reproducibility_report.md": "Reproducibility report (Markdown)",
};

function FactorChart({ outcomeName, family, factorName, rows }) {
  const fmt = fmtByFamily(family);
  const lo = Math.min(...rows.map((r) => r["p2.5"]));
  const hi = Math.max(...rows.map((r) => r["p97.5"]));
  const domain = [lo, hi];
  const color = outcomeName === "time" ? "#e8590c" : "#3b5bdb";
  return (
    <div style={{ marginBottom: 16 }}>
      <div className="hint" style={{ marginBottom: 4 }}>
        {outcomeName} by {factorName} — median bar, 50% &amp; 95% intervals
        (best first)
      </div>
      {rows.map((r) => (
        <DistRow key={r.level} label={r.level} block={r} domain={domain}
          fmt={fmt} color={color} />
      ))}
    </div>
  );
}

export function Results({ project, path, shared, back, goToStart }) {
  const gen = shared.generation;
  if (!gen) {
    return (
      <div className="panel">
        <h2>No results yet</h2>
        <p>Go back and generate participants first.</p>
        <div className="actions"><button onClick={back}>← Back</button><span /></div>
      </div>
    );
  }
  const outcomes = project.design.outcomes;
  const famOf = (name) => (outcomes.find((o) => o.name === name) || {}).family;

  return (
    <div className="panel">
      <h2>Your simulated participants</h2>
      <p className="lead">
        Generated <b>{gen.n_participants.toLocaleString()}</b> counterfactual
        participants across <b>{gen.n_cells}</b> cells
        ({gen.n_trials.toLocaleString()} trial rows), from{" "}
        {path === "posterior" ? "the fitted posterior" : "your assumptions"}.
      </p>

      <Explainer>
        Below is the distribution of per-participant means, aggregated by each
        factor — the same view as the paper’s Figures 2 &amp; 4. Wider intervals
        mean a more heterogeneous population.
      </Explainer>

      {Object.entries(gen.summary.outcomes).map(([oName, block]) => (
        <div key={oName} className="panel" style={{ boxShadow: "none",
          background: "#fbfcfe" }}>
          <h3 style={{ marginTop: 0 }}>{oName}</h3>
          {Object.entries(block.by_factor).map(([fName, rows]) => (
            <FactorChart key={fName} outcomeName={oName} family={famOf(oName)}
              factorName={fName} rows={rows} />
          ))}
        </div>
      ))}

      <h3>Preview: per-participant cell means</h3>
      <div className="scroll">
        <table className="data">
          <thead>
            <tr>{Object.keys(gen.cell_means_preview[0] || {}).map((c) =>
              <th key={c}>{c}</th>)}</tr>
          </thead>
          <tbody>
            {gen.cell_means_preview.map((row, i) => (
              <tr key={i}>{Object.values(row).map((v, j) =>
                <td key={j}>{typeof v === "number" ? v.toFixed(3) : String(v)}</td>)}</tr>
            ))}
          </tbody>
        </table>
      </div>

      <h3 style={{ marginTop: 18 }}>Download</h3>
      <div className="row">
        {gen.artifacts.map((a) => (
          <a key={a} href={api.downloadUrl(project.id, a)} download>
            <button>{ARTIFACT_LABELS[a] || a}</button>
          </a>
        ))}
      </div>

      <div className="actions">
        <button onClick={back}>← Back</button>
        <button className="ghost" onClick={goToStart}>Start a new simulation</button>
      </div>
    </div>
  );
}
