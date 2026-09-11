"use client";

// Live view of the research machine's backtest / sweep: polls /api/backtest, which reads the
// progress file backtest.py uploads after every refit (state/backtest_progress.json in the Blob store).
import { useEffect, useMemo, useState } from "react";
import Heatmap from "@/components/Heatmap";
import type { BacktestProgress, SweepResult } from "@/lib/alpaca";

const POLL_RUNNING_MS = 5000, POLL_IDLE_MS = 30000;
const pct = (v: number, d = 1) => `${v >= 0 ? "+" : ""}${(v * 100).toFixed(d)}%`;
const cls = (v: number) => (v >= 0 ? "up" : "down");
const dur = (s?: number) => s == null ? "—" : s < 90 ? `${Math.round(s)}s` : s < 5400 ? `${Math.round(s / 60)} min` : `${(s / 3600).toFixed(1)} h`;
const ago = (iso?: string) => {
  if (!iso) return "—";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  return s < 60 ? `${Math.max(0, Math.round(s))}s ago` : s < 3600 ? `${Math.round(s / 60)} min ago` : `${(s / 3600).toFixed(1)} h ago`;
};
const COLORS: Record<string, string> = { Portfolio: "var(--line)", "Top-15 rank": "var(--ink-2)", SOXX: "var(--down)", SPY: "var(--up)" };

export default function BacktestLive({ initial }: { initial: BacktestProgress | null }) {
  const [p, setP] = useState<BacktestProgress | null>(initial);
  const [err, setErr] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const running = p?.status === "running" || p?.status === "loading";

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const r = await fetch("/api/backtest", { cache: "no-store" });
        if (!r.ok) throw new Error(`${r.status}`);
        const j = await r.json();
        if (alive) { setP(j); setErr(null); }
      } catch (e) { if (alive) setErr(String(e)); }
    };
    const id = setInterval(load, running ? POLL_RUNNING_MS : POLL_IDLE_MS);
    const clock = setInterval(() => setTick((t) => t + 1), 1000);
    return () => { alive = false; clearInterval(id); clearInterval(clock); };
  }, [running]);

  if (!p) return <div className="card empty">No backtest has published progress yet — run <code>python backtest.py</code> on the research machine.</div>;

  const status = p.status;
  return (
    <>
      <div className="card statusbar">
        <span className={`pill status ${status}`}>{status === "running" ? "● running" : status === "loading" ? "● loading" : status === "done" ? "✓ done" : "✕ failed"}</span>
        <span><b>{p.kind === "sweep" ? "parameter sweep" : "walk-forward backtest"}</b>{p.tag ? ` · tag ${p.tag}` : ""}
          {p.kind === "backtest" && p.exec ? ` · execution at the ${p.exec === "open" ? "next open (live rule)" : "signal-day close"}` : ""}
          {p.period ? ` · ${p.period.start} → ${p.period.end} (${p.period.trading_days} days, ${p.tickers} names)` : ""}</span>
        <span className="muted">updated {tick ? ago(p.updated) : "…"} · polling every {running ? POLL_RUNNING_MS / 1000 : POLL_IDLE_MS / 1000}s{err ? ` · fetch error ${err}` : ""}</span>
      </div>
      {p.message && status !== "running" && <div className="muted" style={{ margin: "8px 0", fontSize: 12 }}>{p.message}</div>}

      <div className="progress" aria-label="progress">
        <div className={`bar ${status}`} style={{ width: `${Math.round((p.pct ?? 0) * 100)}%` }} />
        <div className="ptext">
          {Math.round((p.pct ?? 0) * 100)}%
          {p.kind === "backtest" && p.day != null ? ` · day ${p.day} / ${p.total_days} · ${p.date}` : ""}
          {p.kind === "sweep" && p.done != null ? ` · variant ${p.done} / ${p.total}` : ""}
          {` · elapsed ${dur(p.elapsed_s)}`}{status === "running" ? ` · ETA ${dur(p.eta_s)}` : ""}
        </div>
      </div>

      {p.kind === "backtest" ? <BacktestView p={p} /> : <SweepView p={p} />}
    </>
  );
}

