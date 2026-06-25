import React, { useState } from "react";
import { Concept } from "./steps/Concept.jsx";
import { Design } from "./steps/Design.jsx";
import { DataStep } from "./steps/DataStep.jsx";
import { FitStep } from "./steps/FitStep.jsx";
import { Assumptions } from "./steps/Assumptions.jsx";
import { Generate } from "./steps/Generate.jsx";
import { Results } from "./steps/Results.jsx";

// Step flows differ by path. Each entry: { key, title, Component }.
const FLOWS = {
  posterior: [
    { key: "concept", title: "Start", C: Concept },
    { key: "data", title: "Data", C: DataStep },
    { key: "design", title: "Design", C: Design },
    { key: "fit", title: "Model & fit", C: FitStep },
    { key: "generate", title: "Generate", C: Generate },
    { key: "results", title: "Results", C: Results },
  ],
  assumptions: [
    { key: "concept", title: "Start", C: Concept },
    { key: "design", title: "Design", C: Design },
    { key: "assume", title: "Assumptions", C: Assumptions },
    { key: "generate", title: "Generate", C: Generate },
    { key: "results", title: "Results", C: Results },
  ],
};

function Stepper({ steps, current, maxReached, onJump }) {
  return (
    <div className="stepper">
      {steps.map((s, i) => {
        const cls = i === current ? "active" : i <= maxReached ? "done" : "";
        return (
          <div key={s.key} className={`step ${cls}`}
            onClick={() => i <= maxReached && onJump(i)}>
            <span className="n">{i + 1}</span>
            {s.title}
          </div>
        );
      })}
    </div>
  );
}

export default function App() {
  const [path, setPath] = useState("posterior");
  const [project, setProject] = useState(null); // {id, design, status, ...}
  const [step, setStep] = useState(0);
  const [maxReached, setMaxReached] = useState(0);
  // shared scratch state carried across steps
  const [shared, setShared] = useState({}); // {generation, fitDiagnostics, ...}

  const steps = FLOWS[path];
  const Current = steps[step].C;

  const go = (i) => {
    const clamped = Math.max(0, Math.min(steps.length - 1, i));
    setStep(clamped);
    setMaxReached((m) => Math.max(m, clamped));
  };

  const ctx = {
    path, setPath,
    project, setProject,
    shared, setShared,
    patchShared: (p) => setShared((s) => ({ ...s, ...p })),
    next: () => go(step + 1),
    back: () => go(step - 1),
    goToStart: () => { setStep(0); },
  };

  return (
    <div className="app">
      <div className="appbar">
        <h1>Counterfactual Participant Studio</h1>
        <span className="sub">simulate study participants · method after While &amp; Sarvghad, CHI&nbsp;’25</span>
      </div>
      <Stepper steps={steps} current={step} maxReached={maxReached} onJump={go} />
      <Current {...ctx} />
    </div>
  );
}
