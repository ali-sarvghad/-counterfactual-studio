import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import { Explainer, Field } from "../components/ui.jsx";

const FAMILIES = [
  ["bernoulli", "Binary (Bernoulli) — correct/incorrect, yes/no"],
  ["lognormal", "Positive & skewed (Lognormal) — response time"],
  ["gaussian", "Symmetric continuous (Normal) — ratings, scores"],
  ["poisson", "Counts (Poisson) — clicks, errors"],
];

function FactorEditor({ factor, onChange, onRemove }) {
  const set = (k, v) => onChange({ ...factor, [k]: v });
  return (
    <div className="factor-row">
      <div className="grid3">
        <Field label="Factor name">
          <input type="text" value={factor.name}
            onChange={(e) => set("name", e.target.value)} />
        </Field>
        <Field label="Type">
          <select value={factor.kind || "categorical"}
            onChange={(e) => set("kind", e.target.value)}>
            <option value="categorical">Categorical</option>
            <option value="continuous">Continuous</option>
          </select>
        </Field>
        <Field label="Varies…">
          <select value={factor.role} onChange={(e) => set("role", e.target.value)}>
            <option value="within">Within each participant</option>
            <option value="between">Between participants</option>
          </select>
        </Field>
      </div>
      {(factor.kind || "categorical") === "categorical" && (
        <Field label="Levels (comma-separated)"
          hint="e.g. Bar, Line, Pie, Scatterplot, Table">
          <input type="text" value={(factor.levels || []).join(", ")}
            onChange={(e) =>
              set("levels", e.target.value.split(",").map((s) => s.trim()).filter(Boolean))} />
        </Field>
      )}
      <button className="ghost" onClick={onRemove}>Remove factor</button>
    </div>
  );
}

function OutcomeEditor({ outcome, onChange, onRemove }) {
  const set = (k, v) => onChange({ ...outcome, [k]: v });
  return (
    <div className="outcome-row">
      <div className="grid2">
        <Field label="Outcome name">
          <input type="text" value={outcome.name}
            onChange={(e) => set("name", e.target.value)} />
        </Field>
        <Field label="Measurement type">
          <select value={outcome.family}
            onChange={(e) => set("family", e.target.value)}>
            {FAMILIES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </Field>
      </div>
      <div className="grid2">
        {outcome.family === "bernoulli" && (
          <Field label="Guessing floor"
            hint="Chance of a correct guess. 0.25 for a 4-option question (the paper); 0 for none.">
            <input type="number" step="0.05" min="0" max="0.9"
              value={outcome.guess_rate ?? 0}
              onChange={(e) => set("guess_rate", parseFloat(e.target.value) || 0)} />
          </Field>
        )}
        <Field label="Trials per cell"
          hint="Questions asked per factor combination (the paper used 6).">
          <input type="number" min="1" value={outcome.trials_per_cell ?? 1}
            onChange={(e) => set("trials_per_cell", parseInt(e.target.value) || 1)} />
        </Field>
      </div>
      <button className="ghost" onClick={onRemove}>Remove outcome</button>
    </div>
  );
}

export function Design({ project, setProject, next, back }) {
  const [design, setDesign] = useState(project.design);
  const [validation, setValidation] = useState(null);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState(null);

  // live-validate (debounced) whenever the design changes
  useEffect(() => {
    const t = setTimeout(async () => {
      try {
        setValidation(await api.validate(design));
      } catch (e) {
        setValidation({ valid: false, error: e.message });
      }
    }, 350);
    return () => clearTimeout(t);
  }, [design]);

  const patch = (p) => setDesign((d) => ({ ...d, ...p }));
  const setFactor = (i, f) =>
    patch({ factors: design.factors.map((x, j) => (j === i ? f : x)) });
  const setOutcome = (i, o) =>
    patch({ outcomes: design.outcomes.map((x, j) => (j === i ? o : x)) });

  async function saveAndNext() {
    setSaving(true);
    setErr(null);
    try {
      const proj = await api.updateDesign(project.id, design);
      setProject(proj);
      next();
    } catch (e) {
      setErr(e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="panel">
      <h2>Define your study</h2>
      <p className="lead">A <b>factor</b> is something you vary (a chart type, a
        task). An <b>outcome</b> is what you measure (accuracy, time).</p>

      <Explainer>
        <b>Within vs between participants</b> is the key choice. A
        <b> within</b>-participant factor is one every person experiences at all
        levels (each person saw all five visualizations) — it can carry
        individual differences. A <b>between</b>-participant factor splits people
        into groups (each person had one task, one age group). It determines the
        random-effect structure of the model.
      </Explainer>

      <Field label="Participant identifier (grouping unit)">
        <input type="text" value={design.grouping}
          onChange={(e) => patch({ grouping: e.target.value })}
          style={{ maxWidth: 280 }} />
      </Field>

      <h3>Factors</h3>
      {design.factors.map((f, i) => (
        <FactorEditor key={i} factor={f} onChange={(x) => setFactor(i, x)}
          onRemove={() => patch({ factors: design.factors.filter((_, j) => j !== i) })} />
      ))}
      <button onClick={() => patch({
        factors: [...design.factors,
          { name: `factor${design.factors.length + 1}`, kind: "categorical",
            role: "within", levels: ["A", "B"] }] })}>
        + Add factor
      </button>

      <h3 style={{ marginTop: 20 }}>Outcomes</h3>
      {design.outcomes.map((o, i) => (
        <OutcomeEditor key={i} outcome={o} onChange={(x) => setOutcome(i, x)}
          onRemove={() => patch({ outcomes: design.outcomes.filter((_, j) => j !== i) })} />
      ))}
      <button onClick={() => patch({
        outcomes: [...design.outcomes,
          { name: `outcome${design.outcomes.length + 1}`, family: "gaussian",
            trials_per_cell: 1 }] })}>
        + Add outcome
      </button>

      <div className="panel" style={{ boxShadow: "none", marginTop: 20,
        background: "#fbfcfe" }}>
        <h3 style={{ marginTop: 0 }}>Model preview</h3>
        {validation && validation.valid ? (
          <>
            <p style={{ margin: "0 0 10px" }}>
              <b>{validation.n_cells}</b> factor combinations (cells). Each model:
            </p>
            {Object.entries(validation.formulas).map(([name, f]) => (
              <div key={name} style={{ marginBottom: 8 }}>
                <div><code>{f.bambi}</code></div>
                <div className="hint">
                  brms: <code>{f.brms}</code> · family <code>{f.brms_family}</code>
                  {f.fit_note ? ` — ${f.fit_note}` : ""}
                </div>
              </div>
            ))}
          </>
        ) : (
          <div className="err">{validation ? validation.error : "Validating…"}</div>
        )}
      </div>

      {err && <div className="err">{err}</div>}
      <div className="actions">
        <button onClick={back}>← Back</button>
        <button className="primary" onClick={saveAndNext}
          disabled={saving || !(validation && validation.valid)}>
          {saving ? "Saving…" : "Save & continue →"}
        </button>
      </div>
    </div>
  );
}