function BacktestView({ p }: { p: BacktestProgress }) {
  const curve = p.curve ?? [];
  const last = curve[curve.length - 1];
  const horizons = Object.keys(p.model ?? {});
  const agents = p.agents ?? (horizons.length ? Object.keys(p.model![horizons[0]].agent_ic) : []);
  const months = (p.monthly ?? []).map((m) => m.period);
  const rb = p.robustness;
  return (
    <>
      <h2>Simulated book · so far</h2>
      <div className="tiles">
        <div className="tile"><div className="label">Live rules (sim)</div>
          <div className={`value ${cls((p.equity ?? 1) - 1)}`}>{pct((p.equity ?? 1) - 1)}</div>
          <div className="delta muted">gross {((p.gross ?? 0) * 100).toFixed(0)}% · {p.names ?? 0} names · turnover {((p.turnover_per_day ?? 0) * 100).toFixed(0)}%/day</div></div>
        <div className="tile"><div className="label">Top-15 rank (signal quality)</div>
          <div className={`value ${cls((p.rank ?? 1) - 1)}`}>{pct((p.rank ?? 1) - 1)}</div>
          <div className={`delta ${cls((p.rank ?? 1) - (p.soxx ?? 1))}`}>{pct((p.rank ?? 1) - (p.soxx ?? 1))} vs SOXX</div></div>
        <div className="tile"><div className="label">SOXX</div><div className={`value ${cls((p.soxx ?? 1) - 1)}`}>{pct((p.soxx ?? 1) - 1)}</div></div>
        <div className="tile"><div className="label">SPY</div><div className={`value ${cls((p.spy ?? 1) - 1)}`}>{pct((p.spy ?? 1) - 1)}</div></div>
        <div className="tile"><div className="label">IC (10d) learned vs equal prior</div>
          <div className="value">{p.ic_10d?.learned == null ? "—" : p.ic_10d.learned.toFixed(3)}</div>
          <div className="delta muted">equal prior {p.ic_10d?.equal_prior == null ? "—" : p.ic_10d.equal_prior.toFixed(3)}</div></div>
        {p.portfolio && (
          <div className="tile"><div className="label">Sharpe · max drawdown</div>
            <div className="value">{p.portfolio.sharpe}</div>
            <div className="delta down">−{(p.portfolio.max_drawdown * 100).toFixed(1)}% max drawdown · vol {(p.portfolio.ann_vol * 100).toFixed(0)}%</div></div>
        )}
      </div>

      <h2>Equity curve · growing as the replay advances (log scale)</h2>
      <div className="card">{curve.length > 2 ? <Curve curve={curve} /> : <div className="empty">Waiting for the first traded day (30-day warm-up)</div>}</div>

      <h2>Monthly returns · portfolio vs SOXX</h2>
      <div className="card">
        {months.length ? (
          <Heatmap rows={["Portfolio", "SOXX", "Excess"]} cols={months} colLabel={(c) => c.slice(2).replace("-", "/")}
            values={[(p.monthly ?? []).map((m) => m.portfolio), (p.monthly ?? []).map((m) => m.soxx), (p.monthly ?? []).map((m) => m.excess)]}
            fmt={(v) => pct(v, 0)} max={0.3} />
        ) : <div className="empty">No completed month yet</div>}
        <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>Colour saturates at ±30% a month. A strategy that is one good quarter is not a strategy — look for many mildly green cells, not one dark one.</div>
      </div>

      <h2>Agents · information coefficient and learned weight per horizon (refit weekly, walk-forward)</h2>
      <div className="card">
        {horizons.length ? (
          <div className="two">
            <div>
              <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>IC of each agent&apos;s own calls (rank correlation with abnormal return)</div>
              <Heatmap rows={agents} cols={horizons} colLabel={(h) => `${h}d`} fmt={(v) => v.toFixed(3)} max={0.15}
                values={agents.map((a) => horizons.map((h) => p.model![h].agent_ic[a]))} />
            </div>
            <div>
              <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>Weight the learner currently puts on direction × confidence</div>
              <Heatmap rows={agents} cols={horizons} colLabel={(h) => `w ${h}d`} fmt={(v) => v.toFixed(3)} max={0.3}
                values={agents.map((a) => horizons.map((h) => p.model![h].w_conf[a]))} />
            </div>
          </div>
        ) : <div className="empty">The first model is fitted after the warm-up</div>}
      </div>

      {!!p.holdings?.length && (
        <>
          <h2>Book on {p.date}</h2>
          <div className="card chips">{p.holdings.map((t) => <span key={t} className="chip">{t}</span>)}</div>
        </>
      )}

      {rb && (
        <>
          <h2>Robustness · is the number real?</h2>
          <div className="card">
            <div className="tiles">
              <div className="tile"><div className="label">Sharpe · 95% bootstrap CI</div>
                <div className="value">{rb.sharpe}</div>
                <div className="delta muted">{rb.sharpe_ci95 ? `${rb.sharpe_ci95[0]} to ${rb.sharpe_ci95[1]}` : "—"} (10-day blocks, 2000 resamples)</div></div>
              <div className="tile"><div className="label">Deflated Sharpe (prob. the edge is real)</div>
                <div className={`value ${rb.deflated && rb.deflated.dsr >= 0.95 ? "up" : "down"}`}>{rb.deflated ? `${(rb.deflated.dsr * 100).toFixed(0)}%` : "—"}</div>
                <div className="delta muted">{rb.deflated ? `after ${rb.deflated.n_trials} sweep trials · best random trial ≈ Sharpe ${rb.deflated.sr0_ann}` : "no sweep record"}</div></div>
              <div className="tile"><div className="label">Best quarter&apos;s share of the return</div>
                <div className={`value ${rb.best_quarter_share != null && rb.best_quarter_share > 0.5 ? "down" : ""}`}>{rb.best_quarter_share == null ? "—" : `${(rb.best_quarter_share * 100).toFixed(0)}%`}</div>
                <div className="delta muted">of total log return · above 50% = one burst</div></div>
              {rb.deflated && (
                <div className="tile"><div className="label">Daily return shape</div>
                  <div className="value">{rb.deflated.skew}</div>
                  <div className="delta muted">skew · kurtosis {rb.deflated.kurtosis}</div></div>
              )}
            </div>
            <div className="two" style={{ marginTop: 12 }}>
              <div>
                <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>Cost sensitivity (bps per unit turnover)</div>
                {rb.cost_sensitivity ? (
                  <table><thead><tr><th>Cost</th><th className="num">Return</th><th className="num">Sharpe</th></tr></thead>
                    <tbody>{rb.cost_sensitivity.map((c) => <tr key={c.bps}><td>{c.bps} bps</td><td className={`num ${cls(c.total_return)}`}>{pct(c.total_return)}</td><td className="num">{c.sharpe}</td></tr>)}</tbody></table>
                ) : <div className="muted">—</div>}
              </div>
              <div>
                <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>Quarterly returns</div>
                <table><thead><tr><th>Quarter</th><th className="num">Portfolio</th><th className="num">SOXX</th><th className="num">Excess</th></tr></thead>
                  <tbody>{(p.quarterly ?? []).map((q) => <tr key={q.period}><td>{q.period}</td><td className={`num ${cls(q.portfolio)}`}>{pct(q.portfolio)}</td><td className={`num ${cls(q.soxx)}`}>{pct(q.soxx)}</td><td className={`num ${cls(q.excess)}`}>{pct(q.excess)}</td></tr>)}</tbody></table>
              </div>
            </div>
            {rb.rolling_sharpe_60d?.length > 5 && (
              <div style={{ marginTop: 12 }}>
                <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>Rolling 60-day Sharpe — a stable edge stays above zero most of the time</div>
                <Sparkline points={rb.rolling_sharpe_60d.map((r) => r.sharpe)} labels={rb.rolling_sharpe_60d.map((r) => r.date)} />
              </div>
            )}
            {p.caveats && <div className="muted" style={{ fontSize: 11, marginTop: 10 }}>{p.caveats.map((c, i) => <div key={i}>· {c}</div>)}</div>}
          </div>
        </>
      )}
    </>
  );
}

