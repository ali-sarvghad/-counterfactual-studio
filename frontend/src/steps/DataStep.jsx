import React, { useState } from "react";
import { api } from "../api.js";
import { Explainer, Field, Spinner } from "../components/ui.jsx";

export function DataStep({ project, patchShared, next, back }) {
  const design = project.design;
  const roles = [design.grouping,
    ...design.factors.map((f) => f.name),
    ...design.outcomes.map((o) => o.name)];

  const [preview, setPreview] = useState(null);
  const [mapping, setMapping] = useState({});
  const [hampel, setHampel] = useState(false);
  const [busy, setBusy] = useState(false);
  const [committed, setCommitted] = useState(null);
  const [err, setErr] = useState(null);

  async function onFile(e) {
    const file = e.target.files[0];
    if (!file) return;
    setBusy(true);
    setErr(null);
    try {
      const p = await api.uploadData(project.id, file);
      setPreview(p);
      setMapping(p.suggested_mapping || {});
    } catch (e2) {
      setErr(e2.message);
    } finally {
      setBusy(false);
    }
  }

  async function commit() {
    setBusy(true);
    setErr(null);
    try {
      const r = await api.commitData(project.id, { mapping, apply_hampel: hampel });
      setCommitted(r);
      patchShared({ committed: true });
    } catch (e2) {
      setErr(e2.message);
    } finally {
      setBusy(false);
    }
  }

  const allMapped = roles.every((r) => mapping[r]);

  return (
    <div className="panel">
      <h2>Upload your data</h2>
      <p className="lead">Provide a CSV in <b>long format</b>: one row per trial,
        with a column for the participant, each factor, and each outcome.</p>

      <Explainer>
        Your data is only used to <b>fit</b> the model. The model then generates
        brand-new counterfactual participants — so your raw responses are never
        republished.
      </Explainer>

      <Field label="CSV file">
        <input type="file" accept=".csv,text/csv" onChange={onFile} />
      </Field>
      {busy && !preview && <Spinner label="Reading…" />}

      {preview && (
        <>
          <p><b>{preview.n_rows}</b> rows · {preview.columns.length} columns</p>
          <div className="scroll">
            <table className="data">
              <thead><tr>{preview.columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
              <tbody>
                {preview.rows.map((row, i) => (
                  <tr key={i}>{preview.columns.map((c) =>
                    <td key={c}>{String(row[c] ?? "")}</td>)}</tr>
                ))}
              </tbody>
            </table>
          </div>

          <h3 style={{ marginTop: 18 }}>Map your columns</h3>
          <p className="hint">Match each part of your design to a column in the file.</p>
          <div className="grid2">
            {roles.map((role) => (
              <Field key={role} label={role}>
                <select value={mapping[role] || ""}
                  onChange={(e) => setMapping({ ...mapping, [role]: e.target.value })}>
                  <option value="">— choose column —</option>
                  {preview.columns.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </Field>
            ))}
          </div>

          <label style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 6 }}>
            <input type="checkbox" checked={hampel}
              onChange={(e) => setHampel(e.target.checked)} style={{ width: "auto" }} />
            Apply a Hampel outlier filter to continuous outcomes (paper §4.1):
            drops trials beyond 3 MADs from the cell median.
          </label>

          <div style={{ marginTop: 14 }}>
            <button className="primary" onClick={commit} disabled={busy || !allMapped}>
              {busy ? "Committing…" : "Use this data"}
            </button>
            {!allMapped && <span className="hint" style={{ marginLeft: 10 }}>
              Map every field to continue.</span>}
          </div>

          {committed && (
            <div className="ok" style={{ marginTop: 10 }}>
              ✓ Committed {committed.n_rows} rows
              {committed.hampel && committed.hampel.removed > 0
                ? ` (Hampel removed ${committed.hampel.removed})` : ""}.
            </div>
          )}
        </>
      )}

      {err && <div className="err">{err}</div>}
      <div className="actions">
        <button onClick={back}>← Back</button>
        <button className="primary" onClick={next} disabled={!committed}>
          Continue to model &amp; fit →
        </button>
      </div>
    </div>
  );
}
