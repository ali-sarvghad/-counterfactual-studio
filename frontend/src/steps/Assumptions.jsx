import React, { useMemo, useState } from "react";
import { api } from "../api.js";
import { Explainer, Field, Histogram, fmtByFamily } from "../components/ui.jsx";

const DEFAULT_MEAN = { bernoulli: 0.7, lognormal: 20, gaussian: 0, poisson: 5 };
const DEFAULT_BSD = 0.4;

function cartesian(factors) {
  // categorical factors only, in order -> list of {key, levels:{name:level}}
  const cats = factors.filter((f) => (f.kind || "categorical") === "categorical");
  let combos = [{}];
  for (const f of cats) {
    const nxt = [];
    for (const c of combos) for (const lv of f.levels) nxt.push({ ...c, [f.name]: lv });
    combos = nxt;
  }
  return combos.map((c) => ({
    levels: c,
    key: cats.map((f) => `${f.name}=${c[f.name]}`).join("|"),
  }));
}

function OutcomePreview({ outcome, mean, bsd }) {
  const [res, setRes] = useState(null);
  React.useEffect(() => {
    const t = setTimeout(async () => {
      setRes(await api.previewOutcome({
        family: outcome.family, guess_rate: outcome.guess_rate || 0,
        mean: Number(mean), between_sd: Number(bsd) }));
    }, 250);
    return () => clearTimeout(t);
  }, [mean, bsd, outcome.family]);
  if (!res) return null;
  return (
    <div>
      <Histogram samples={res.samples} fmt={fmtByFamily(outcome.family)} />
      <div className="hint">{res.explanation}</div>
    </div>
  );
}

export function Assumptions({ project, patchShared, next, back }) {
  const design = project.design;
  const cells = useMemo(() => cartesian(design.factors), [design]);

  const [means, setMeans] = useState(() => {
    const m = {};
    for (const o of design.outcomes) {
      m[o.name] = {};
      for (const c of cells) m[o.name][c.key] = DEFAULT_MEAN[o.family] ?? 1;
    }
    return m;
  });
  const [betweenSd, setBetweenSd] = useState(
    Object.fromEntries(design.outcomes.map((o) => [o.name, DEFAULT_BSD])));
  const [residualSd, setResidualSd] = useState(
    Object.fromEntries(design.outcomes.map((o) => [o.name, 0.3])));

  const fillAll = (oName, val) =>
    setMeans((m) => ({ ...m, [oName]: Object.fromEntries(
      cells.map((c) => [c.key, val])) }));
  const setCell = (oName, key, val) =>
    setMeans((m) => ({ ...m, [oName]: { ...m[oName], [key]: val } }));

  function proceed() {
    patchShared({
      assumptions: {
        cell_means: Object.fromEntries(design.outcomes.map((o) => [
          o.name, Object.fromEntries(Object.entries(means[o.name]).map(
            ([k, v]) => [k, Number(v)]))])),
        between_sd: betweenSd,
        residual_sd: residualSd,
      },
    });
    next();
  }

  const factorNames = design.factors
    .filter((f) => (f.kind || "categorical") === "categorical")
    .map((f) => f.name);

  return (
    <div className="panel">
      <h2>State your assumptions</h2>
      <p className="lead">Tell the tool what you expect for each factor
        combination. We’ll simulate participants from these — no data needed.</p>

      <Explainer>
        Two ingredients per outcome: the <b>expected value</b> in each cell, and
        the <b>between-participant spread</b> — how much individuals differ. A
        larger spread produces a more heterogeneous (realistic) population, just
        as the paper found for people in late adulthood. The previews below show
        exactly what your spread implies.
      </Explainer>

      {design.outcomes.map((o) => {
        const firstKey = cells[0].key;
        return (
          <div key={o.name} className="panel" style={{ boxShadow: "none",
            background: "#fbfcfe" }}>
            <h3 style={{ marginTop: 0 }}>{o.name} <span className="tag">{o.family}</span></h3>
            <div className="grid2">
              <Field label="Between-participant spread (link scale)"
                hint="How different individuals are. Bigger = more heterogeneous.">
                <input type="range" min="0" max="2" step="0.05"
                  value={betweenSd[o.name]}
                  onChange={(e) => setBetweenSd({ ...betweenSd,
                    [o.name]: parseFloat(e.target.value) })} />
                <span className="hint">{betweenSd[o.name]}</span>
              </Field>
              <Field label="Quick fill all cells with a value">
                <input type="number" step="any"
                  onChange={(e) => e.target.value !== "" &&
                    fillAll(o.name, parseFloat(e.target.value))}
                  placeholder={`e.g. ${DEFAULT_MEAN[o.family]}`} />
              </Field>
            </div>
            <OutcomePreview outcome={o} mean={means[o.name][firstKey]}
              bsd={betweenSd[o.name]} />

            <details style={{ marginTop: 8 }}>
              <summary>Per-cell expected values ({cells.length} cells)</summary>
              <div className="scroll" style={{ marginTop: 8 }}>
                <table className="data">
                  <thead><tr>
                    {factorNames.map((fn) => <th key={fn}>{fn}</th>)}
                    <th>expected {o.name}</th>
                  </tr></thead>
                  <tbody>
                    {cells.map((c) => (
                      <tr key={c.key}>
                        {factorNames.map((fn) => <td key={fn}>{c.levels[fn]}</td>)}
                        <td>
                          <input type="number" step="any"
                            value={means[o.name][c.key]}
                            onChange={(e) => setCell(o.name, c.key, e.target.value)}
                            style={{ width: 110 }} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          </div>
        );
      })}

      <div className="actions">
        <button onClick={back}>← Back</button>
        <button className="primary" onClick={proceed}>Continue to generate →</button>
      </div>
    </div>
  );
}