function Curve({ curve }: { curve: NonNullable<BacktestProgress["curve"]> }) {
  const [hover, setHover] = useState<number | null>(null);
  const W = 800, H = 260, PAD = { l: 48, r: 12, t: 12, b: 24 };
  const series: Record<string, number[]> = {
    Portfolio: curve.map((c) => c.portfolio), "Top-15 rank": curve.map((c) => c.rank), SOXX: curve.map((c) => c.soxx), SPY: curve.map((c) => c.spy),
  };
  const all = Object.values(series).flat().filter((v) => v > 0);
  const y0 = Math.log(Math.min(...all)) - 0.05, y1 = Math.log(Math.max(...all)) + 0.05;
  const X = (i: number) => PAD.l + (i / (curve.length - 1)) * (W - PAD.l - PAD.r);
  const Y = (v: number) => PAD.t + (1 - (Math.log(v) - y0) / (y1 - y0)) * (H - PAD.t - PAD.b);
  const path = (arr: number[]) => arr.map((v, i) => `${i ? "L" : "M"}${X(i).toFixed(1)},${Y(v).toFixed(1)}`).join(" ");
  const ticks = [0.5, 0.75, 1, 1.5, 2, 3, 4, 6, 8, 12, 16].filter((v) => Math.log(v) > y0 && Math.log(v) < y1);
  const xt = [0, 0.25, 0.5, 0.75, 1].map((f) => Math.round(f * (curve.length - 1)));
  const h = hover == null ? null : curve[Math.max(0, Math.min(curve.length - 1, hover))];
  return (
    <div>
      <div className="legend">{Object.keys(series).map((n) => <span key={n}><i style={{ background: COLORS[n] }} />{n} <b>{pct(series[n][series[n].length - 1] - 1)}</b></span>)}</div>
      <div className="chart-wrap">
        <svg className="chart" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ height: 260 }}
          onMouseMove={(e) => { const r = e.currentTarget.getBoundingClientRect(); setHover(Math.round(((e.clientX - r.left) / r.width * W - PAD.l) / (W - PAD.l - PAD.r) * (curve.length - 1))); }}
          onMouseLeave={() => setHover(null)}>
          {ticks.map((v) => <g key={v}><line className="grid" x1={PAD.l} x2={W - PAD.r} y1={Y(v).toFixed(1)} y2={Y(v).toFixed(1)} /><text className="axis" x={PAD.l - 6} y={(Y(v) + 4).toFixed(1)} textAnchor="end">{v}x</text></g>)}
          {xt.map((i) => <text key={i} className="axis" x={X(i).toFixed(1)} y={H - 6} textAnchor="middle">{curve[i].date.slice(2)}</text>)}
          {Object.entries(series).map(([n, arr]) => <path key={n} d={path(arr)} fill="none" stroke={COLORS[n]} strokeWidth={n === "Portfolio" ? 2.2 : 1.4} strokeLinejoin="round" />)}
          {h && <line className="cross" x1={X(hover!).toFixed(1)} x2={X(hover!).toFixed(1)} y1={PAD.t} y2={H - PAD.b} />}
        </svg>
        {h && <div className="tip" style={{ left: `${(X(hover!) / W) * 100}%`, top: 0 }}>{h.date} · portfolio {pct(h.portfolio - 1)} · rank {pct(h.rank - 1)} · SOXX {pct(h.soxx - 1)} · {h.n} names, gross {(h.gross * 100).toFixed(0)}%</div>}
      </div>
    </div>
  );
}

