import React, { useState } from "react";
import { api } from "../api.js";
import { Explainer, Field, Histogram, Spinner, fmtByFamily } from "../components/ui.jsx";

// Distribution families, with the same plain-language labels as the Design step.
const FAMILIES = [
  ["bernoulli", "Binary (Bernoulli) — correct/incorrect, yes/no"],
  ["lognormal", "Positive & skewed (Lognormal) — response time"],
  ["gaussian", "Symmetric continuous (Normal) — ratings, scores"],
  ["poisson", "Counts (Poisson) — clicks, errors"],
];

const ROLE_LABEL = {
  participant: "Participant",
  factor: "Factor (something you varied)",
  outcome: "Outcome (something you measured)",
  ignore: "Ignore this column",
};

// Which roles a column can take, given what its values look like.
function roleOptions(col) {
  const opts = [];
  if (col.numeric) opts.push("outcome");
  if (col.candidate_levels && col.candidate_levels.length >= 2) opts.push("factor");
  opts.push("ignore");
  return opts;
}

function defaultRole(col) {
  if (col.role && col.role !== "participant") return col.role;
  if (col.candidate_levels && col.candidate_levels.length >= 2) return "factor";
  if (col.numeric) return "outcome";
  return "ignore";
}

function ColumnCard({ col, role, family, onRole, onFamily }) {
  const opts = roleOptions(col);
  return (
    <div className="factor-row">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <b>{col.original}</b>
        <span className="hint">{col.n_unique} distinct
          {col.n_missing ? ` · ${col.n_missing} missing` : ""}</span>
      </div>
      <div className="hint" style={{ margin: "2px 0 8px" }}>{col.reason}</div>

      <div className="grid2">
        <Field label="This column is…">
          <select value={role} onChange={(e) => onRole(e.target.value)}>
            {opts.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
          </select>
        </Field>
        {role === "outcome" && (
          <Field label="Distribution (auto-detected)"
            hint="This is the shape we recognized — change it if you know better.">
            <select value={family} onChange={(e) => onFamily(e.target.value)}>
              {FAMILIES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </Field>
        )}
      </div>

      {role === "outcome" && col.samples && (
        <div style={{ marginTop: 4 }}>
          <div className="hint">Shape of your <b>{col.original}</b> values:</div>
          <Histogram samples={col.samples} fmt={fmtByFamily(family)} />
        </div>
      )}
      {role === "factor" && col.candidate_levels && (
        <div style={{ marginTop: 4 }}>
          <span className="hint">Levels: </span>
          {col.candidate_levels.slice(0, 12).map((lv) => (
            <span key={lv} className="tag" style={{ marginRight: 4 }}>{lv}</span>
          ))}
          {col.candidate_levels.length > 12 &&
            <span className="hint">+{col.candidate_levels.length - 12} more</span>}
        </div>
      )}
    </div>
  );
}

export function DataStep({ project, setProject, patchShared, next, back }) {
  const [preview, setPreview] = useState(null);
  const [cols, setCols] = useState(null);       // profiled column entries
  const [participant, setParticipant] = useState(null); // original col name
  const [roles, setRoles] = useState({});       // original -> role
  const [families, setFamilies] = useState({}); // original -> family
  const [hampel, setHampel] = useState(false);
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState(null);

  async function onFile(e) {
    const file = e.target.files[0];
    if (!file) return;
    setBusy(true);
    setErr(null);
    setCols(null);
    try {
      const p = await api.uploadData(project.id, file);
      setPreview(p);
      const prof = await api.profileData(project.id);
      setCols(prof.columns);
      const part = prof.columns.find((c) => c.role === "participant");
      setParticipant(part ? part.original : null);
      const r = {}, fam = {};
      for (const c of prof.columns) {
        r[c.original] = c.role;
        if (c.family) fam[c.original] = c.family;
      }
      setRoles(r);
      setFamilies(fam);
    } catch (e2) {
      setErr(e2.message);
    } finally {
      setBusy(false);
    }
  }

  function chooseParticipant(original) {
    setParticipant(original);
    setRoles((prev) => {
      const r = { ...prev };
      for (const c of cols) {
        if (c.original === original) r[c.original] = "participant";
        else if (r[c.original] === "participant") r[c.original] = defaultRole(c);
      }
      return r;
    });
  }

  function buildDesignAndMapping() {
    const partCol = cols.find((c) => c.original === participant);
    const mapping = { [partCol.name]: partCol.original };
    const factors = [];
    const outcomes = [];
    for (const c of cols) {
      if (c.original === participant) continue;
      const role = roles[c.original];
      if (role === "factor") {
        factors.push({ name: c.name, label: c.original, kind: "categorical",
          role: "within", levels: c.candidate_levels || [] });
        mapping[c.name] = c.original;
      } else if (role === "outcome") {
        outcomes.push({ name: c.name, family: families[c.original] || "gaussian",
          label: c.original, guess_rate: 0, trials_per_cell: 1 });
        mapping[c.name] = c.original;
      }
    }
    const design = {
      name: "Detected from your data",
      grouping: partCol.name,
      factors,
      outcomes,
      interaction_order: factors.length <= 2 ? null : 1,
      drop_intercept: true,
      description: "Inferred from your uploaded CSV — confirm on the next screen.",
    };
    return { design, mapping };
  }

  async function useDataAndContinue() {
    if (!participant) { setErr("Choose which column identifies the participant."); return; }
    setSaving(true);
    setErr(null);
    try {
      const { design, mapping } = buildDesignAndMapping();
      const proj = await api.updateDesign(project.id, design);
      setProject(proj);
      await api.commitData(project.id, { mapping, apply_hampel: hampel });
      patchShared({ dataMapping: mapping, hampel, committed: true });
      next();
    } catch (e2) {
      setErr(e2.message);
    } finally {
      setSaving(false);
    }
  }

  const otherCols = cols ? cols.filter((c) => c.original !== participant) : [];

  return (
    <div className="panel">
      <h2>Upload your data</h2>
      <p className="lead">Provide a CSV in <b>long format</b>: one row per trial,
        with a column for the participant, each factor, and each outcome.</p>

      <Explainer>
        As soon as you upload, we read every column and <b>figure out the
        statistics for you</b> — which column is the participant, which are the
        things you varied, which are what you measured, and the right probability
        distribution for each outcome (with a picture of its shape). You just
        confirm. Your raw data is only used to fit the model.
      </Explainer>

      <Field label="CSV file">
        <input type="file" accept=".csv,text/csv" onChange={onFile} />
      </Field>
      {busy && <Spinner label="Reading and analyzing your data…" />}

      {preview && cols && (
        <>
          <p style={{ marginTop: 12 }}><b>{preview.n_rows}</b> rows ·
            {" "}{preview.columns.length} columns</p>
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

          <h3 style={{ marginTop: 18 }}>Here’s what we detected</h3>
          <Field label="Participant / grouping column"
            hint="The column that identifies who produced each row.">
            <select value={participant || ""}
              onChange={(e) => chooseParticipant(e.target.value)}>
              <option value="">— choose column —</option>
              {cols.map((c) => <option key={c.original} value={c.original}>{c.original}</option>)}
            </select>
          </Field>

          <div style={{ marginTop: 10 }}>
            {otherCols.map((c) => (
              <ColumnCard key={c.original} col={c}
                role={roles[c.original]} family={families[c.original] || "gaussian"}
                onRole={(r) => setRoles({ ...roles, [c.original]: r })}
                onFamily={(f) => setFamilies({ ...families, [c.original]: f })} />
            ))}
          </div>

          <label style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 10 }}>
            <input type="checkbox" checked={hampel}
              onChange={(e) => setHampel(e.target.checked)} style={{ width: "auto" }} />
            Apply a Hampel outlier filter to continuous outcomes (paper §4.1):
            drops trials beyond 3 MADs from the cell median.
          </label>
        </>
      )}

      {err && <div className="err">{err}</div>}
      <div className="actions">
        <button onClick={back}>← Back</button>
        <button className="primary" onClick={useDataAndContinue}
          disabled={!cols || saving}>
          {saving ? "Saving…" : "Use this data & continue →"}
        </button>
      </div>
    </div>
  );
}
