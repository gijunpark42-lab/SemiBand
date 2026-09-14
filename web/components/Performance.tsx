"use client";

import { useEffect, useRef, useState } from "react";
import { BENCHMARK_START, LIVE, buildComparison, sessionLabel, type DailySeries, type EquityPoint, type LivePoint } from "@/lib/performance";

const H = 240, PAD = { l: 62, r: 12, t: 14, b: 24 };
const COLORS: Record<string, string> = { Portfolio: "var(--line)", SOXX: "var(--down)", SPY: "var(--ink-3)", QQQ: "var(--up)" };
const pct = (v: number) => `${v >= 0 ? "+" : ""}${(v * 100).toFixed(2)}%`;
const day = (iso: string) => new Date(iso + "T12:00:00Z").toLocaleDateString("en-US", { timeZone: "America/New_York", month: "short", day: "numeric" });

export default function Performance({ equity, benchmarks, openingPrices, source, unavailable, live }: {
  equity: EquityPoint[]; benchmarks: DailySeries; openingPrices: Record<string, number | null>; source: string; unavailable: boolean;
  live?: LivePoint | null;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const [W, setWidth] = useState(800);
  const chart = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!chart.current) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(280, Math.round(entry.contentRect.width))));
    observer.observe(chart.current);
    return () => observer.disconnect();
  }, []);
  const { dates, lines, latestDates, endDate, portfolioBaselineDate, bases, live: mark } = buildComparison(equity, benchmarks, openingPrices, live ?? undefined);
  const isLive = dates.at(-1) === LIVE;
  const liveLabel = mark ? `${new Date(mark.time).toLocaleString("en-US", { timeZone: "America/New_York", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })} ET · ${sessionLabel(mark.time)}` : "";
  const label = (i: number) => dates[i] === LIVE ? `Live · ${liveLabel}` : `${day(dates[i])} ${i === 0 ? "open" : "close"}`;
  const all = Object.values(lines).flat().filter((v): v is number => v != null);
  let y0 = Math.min(0, ...all), y1 = Math.max(0, ...all);
  const padY = (y1 - y0 || 0.01) * 0.1; y0 -= padY; y1 += padY;
  const X = (i: number) => PAD.l + (i / Math.max(1, dates.length - 1)) * (W - PAD.l - PAD.r);
  const Y = (v: number) => PAD.t + (1 - (v - y0) / (y1 - y0)) * (H - PAD.t - PAD.b);
  const path = (arr: (number | null)[]) => {
    let d = "", pen = false;
    arr.forEach((v, i) => { if (v == null) { pen = false; return; } d += `${pen ? "L" : "M"}${X(i).toFixed(1)},${Y(v).toFixed(1)} `; pen = true; });
    return d;
  };
  const yTicks = [0, 0.5, 1].map((f) => y0 + f * (y1 - y0));
  const hi = hover == null ? dates.length - 1 : Math.max(0, Math.min(dates.length - 1, hover));

  return (
    <div ref={chart} className="performance">
      <div className="performance-context">
        <span>ETF baseline: Sep 10, 2026 market open → {isLive ? "live mark" : endDate ? `${day(endDate)} close` : "latest daily close"}</span>
        <span>{source} · closes: free delayed data, 5-minute cache · live mark: latest trade on every load (IEX real-time, consolidated tape 15 min delayed, overnight session)</span>
      </div>
      {unavailable && <p className="data-notice">Benchmark prices are temporarily unavailable. Opening prices are never replaced by a closing price or zero. Try refreshing shortly.</p>}
      {!isLive && endDate && latestDates.Portfolio && endDate < latestDates.Portfolio && <p className="data-notice">Comparison ends {day(endDate)} because one or more benchmarks have not published the portfolio&apos;s latest session.</p>}
      <div className="tiles" style={{ marginBottom: 16 }}>
        {Object.entries(lines).map(([name, arr]) => {
          const value = arr.at(-1) ?? null;
          return <div className="tile" key={name}>
            <div className="label" style={{ color: COLORS[name] }}>{name}</div>
            <div className={`value ${value == null ? "muted" : value < 0 ? "down" : "up"}`}>{value == null ? "—" : pct(value)}</div>
            <div className="delta muted">{value == null ? "Opening baseline unavailable" : isLive ? `live · ${liveLabel}` : endDate ? `through ${day(endDate)} close` : ""}</div>
            <div className="delta muted">{name === "Portfolio"
              ? portfolioBaselineDate ? `${day(portfolioBaselineDate)} account close as opening proxy` : "No opening account history"
              : bases[name] != null ? `Sep 10 open $${bases[name]!.toFixed(2)}` : "Sep 10 open not available"}</div>
          </div>;
        })}
      </div>
      {dates.length < 2 ? <div className="empty">The comparison needs the opening baseline and at least one subsequent daily close or live mark.</div> : <>
        <div className="chart-readout"><span>{label(hi)}</span><span>{Object.entries(lines).map(([name, arr]) => `${name} ${arr[hi] == null ? "—" : pct(arr[hi]!)}`).join(" · ")}</span></div>
        <svg className="chart" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img"
          aria-label={`Portfolio and benchmark returns from ${day(BENCHMARK_START)} open through ${isLive ? "the live mark" : `${day(endDate!)} close`}`}
          onPointerMove={(e) => {
            const rect = e.currentTarget.getBoundingClientRect();
            setHover(Math.round((e.clientX - rect.left - PAD.l) / (rect.width - PAD.l - PAD.r) * (dates.length - 1)));
          }} onPointerLeave={() => setHover(null)}>
          {yTicks.map((value) => <g key={value}>
            <line className="grid" x1={PAD.l} x2={W - PAD.r} y1={Y(value)} y2={Y(value)} />
            <text className="axis" x={PAD.l - 6} y={Y(value) + 4} textAnchor="end">{pct(value)}</text>
          </g>)}
          {Object.entries(lines).map(([name, arr]) => <path key={name} d={path(arr)} fill="none" stroke={COLORS[name]}
            strokeWidth={name === "Portfolio" ? 2.2 : 1.4} strokeLinejoin="round" />)}
          {hover != null && <line className="cross" x1={X(hi)} x2={X(hi)} y1={PAD.t} y2={H - PAD.b} />}
          {[...new Set([0, Math.floor((dates.length - 1) / 2), dates.length - 1])].map((i) => <text key={i} className="axis" x={X(i)} y={H - 6}
            textAnchor={i === 0 ? "start" : i === dates.length - 1 ? "end" : "middle"}>{dates[i] === LIVE ? "live" : day(dates[i])}{i === 0 ? " open" : ""}</text>)}
        </svg>
        <label className="chart-scrubber">Explore dates<input type="range" min={0} max={dates.length - 1} value={hi}
          aria-label="Explore benchmark returns by date" aria-valuetext={label(hi)} onChange={(e) => setHover(Number(e.target.value))} /></label>
      </>}
    </div>
  );
}