function Sparkline({ points, labels }: { points: number[]; labels: string[] }) {
  const W = 800, H = 90, PAD = { l: 36, r: 8, t: 8, b: 18 };
  const y0 = Math.min(0, ...points) - 0.2, y1 = Math.max(0, ...points) + 0.2;
  const X = (i: number) => PAD.l + (i / (points.length - 1)) * (W - PAD.l - PAD.r);
  const Y = (v: number) => PAD.t + (1 - (v - y0) / (y1 - y0)) * (H - PAD.t - PAD.b);
  return (
    <svg className="chart" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ height: 90 }}>
      <line className="grid" x1={PAD.l} x2={W - PAD.r} y1={Y(0).toFixed(1)} y2={Y(0).toFixed(1)} />
      <text className="axis" x={PAD.l - 6} y={(Y(0) + 4).toFixed(1)} textAnchor="end">0</text>
      {[0, Math.floor(points.length / 2), points.length - 1].map((i) => <text key={i} className="axis" x={X(i).toFixed(1)} y={H - 4} textAnchor="middle">{labels[i]?.slice(2)}</text>)}
      <path className="series" d={points.map((v, i) => `${i ? "L" : "M"}${X(i).toFixed(1)},${Y(v).toFixed(1)}`).join(" ")} />
    </svg>
  );
}

