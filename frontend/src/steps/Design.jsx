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
  // Keep the raw text the user is typing so a trailing comma (mid-typing the
  // next level) isn't stripped by the parse-and-rejoin round trip.
  const [levelsText, setLevelsText] = useState((factor.levels || []).join(", "));
  const onLevels = (text) => {
    setLevelsText(text);
    set("levels", text.split(",").map((s) => s.trim()).filter(Boolean));
  };
  return (
    <div className="factor-row">
      <div className="grid3">
        <Field label="Factor name" tip={
          <><b>What you varied</b> in the study (e.g. visualization, task). It
          becomes a variable in the model, so use letters, numbers, or
          underscores — no spaces.</>}>
          <input type="text" value={factor.name}
            onChange={(e) => set("name", e.target.value)} />
        </Field>
        <Field label="Type" tip={
          <><b>Categorical</b> = a fixed set of named conditions (Bar, Line,
          Pie). <b>Continuous</b> = a number that varies smoothly (age in years,
          font size). Most experimental factors are categorical.</>}>
          <select value={factor.kind || "categorical"}
            onChange={(e) => set("kind", e.target.value)}>
            <option value="categorical">Categorical</option>
            <option value="continuous">Continuous</option>
          </select>
        </Field>
        <Field label="Varies…" tip={
          <><b>The most important choice here.</b> <b>Within</b> = every person
          experiences all levels (each saw all chart types). <b>Between</b> =
          each person is in only one level (one task, or one age group). It sets
          the model’s random-effect structure.</>}>
          <select value={factor.role} onChange={(e) => set("role", e.target.value)}>
            <option value="within">Within each participant</option>
            <option value="between">Between participants</option>
          </select>
        </Field>
      </div>
      {(factor.kind || "categorical") === "categorical" && (
        <Field label="Levels (comma-separated)"
          tip={<>The named conditions of this factor, separated by commas. Need
          at least two. Every counterfactual participant gets data at <b>every</b>
          level of a within-participant factor.</>}
          hint="e.g. Bar, Line, Pie, Scatterplot, Table">
          <input type="text" value={levelsText}
            onChange={(e) => onLevels(e.target.value)} />
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
        <Field label="Outcome name" tip={
          <><b>What you measured</b> (accuracy, time, errors). Becomes a variable
          in the model — letters, numbers, or underscores only.</>}>
          <input type="text" value={outcome.name}
            onChange={(e) => set("name", e.target.value)} />
        </Field>
        <Field label="Measurement type" tip={
          <>The kind of number this is, which sets the statistical distribution
          used to model it. <b>Binary</b> for correct/incorrect, <b>Positive &
          skewed</b> for response times, <b>Symmetric</b> for ratings/scores,
          <b> Counts</b> for errors or clicks. Pick what matches your measure.</>}>
          <select value={outcome.family}
            onChange={(e) => set("family", e.target.value)}>
            {FAMILIES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </Field>
      </div>
      <div className="grid2">
        {outcome.family === "bernoulli" && (
          <Field label="Guessing floor" tip={
            <>For multiple-choice tasks: the chance of getting it right by pure
            guessing. Accuracy can never fall below this floor. <b>Suggested:</b>
            {" "}0.25 for a 4-option question (the paper’s value), 0.5 for
            true/false, 0 if guessing isn’t possible.</>}
            hint="Chance of a correct guess. 0.25 for a 4-option question (the paper); 0 for none.">
            <input type="number" step="0.05" min="0" max="0.9"
              value={outcome.guess_rate ?? 0}
              onChange={(e) => set("guess_rate", parseFloat(e.target.value) || 0)} />
          </Field>
        )}
        <Field label="Trials per cell" tip={
          <>How many separate questions/observations each participant answers per
          combination of factor levels. More trials = less noise per simulated
          participant. <b>Suggested:</b> 6 (the paper’s value); use 1 if you
          model a single value per cell.</>}
          hint="Questions asked per factor combination (the paper used 6).">
          <input type="number" min="1" value={outcome.trials_per_cell ?? 1}
            onChange={(e) => set("trials_per_cell", parseInt(e.target.value) || 1)} />
        </Field>
      </div>
      <button className="ghost" onClick={onRemove}>Remove outcome</button>
    </div>
  );
}

export function Design({ project, setProject, next, back, path, shared }) {
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
      // Data path: re-apply the upload with the (possibly edited) design so the
      // fit sees data consistent with the confirmed variables and families.
      if (path === "posterior" && shared && shared.dataMapping) {
        await api.commitData(project.id, {
          mapping: shared.dataMapping, apply_hampel: !!shared.hampel });
      }
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

      {path === "posterior" && shared && shared.dataMapping && (
        <Explainer>
          We pre-filled this from your uploaded data — variable names,
          categories, and each outcome’s distribution. <b>Review and adjust</b>
          anything that looks off (especially whether each factor varies
          <i> within</i> or <i>between</i> participants), then continue.
        </Explainer>
      )}

      <Explainer>
        <b>Within vs between participants</b> is the key choice. A
        <b> within</b>-participant factor is one every person experiences at all
        levels (each person saw all five visualizations) — it can carry
        individual differences. A <b>between</b>-participant factor splits people
        into groups (each person had one task, one age group). It determines the
        random-effect structure of the model.
      </Explainer>

      <Field label="Participant identifier (grouping unit)" tip={
        <>The name of the unit you’re simulating — usually <b>participant</b>.
        Each counterfactual participant gets a full set of responses across your
        factors. Use letters, numbers, or underscores only.</>}>
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

      {design.factors.length >= 2 && (
        <Field label="How factors combine" tip={
          <><b>Main effects only</b> models each factor on its own — simplest and
          safest, and it always fits. <b>Two-way</b> and <b>Full</b> also estimate
          how factors interact, which is richer but needs data in <i>every</i>
          combination; with limited data those can fail to fit. The fit screen
          checks this for you before running. <b>Suggested:</b> main effects
          unless you specifically need interactions and have plenty of data.</>}>
          <select
            value={(design.interaction_order === null
              || design.interaction_order === undefined
              || design.interaction_order >= design.factors.length)
              ? "full" : String(design.interaction_order)}
            onChange={(e) => patch({ interaction_order:
              e.target.value === "full" ? null : Number(e.target.value) })}
            style={{ maxWidth: 360 }}>
            <option value="0">Main effects only (simplest, always fits)</option>
            <option value="1">Two-way interactions</option>
            <option value="full">Full interaction (every combination)</option>
          </select>
        </Field>
      )}

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
