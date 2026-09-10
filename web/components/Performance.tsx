"use client";

// Portfolio vs SOXX / SPY / QQQ since the study started, all rebased to 0% on the first day.
import { useState } from "react";

type Point = { t: number; v: number };            // Alpaca portfolio history (unix seconds, equity)
type Series = Record<string, [string, number][]>; // benchmark closes by date

const W = 800, H = 240, PAD = { l: 52, r: 12, t: 14, b: 24 };
const COLORS: Record<string, string> = { Portfolio: "var(--line)", SOXX: "var(--down)", SPY: "var(--ink-3)", QQQ: "var(--up)" };

const pct = (v: number) => `${v >= 0 ? "+" : ""}${(v * 100).toFixed(2)}%`;
const day = (iso: string) => new Date(iso + "T00:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" });

export default function Performance({ equity, benchmarks, startDate }: { equity: Point[]; benchmarks: Series; startDate: string }) {
  const [hover, setHover] = useState<number | null>(null);

  // Portfolio: one value per calendar day (ISO), rebased to the first day of the study.
  const eq = new Map<string, number>();
  for (const p of equity) eq.set(new Date(p.t * 1000).toISOString().slice(0, 10), p.v);
  const dates = [...new Set([...eq.keys(), ...Object.values(benchmarks).flat().map(([d]) => d)])]
    .filter((d) => d >= startDate).sort();
  if (dates.length < 2) return <div className="empty">Not enough history yet — the comparison starts after the first full trading day</div>;

  const lines: Record<string, (number | null)[]> = {};
  const base = (arr: [string, number][]) => arr.find(([d]) => d >= startDate)?.[1];
  const eqBase = dates.map((d) => eq.get(d)).find((v) => v != null);
  lines.Portfolio = dates.map((d) => (eq.has(d) && eqBase ? eq.get(d)! / eqBase - 1 : null));
  for (const [name, arr] of Object.entries(benchmarks)) {
    const b = base(arr);
    const m = new Map(arr);
    lines[name] = dates.map((d) => (b && m.has(d) ? m.get(d)! / b - 1 : null));
  }
  const all = Object.values(lines).flat().filter((v): v is number => v != null);
  let y0 = Math.min(0, ...all), y1 = Math.max(0, ...all);
  const padY = (y1 - y0 || 0.01) * 0.1; y0 -= padY; y1 += padY;
  const X = (i: number) => PAD.l + (i / (dates.length - 1)) * (W - PAD.l - PAD.r);
  const Y = (v: number) => PAD.t + (1 - (v - y0) / (y1 - y0)) * (H - PAD.t - PAD.b);
  const path = (arr: (number | null)[]) => {
    let d = "", pen = false;
    arr.forEach((v, i) => { if (v == null) { pen = false; return; } d += `${pen ? "L" : "M"}${X(i).toFixed(1)},${Y(v).toFixed(1)} `; pen = true; });
    return d;
  };
  const latest = (arr: (number | null)[]) => [...arr].reverse().find((v) => v != null) ?? null;
  const yTicks = [0, 0.5, 1].map((f) => y0 + f * (y1 - y0));
  const hi = hover != null ? Math.max(0, Math.min(dates.length - 1, hover)) : null;

  return (
    <div>
      <div className="tiles" style={{ marginBottom: 10 }}>
        {Object.entries(lines).map(([name, arr]) => {
          const v = latest(arr);
          return (
            <div className="tile" key={name}>
              <div className="label" style={{ color: COLORS[name] }}>{name}</div>
              <div className={`value ${v != null && v < 0 ? "down" : "up"}`}>{v == null ? "—" : pct(v)}</div>
              <div className="delta muted">since {day(startDate)}</div>
            </div>
          );
        })}
      </div>
      <div className="chart-wrap">
        <svg className="chart" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none"
          onMouseMove={(e) => {
            const r = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
            const x = ((e.clientX - r.left) / r.width) * W;
            setHover(Math.round(((x - PAD.l) / (W - PAD.l - PAD.r)) * (dates.length - 1)));
          }}
          onMouseLeave={() => setHover(null)}>
          {yTicks.map((v) => (
            <g key={v}>
              <line className="grid" x1={PAD.l} x2={W - PAD.r} y1={Y(v)} y2={Y(v)} />
              <text className="axis" x={PAD.l - 6} y={Y(v) + 4} textAnchor="end">{pct(v)}</text>
            </g>
          ))}
          <line className="grid" x1={PAD.l} x2={W - PAD.r} y1={Y(0)} y2={Y(0)} style={{ strokeDasharray: "3 3" }} />
          {Object.entries(lines).map(([name, arr]) => (
            <path key={name} d={path(arr)} fill="none" stroke={COLORS[name]} strokeWidth={name === "Portfolio" ? 2.2 : 1.4}
              strokeLinejoin="round" opacity={name === "Portfolio" ? 1 : 0.85} />
          ))}
          {hi != null && <line className="cross" x1={X(hi)} x2={X(hi)} y1={PAD.t} y2={H - PAD.b} />}
          {[0, Math.floor((dates.length - 1) / 2), dates.length - 1].map((i) => (
            <text key={i} className="axis" x={X(i)} y={H - 6} textAnchor={i === 0 ? "start" : i === dates.length - 1 ? "end" : "middle"}>{day(dates[i])}</text>
          ))}
        </svg>
        {hi != null && (
          <div className="tip" style={{ left: `${(X(hi) / W) * 100}%`, top: 0 }}>
            {day(dates[hi])} · {Object.entries(lines).map(([n, arr]) => `${n} ${arr[hi] == null ? "—" : pct(arr[hi]!)}`).join(" · ")}
          </div>
        )}
      </div>
    </div>
  );
}