function SweepView({ p }: { p: BacktestProgress }) {
  const results = useMemo(() => (p.results ?? []).slice().sort((a, b) => (b.score ?? b.sharpe) - (a.score ?? a.sharpe)), [p.results]);
  // heatmap over the two swept parameters with the most distinct values
  const grid = useMemo(() => {
    if (results.length < 4) return null;
    const keys = Object.keys(results[0].params).filter((k) => new Set(results.map((r) => JSON.stringify(r.params[k]))).size > 1);
    const ranked = keys.sort((a, b) => new Set(results.map((r) => JSON.stringify(r.params[b]))).size - new Set(results.map((r) => JSON.stringify(r.params[a]))).size);
    if (ranked.length < 2) return null;
    const [kr, kc] = ranked;
    const rows = [...new Set(results.map((r) => JSON.stringify(r.params[kr])))].sort();
    const cols = [...new Set(results.map((r) => JSON.stringify(r.params[kc])))].sort();
    const cell = (r: string, c: string) => {
      const hits = results.filter((x) => JSON.stringify(x.params[kr]) === r && JSON.stringify(x.params[kc]) === c);
      return hits.length ? Math.max(...hits.map((x) => x.sharpe)) : null;
    };
    return { kr, kc, rows, cols, values: rows.map((r) => cols.map((c) => cell(r, c))) };
  }, [results]);
  return (
    <>
      {p.pbo && (
        <div className="tiles" style={{ marginTop: 12 }}>
          <div className="tile"><div className="label">Probability of backtest overfitting (CSCV)</div>
            <div className={`value ${p.pbo.pbo > 0.5 ? "down" : "up"}`}>{(p.pbo.pbo * 100).toFixed(0)}%</div>
            <div className="delta muted">{p.pbo.combinations} in/out splits · median OOS rank of the in-sample winner {(p.pbo.median_oos_rank * 100).toFixed(0)}%</div></div>
        </div>
      )}
      {grid && (
        <>
          <h2>Sharpe by {grid.kr} × {grid.kc} (best over the other knobs)</h2>
          <div className="card"><Heatmap rows={grid.rows} cols={grid.cols} values={grid.values} fmt={(v) => v.toFixed(2)} max={3} /></div>
        </>
      )}
      <h2>Variants · {results.length} of {p.total} scored</h2>
      <div className="card scroll">
        <table>
          <thead><tr><th>Variant</th><th className="num">Return</th><th className="num">vs SOXX</th><th className="num">Sharpe</th><th className="num">Max DD</th><th className="num">Gross</th><th className="num">Turnover</th><th className="num">IC 10d</th><th className="num">Score</th></tr></thead>
          <tbody>{results.map((r: SweepResult) => (
            <tr key={r.name}><td><b>{r.name}</b></td><td className={`num ${cls(r.total_return)}`}>{pct(r.total_return)}</td><td className={`num ${cls(r.excess_vs_soxx)}`}>{pct(r.excess_vs_soxx)}</td>
              <td className="num">{r.sharpe}</td><td className="num down">{(r.max_drawdown * 100).toFixed(1)}%</td><td className="num">{(r.avg_gross * 100).toFixed(0)}%</td>
              <td className="num">{(r.turnover_per_day * 100).toFixed(0)}%</td><td className="num">{r.ic_10d == null ? "—" : r.ic_10d.toFixed(3)}</td><td className="num">{r.score ?? "—"}</td></tr>
          ))}</tbody>
        </table>
      </div>
    </>
  );
}
