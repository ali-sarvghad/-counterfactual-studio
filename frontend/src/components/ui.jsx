import React from "react";

export function Explainer({ children }) {
  return <div className="explainer">{children}</div>;
}

export function Field({ label, hint, children }) {
  return (
    <div className="field">
      {label && <label>{label}</label>}
      {children}
      {hint && <div className="hint">{hint}</div>}
    </div>
  );
}

export function Badge({ status, children }) {
  return <span className={`badge ${status}`}>{children}</span>;
}

export function Spinner({ label }) {
  return (
    <span>
      <span className="spin" />
      {label}
    </span>
  );
}

// A compact SVG histogram for the "what does this imply?" previews.
export function Histogram({ samples, bins = 22, fmt = (x) => x, width = 360, height = 90 }) {
  if (!samples || samples.length === 0) return null;
  const lo = Math.min(...samples);
  const hi = Math.max(...samples);
  const span = hi - lo || 1;
  const counts = new Array(bins).fill(0);
  for (const s of samples) {
    let b = Math.floor(((s - lo) / span) * bins);
    if (b >= bins) b = bins - 1;
    if (b < 0) b = 0;
    counts[b] += 1;
  }
  const maxc = Math.max(...counts) || 1;
  const bw = width / bins;
  return (
    <svg width="100%" viewBox={`0 0 ${width} ${height + 18}`} role="img">
      {counts.map((c, i) => {
        const h = (c / maxc) * height;
        return (
          <rect key={i} x={i * bw + 1} y={height - h} width={bw - 1.5} height={h}
            fill="#3b5bdb" opacity="0.78" rx="1.5" />
        );
      })}
      <line x1="0" y1={height} x2={width} y2={height} stroke="#c9d0e0" />
      <text x="0" y={height + 14} fontSize="11" fill="#5b6472">{fmt(lo)}</text>
      <text x={width} y={height + 14} fontSize="11" fill="#5b6472" textAnchor="end">
        {fmt(hi)}
      </text>
    </svg>
  );
}

// One row of a paper-style distribution summary: a bar from p2.5..p97.5 with
// ticks at the 66th/95th and a marker at the median.
export function DistRow({ label, block, domain, fmt = (x) => x, color = "#3b5bdb" }) {
  const [d0, d1] = domain;
  const span = d1 - d0 || 1;
  const x = (v) => `${((v - d0) / span) * 100}%`;
  return (
    <div className="dist-row">
      <div className="dist-label">{label}</div>
      <div style={{ position: "relative", height: 16 }}>
        <div style={{ position: "absolute", top: 7, left: 0, right: 0, height: 2,
          background: "#eef1f7" }} />
        <div style={{ position: "absolute", top: 5, left: x(block["p2.5"]),
          width: `calc(${x(block["p97.5"])} - ${x(block["p2.5"])})`, height: 6,
          background: color, opacity: 0.25, borderRadius: 3 }} />
        <div style={{ position: "absolute", top: 3, left: x(block.p25),
          width: `calc(${x(block.p75)} - ${x(block.p25)})`, height: 10,
          background: color, opacity: 0.5, borderRadius: 3 }} />
        <div style={{ position: "absolute", top: 1, left: `calc(${x(block.p50)} - 1px)`,
          width: 3, height: 14, background: color, borderRadius: 2 }} />
      </div>
      <div className="dist-val">{fmt(block.p50)}</div>
    </div>
  );
}

export function fmtByFamily(family) {
  if (family === "bernoulli") return (x) => `${(x * 100).toFixed(0)}%`;
  if (family === "lognormal") return (x) => `${x.toFixed(1)}s`;
  return (x) => x.toFixed(2);
}
