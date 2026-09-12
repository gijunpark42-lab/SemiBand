"use client";

import { useEffect, useRef, useState } from "react";

type Point = { t: number; v: number };

const H = 220, PAD = { l: 86, r: 12, t: 12, b: 24 };

const money = (v: number) =>
  v.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
const day = (t: number) =>
  new Date(t * 1000).toLocaleDateString("en-US", { timeZone: "America/New_York", month: "short", day: "numeric" });

export default function EquityChart({ points }: { points: Point[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const [W, setWidth] = useState(800);
  const chart = useRef<HTMLDivElement>(null);
  const hasHistory = points.length >= 2;
  useEffect(() => {
    if (!chart.current) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(280, Math.round(entry.contentRect.width))));
    observer.observe(chart.current);
    return () => observer.disconnect();
  }, [hasHistory]);
  if (points.length < 2) return <div className="empty">Not enough history yet</div>;

  const xs = points.map((p) => p.t), ys = points.map((p) => p.v);
  const x0 = Math.min(...xs), x1 = Math.max(...xs);
  let y0 = Math.min(...ys), y1 = Math.max(...ys);
  const padY = (y1 - y0 || y1 * 0.01) * 0.1;
  y0 -= padY; y1 += padY;

  const X = (t: number) => PAD.l + ((t - x0) / (x1 - x0)) * (W - PAD.l - PAD.r);
  const Y = (v: number) => PAD.t + (1 - (v - y0) / (y1 - y0)) * (H - PAD.t - PAD.b);
  const path = points.map((p, i) => `${i ? "L" : "M"}${X(p.t).toFixed(1)},${Y(p.v).toFixed(1)}`).join(" ");

  const yTicks = [0, 0.5, 1].map((f) => y0 + f * (y1 - y0));
  const xTicks = (W < 520 ? [0, 0.5, 1] : [0, 0.25, 0.5, 0.75, 1]).map((f) => x0 + f * (x1 - x0));

  const onMove = (e: React.PointerEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * W;
    let best = 0, dist = Infinity;
    points.forEach((p, i) => {
      const d = Math.abs(X(p.t) - px);
      if (d < dist) { dist = d; best = i; }
    });
    setHover(best);
  };

  const h = hover === null ? null : points[hover];
  const selected = h ?? points[points.length - 1];
  return (
    <div className="chart-wrap" ref={chart}>
      <div className="chart-readout"><span>{day(selected.t)}<strong>{money(selected.v)}</strong></span><span>Hover, touch, or use the slider to explore</span></div>
      <svg className="chart" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img"
        aria-label={`Account equity from ${day(points[0].t)} to ${day(points[points.length - 1].t)}. Latest equity ${money(points[points.length - 1].v)}.`}
        onPointerMove={onMove} onPointerDown={onMove} onPointerLeave={() => setHover(null)}>
        {yTicks.map((v) => (
          <g key={v}>
            <line className="grid" x1={PAD.l} x2={W - PAD.r} y1={Y(v)} y2={Y(v)} />
            <text className="axis" x={PAD.l - 8} y={Y(v) + 4} textAnchor="end">{money(v)}</text>
          </g>
        ))}
        {xTicks.map((t) => (
          <text key={t} className="axis" x={X(t)} y={H - 6} textAnchor={t === x0 ? "start" : t === x1 ? "end" : "middle"}>{day(t)}</text>
        ))}
        <path className="series" d={path} />
        {h && (
          <>
            <line className="cross" x1={X(h.t)} x2={X(h.t)} y1={PAD.t} y2={H - PAD.b} />
            <circle className="dot" cx={X(h.t)} cy={Y(h.v)} r={5} />
          </>
        )}
      </svg>
      <label className="chart-scrubber">Explore dates
        <input type="range" min={0} max={points.length - 1} value={hover ?? points.length - 1}
          aria-label="Explore account equity by date" aria-valuetext={`${day(selected.t)}, ${money(selected.v)}`}
          onChange={(e) => setHover(Number(e.target.value))} />
      </label>
    </div>
  );
}
