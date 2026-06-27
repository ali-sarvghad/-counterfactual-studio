import React, { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { Badge, Explainer, Field, Histogram, InfoTip, Spinner, fmtByFamily } from "../components/ui.jsx";

// Plain-language help for the convergence diagnostics, including how to act.
const DIAG_TIP = (
  <>These three numbers check whether the MCMC sampler reliably explored the
  model. A green <b>OK</b> badge means all good; <b>WARN</b> means borderline —
  fine for a look, but improve the fit before relying on it; <b>FAIL</b> means
  don’t trust it yet. Hover each number to see how to handle it.</>
);
const RHAT_TIP = (
  <><b>R-hat</b> measures agreement between the independent sampler chains.
  <b> Below 1.01</b> is good; 1.01–1.05 is borderline; above 1.05 means the
  chains disagree and it hasn’t converged. <b>Fix:</b> raise <i>tune</i> and
  <i> draws</i>, or simplify the design, then re-fit.</>
);
const ESS_TIP = (
  <><b>Effective sample size</b> is how much independent information you have for
  the hardest-to-estimate parameter — <b>higher is better</b>. A few hundred is
  usually enough; very low means noisy estimates. <b>Fix:</b> increase
  <i> draws</i> (and <i>tune</i>).</>
);
const DIV_TIP = (
  <><b>Divergences</b> are steps where the sampler hit numerical trouble and may
  have missed part of the distribution. <b>0 is ideal</b>; a few is usually
  tolerable; many makes results untrustworthy. <b>Fix:</b> raise
  <i> target_accept</i> toward 0.95–0.99, use tighter priors, or simplify the
  model.</>
);
const SAMPLER_TIPS = {
  draws: (<>Posterior samples kept <b>per chain</b> after warm-up. More =
    smoother, more reliable estimates but slower. <b>Suggested:</b> 1000 (lower
    to ~500 for a quick trial).</>),
  tune: (<>Warm-up steps the sampler uses to calibrate itself, then discards.
    More tuning helps convergence (lower R-hat, fewer divergences).
    <b> Suggested:</b> 1000.</>),
  chains: (<>Independent sampler runs started from different points; comparing
    them is how R-hat detects trouble. <b>Suggested:</b> 4 (or 2 for a quick
    trial).</>),
  seed: (<>Fixes the random numbers so the fit is exactly reproducible. Any
    integer works. <b>Suggested:</b> 1234.</>),
};

// Weakly-informed defaults matching the paper (logit and log scales).
const DEFAULT_PRIOR = { bernoulli: [0, 1], lognormal: [3.4, 1], gaussian: [0, 5], poisson: [1, 1] };

function PriorPreview({ outcome }) {
  const [m, setM] = useState(DEFAULT_PRIOR[outcome.family]?.[0] ?? 0);
  const [s, setS] = useState(DEFAULT_PRIOR[outcome.family]?.[1] ?? 1);
  const [res, setRes] = useState(null);
  useEffect(() => {
    const t = setTimeout(async () => {
      setRes(await api.previewPrior({
        family: outcome.family, guess_rate: outcome.guess_rate || 0,
        prior_mean: m, prior_sd: s }));
    }, 250);
    return () => clearTimeout(t);
  }, [m, s, outcome.family]);
  const fmt = fmtByFamily(outcome.family);
  return (
    <div style={{ marginBottom: 16 }}>
      <b>{outcome.name}</b> <span className="tag">{outcome.family}</span>
      <div className="grid2" style={{ marginTop: 6 }}>
        <Field label={`Prior mean (link scale): ${m}`}>
          <input type="range" min="-2" max="6" step="0.1" value={m}
            onChange={(e) => setM(parseFloat(e.target.value))} />
        </Field>
        <Field label={`Prior spread: ${s}`}>
          <input type="range" min="0.2" max="3" step="0.1" value={s}
            onChange={(e) => setS(parseFloat(e.target.value))} />
        </Field>
      </div>
      {res && <>
        <Histogram samples={res.samples} fmt={fmt} />
        <div className="hint">{res.explanation}</div>
      </>}
    </div>
  );
}

export function FitStep({ project, setProject, shared, patchShared, next, back }) {
  const design = project.design;
  const [formulas, setFormulas] = useState(null);
  const [settings, setSettings] = useState({ draws: 1000, tune: 1000, chains: 4, seed: 1234 });
  const [status, setStatus] = useState(project.status === "fitted" ? "fitted" : "idle");
  const [diag, setDiag] = useState(shared.fitDiagnostics || null);
  const [elapsed, setElapsed] = useState(0);
  const [err, setErr] = useState(null);
  const [pf, setPf] = useState(null);
  const [fixing, setFixing] = useState(false);
  const poll = useRef(null);
  const timer = useRef(null);

  function runPreflight() {
    api.preflight(project.id).then(setPf).catch(() => setPf(null));
  }

  useEffect(() => {
    api.validate(design).then((v) => setFormulas(v.formulas)).catch(() => {});
    runPreflight();
    return () => { clearInterval(poll.current); clearInterval(timer.current); };
  }, []);

  async function applyFix(fix) {
    setFixing(true);
    try {
      const next = { ...project.design, interaction_order: fix.value };
      const proj = await api.updateDesign(project.id, next);
      setProject(proj);
      api.validate(next).then((v) => setFormulas(v.formulas)).catch(() => {});
      const res = await api.preflight(project.id);
      setPf(res);
    } catch (e) {
      setErr(e.message);
    } finally {
      setFixing(false);
    }
  }

  const blocked = pf && pf.ok === false;

  async function startFit() {
    setErr(null);
    setDiag(null);
    setStatus("fitting");
    setElapsed(0);
    try {
      await api.startFit(project.id, settings);
      timer.current = setInterval(() => setElapsed((e) => e + 1), 1000);
      poll.current = setInterval(async () => {
        const st = await api.fitStatus(project.id);
        if (st.status === "fitted" || st.status === "failed") {
          clearInterval(poll.current);
          clearInterval(timer.current);
          setStatus(st.status);
          if (st.status === "fitted") {
            setDiag(st.diagnostics);
            patchShared({ fitDiagnostics: st.diagnostics });
          } else {
            setErr(st.error || "Fit failed.");
          }
        }
      }, 1500);
    } catch (e) {
      setStatus("idle");
      setErr(e.message);
    }
  }

  return (
    <div className="panel">
      <h2>Model &amp; fit</h2>
      <p className="lead">We model each outcome with the interaction of your
        factors plus participant-level effects, then fit it with MCMC.</p>

      {formulas && (
        <div className="panel" style={{ boxShadow: "none", background: "#fbfcfe" }}>
          <h3 style={{ marginTop: 0 }}>Your models</h3>
          {Object.entries(formulas).map(([n, f]) => (
            <div key={n} style={{ marginBottom: 6 }}>
              <code>{f.bambi}</code>
              {f.fit_note && <div className="hint">{f.fit_note}</div>}
            </div>
          ))}
        </div>
      )}

      {pf && pf.issues && pf.issues.length > 0 && (
        <div style={{ marginTop: 6 }}>
          {pf.issues.map((iss, i) => (
            <div key={i} className={`preflight ${iss.severity}`}>
              <div className="preflight-title">
                {iss.severity === "error" ? "⛔" : "⚠️"} {iss.title}
              </div>
              <div style={{ marginTop: 4 }}>{iss.detail}</div>
              <ul className="preflight-sugg">
                {iss.suggestions.map((s, j) => <li key={j}>{s}</li>)}
              </ul>
              {iss.fix && (
                <button className="primary" onClick={() => applyFix(iss.fix)}
                  disabled={fixing}>
                  {fixing ? "Applying…" : iss.fix.label}
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      <h3>Understand your priors</h3>
      <Explainer>
        Priors say what’s plausible <i>before</i> seeing data. The paper used
        weakly-informed priors so the data dominates. Drag the sliders to see how
        a prior on the model’s link scale translates into real outcome values —
        this is the reasoning behind the paper’s prior choices. The fit itself
        uses these weakly-informed defaults.
      </Explainer>
      {design.outcomes.map((o) => <PriorPreview key={o.name} outcome={o} />)}

      <h3>Sampler settings</h3>
      <div className="grid2">
        {["draws", "tune", "chains", "seed"].map((k) => (
          <Field key={k} label={k} tip={SAMPLER_TIPS[k]}>
            <input type="number" value={settings[k]}
              onChange={(e) => setSettings({ ...settings, [k]: parseInt(e.target.value) || 0 })} />
          </Field>
        ))}
      </div>
      <div className="hint">More draws/chains = more reliable but slower. Defaults
        mirror a robust run; lower them for a quick trial.</div>

      <div style={{ marginTop: 14 }}>
        <button className="primary" onClick={startFit}
          disabled={status === "fitting" || blocked || fixing}>
          {status === "fitting" ? <Spinner label={`Fitting… ${elapsed}s`} /> : "Fit the model"}
        </button>
        {status === "fitting" && <span className="hint" style={{ marginLeft: 10 }}>
          MCMC can take a few minutes for large designs.</span>}
        {blocked && status !== "fitting" && <span className="hint" style={{ marginLeft: 10 }}>
          Resolve the issue above before fitting.</span>}
      </div>

      {diag && (
        <div style={{ marginTop: 16 }}>
          <h3>Convergence diagnostics <InfoTip>{DIAG_TIP}</InfoTip></h3>
          {Object.entries(diag).map(([n, d]) => (
            <div key={n} style={{ marginBottom: 8 }}>
              <b>{n}</b> <Badge status={d.status}>{d.status.toUpperCase()}</Badge>
              <span className="hint" style={{ marginLeft: 8 }}>
                max R̂<InfoTip>{RHAT_TIP}</InfoTip> {d.max_rhat.toFixed(3)} ·
                min ESS<InfoTip>{ESS_TIP}</InfoTip> {Math.round(d.min_ess_bulk)} ·
                divergences<InfoTip>{DIV_TIP}</InfoTip> {d.n_divergences}
              </span>
              <div className="hint">{d.interpretation}</div>
            </div>
          ))}
        </div>
      )}

      {err && <div className="err" style={{ whiteSpace: "pre-wrap" }}>{err}</div>}
      <div className="actions">
        <button onClick={back}>← Back</button>
        <button className="primary" onClick={next} disabled={status !== "fitted"}>
          Continue to generate →
        </button>
      </div>
    </div>
  );
}
