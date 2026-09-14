import Link from "next/link";
import EquityChart from "@/components/EquityChart";
import Performance from "@/components/Performance";
import Pipeline, { ROLES } from "@/components/Pipeline";
import SiteHeader from "@/components/SiteHeader";
import Convictions from "@/components/Convictions";
import { getBenchmarks, getLivePrices } from "@/lib/benchmarks";
import { BENCHMARKS, type LivePoint } from "@/lib/performance";
import { getAccount, getDashboard, getHistory, getPositions, getTrades } from "@/lib/alpaca";

export const dynamic = "force-dynamic";

const usd = (v: number, digits = 2) =>
  v.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: digits });
const pct = (v: number) => `${v >= 0 ? "+" : ""}${(v * 100).toFixed(2)}%`;
const cls = (v: number) => (v >= 0 ? "up" : "down");
const when = (iso: string) =>
  new Date(iso).toLocaleString("en-US", { timeZone: "America/New_York", month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit" });
const signed = (v: number, digits = 2) => `${v >= 0 ? "+" : ""}${v.toFixed(digits)}`;

export default async function Page() {
  let account, positions, history, trades, dash;
  try {
    [account, positions, history, trades, dash] = await Promise.all([
      getAccount(), getPositions(), getHistory(), getTrades(), getDashboard(),
    ]);
  } catch {
    return (
      <main id="main-content">
        <SiteHeader page="dashboard" />
        <div className="card connection-state">
          <span className="eyebrow">Account connection</span>
          <h1>Portfolio data is temporarily unavailable.</h1>
          <p className="muted">We couldn&apos;t reach the paper account. Try again in a moment, or explore the latest backtest research.</p>
          <div className="connection-actions"><a href="/" className="button">Try again</a><Link href="/backtest" className="text-button">View backtest →</Link></div>
        </div>
      </main>
    );
  }

  const equity = Number(account.equity);
  const lastEquity = Number(account.last_equity);
  const dayPl = equity - lastEquity;
  const dayPct = lastEquity ? dayPl / lastEquity : 0;
  const invested = positions.reduce((s, p) => s + Number(p.market_value), 0);
  const openPl = positions.reduce((s, p) => s + Number(p.unrealized_pl), 0);

  const points = history.timestamp
    .map((t, i) => ({ t, v: history.equity[i] }))
    .filter((p): p is { t: number; v: number } => p.v !== null && p.v > 0);

  const weights = dash ? Object.entries(dash.weights).sort((a, b) => b[1] - a[1]) : [];
  const convictions = dash?.convictions ?? [];
  const agentNames = weights.map(([a]) => a);
  const [benchmarkData, liveTrades] = await Promise.all([getBenchmarks(), getLivePrices(BENCHMARKS)]);
  // Live mark: the account's equity (Alpaca values positions at the latest trade, any session, including overnight)
  // and the benchmarks' latest trades. Recorded closes stay as they are; this point only sits after them.
  const liveTimes = Object.values(liveTrades.trades).flatMap((trade) => trade ? [Date.parse(trade.t)] : []);
  const live: LivePoint | null = liveTrades.unavailable || !liveTimes.length ? null : {
    prices: Object.fromEntries(BENCHMARKS.map((symbol) => [symbol, liveTrades.trades[symbol]?.p ?? null])),
    equity: equity > 0 ? equity : null,
    time: new Date(Math.max(...liveTimes)).toISOString(),
  };
  const livePoints = equity > 0 ? [...points, { t: Math.floor(Date.now() / 1000), v: equity }] : points;

  return (
    <main id="main-content">
      <SiteHeader page="dashboard" />
      <div className="page-heading">
        <div><span className="eyebrow">Portfolio overview</span><h1>The portfolio, at a glance.</h1>
          <p className="sub">A self-weighting agent ensemble across the AI supply chain.</p></div>
        <div className="data-timestamp"><span>Account retrieved</span><time dateTime={new Date().toISOString()}>{when(new Date().toISOString())} ET</time>
          <span>{dash ? `Published cycle · ${dash.date}${dash.dry_run ? " · dry run" : ""}` : "Awaiting a published cycle"}</span></div>
      </div>
      <nav className="section-nav" aria-label="Dashboard sections">
        <a href="#overview">Overview</a><a href="#convictions">Convictions</a><a href="#positions">Positions</a>
        <a href="#decisions">Decisions</a><a href="#agents">Agents</a><a href="#guardian">Guardian</a><a href="#trades">Trades</a>
      </nav>

      <div className="tiles overview-tiles" id="overview">
        <div className="tile primary-tile">
          <div className="label">Equity</div>
          <div className="value">{usd(equity)}</div>
          <div className={`delta ${cls(dayPl)}`}>{usd(dayPl)} ({pct(dayPct)}) today</div>
          <div className="delta muted">Live mark · positions valued at the latest trade, any session</div>
        </div>
        <div className="tile">
          <div className="label">Invested</div>
          <div className="value">{usd(invested, 0)}</div>
          <div className="delta muted">{positions.length} position{positions.length === 1 ? "" : "s"}</div>
        </div>
        <div className="tile">
          <div className="label">Open P/L</div>
          <div className={`value ${cls(openPl)}`}>{usd(openPl)}</div>
          <div className="delta muted">{invested ? pct(openPl / (invested - openPl)) : "—"} vs entry price (not a fee)</div>
        </div>
        <div className="tile">
          <div className="label">Cash</div>
          <div className="value">{usd(Number(account.cash), 0)}</div>
          <div className="delta muted">{equity > 0 ? `${(Number(account.cash) / equity * 100).toFixed(1)}% of equity` : "Available cash"}</div>
        </div>
      </div>

      <h2>Account equity <span>Last 3 months · live mark at the end</span></h2>
      <div className="card"><EquityChart points={livePoints} /></div>

      <h2>Benchmark comparison <span>Since the study started · live mark at the end</span></h2>
      <div className="card">
        {points.length ? (
          <Performance equity={points} benchmarks={benchmarkData.series} openingPrices={benchmarkData.openingPrices}
            source={benchmarkData.source} unavailable={benchmarkData.unavailable} live={live} />
        ) : (
          <div className="empty">Benchmarks appear after the first cycle publishes</div>
        )}
      </div>

      <h2>Backtest · walk-forward, point-in-time rule agents only</h2>
      <div className="card">
        {!dash?.backtest ? (
          <div className="empty">No backtest published yet</div>
        ) : (() => {
          const bt = dash.backtest!;
          const p = bt.portfolio;
          return (
            <>
              <div className="muted" style={{ fontSize: 12, marginBottom: 10 }}>
                {bt.period.start} → {bt.period.end} · {bt.period.trading_days} trading days · agents simulated: {bt.agents.join(", ")} ·
                learner refit daily on outcomes known at the time · 5 bps per unit turnover
              </div>
              <div className="tiles">
                <div className="tile"><div className="label">Live rules (sim)</div>
                  <div className={`value ${cls(p.total_return)}`}>{pct(p.total_return)}</div>
                  <div className="delta muted">avg gross {(p.avg_gross * 100).toFixed(0)}% · {p.avg_names} names · Sharpe {p.sharpe}</div></div>
                {bt.rank_portfolio && (
                  <div className="tile"><div className="label">Top-15 rank (signal quality)</div>
                    <div className={`value ${cls(bt.rank_portfolio.total_return)}`}>{pct(bt.rank_portfolio.total_return)}</div>
                    <div className={`delta ${cls(bt.rank_portfolio.excess_vs_soxx)}`}>{pct(bt.rank_portfolio.excess_vs_soxx)} vs SOXX · Sharpe {bt.rank_portfolio.sharpe}</div></div>
                )}
                <div className="tile"><div className="label">SOXX</div><div className={`value ${cls(p.soxx_return)}`}>{pct(p.soxx_return)}</div></div>
                <div className="tile"><div className="label">SPY</div><div className={`value ${cls(p.spy_return)}`}>{pct(p.spy_return)}</div></div>
                <div className="tile"><div className="label">IC (10d) learned vs equal prior</div>
                  <div className="value">{bt.ic_10d.learned == null ? "—" : bt.ic_10d.learned.toFixed(3)}</div>
                  <div className="delta muted">equal prior {bt.ic_10d.equal_prior == null ? "—" : bt.ic_10d.equal_prior.toFixed(3)} · {bt.ic_10d.days} days</div></div>
              </div>
              <div className="scroll" style={{ marginTop: 10 }}>
                <table>
                  <thead><tr><th>Agent</th>{Object.keys(bt.model_final).map((h) => <th key={h} className="num">IC {h}d</th>)}{Object.keys(bt.model_final).map((h) => <th key={"w" + h} className="num">w {h}d</th>)}</tr></thead>
                  <tbody>
                    {bt.agents.map((a) => (
                      <tr key={a}>
                        <td><b>{a}</b></td>
                        {Object.values(bt.model_final).map((m, i) => <td key={i} className={`num ${(m.agent_ic[a] ?? 0) < 0 ? "down" : ""}`}>{m.agent_ic[a] == null ? "—" : m.agent_ic[a]!.toFixed(3)}</td>)}
                        {Object.values(bt.model_final).map((m, i) => <td key={"w" + i} className={`num ${(m.w_conf[a] ?? 0) < 0 ? "down" : ""}`}>{m.w_conf[a] == null ? "—" : m.w_conf[a].toFixed(3)}</td>)}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="muted" style={{ fontSize: 11, marginTop: 8 }}>{bt.caveats.map((c, i) => <div key={i}>· {c}</div>)}</div>
            </>
          );
        })()}
      </div>

      <h2>How it works <span>Data → agents → orders → scoring</span></h2>
      <div className="card">
        <div className="scroll pipeline-wrap" tabIndex={0} role="region" aria-label="Ensemble pipeline"><Pipeline /></div>
        <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
          Each trading day, agents hand in their own opinions (direction -1..+1, confidence 0..1), and orders go out at the 09:30 ET open.
          Weights start as an equal blend and are refit daily on scored predictions; an agent that is reliably wrong can receive a negative weight and act as a contrarian signal. The minutes of every order are under Decisions.
        </div>
        <div className="scroll" style={{ marginTop: 12 }}>
          <table>
            <thead><tr><th>Agent</th><th>Role</th><th>What it sees</th><th>When it speaks</th><th>Cost</th></tr></thead>
            <tbody>
              {ROLES.map((r) => (
                <tr key={r.agent}>
                  <td><b>{r.agent}</b></td>
                  <td>{r.role}</td>
                  <td className="reason">{r.sees}</td>
                  <td className="reason" style={{ minWidth: 140 }}>{r.speaks}</td>
                  <td className="muted">{r.cost}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <h2 id="agents">Agents <span>Who the ensemble trusts</span></h2>
      <div className="card">
        {!dash ? (
          <div className="empty">dashboard.json not connected — the cycle has not published yet</div>
        ) : (
          <>
            <div className="muted" style={{ marginBottom: 10, fontSize: 12 }}>
              cycle {dash.date}{dash.dry_run ? " · dry run" : ""} · universe {dash.universe_size ?? "?"} tickers ·
              weights = Bayesian ridge stacking refit daily on scored predictions (prior: equal blend; negative = used as a contrarian signal) ·
              shown as share of total |weight|
              {dash.model && (
                <span> · model: {Object.entries(dash.model).map(([h, m]) => `${h}d ${m.n_obs} rows${m.cv_ic != null ? `, IC ${m.cv_ic.toFixed(2)}` : ""}`).join(" · ")}</span>
              )}
            </div>
            <div className="tiles">
              {weights.map(([agent, w]) => (
                <div className="tile" key={agent}>
                  <div className="label">{agent}</div>
                  <div className={`value ${w < 0 ? "down" : ""}`}>{w < 0 ? "-" : ""}{(Math.abs(w) * 100).toFixed(1)}%</div>
                  <div className="delta muted">
                    {dash.weights_hedge && dash.weights_hedge[agent] != null && (
                      <span style={{ marginRight: 8 }}>Hedge ref {(dash.weights_hedge[agent] * 100).toFixed(0)}%</span>
                    )}
                    {dash.model && Object.entries(dash.model).some(([, m]) => m.agent_ic?.[agent] != null) && (
                      <span style={{ marginRight: 8 }}>
                        IC {Object.entries(dash.model).map(([h, m]) => `${h}d ${m.agent_ic?.[agent] == null ? "-" : m.agent_ic[agent]!.toFixed(2)}`).join(" / ")}
                      </span>
                    )}
                    {(dash.scoreboard ?? []).filter((s) => s.agent === agent).map((s) => (
                      <span key={s.horizon} style={{ marginRight: 8 }}>
                        {s.horizon}d: {s.n} scored{s.hit_rate != null ? `, ${(s.hit_rate * 100).toFixed(0)}% hit` : ""}
                        {s.mean_abnormal_signed != null ? `, ${pct(s.mean_abnormal_signed)} vs SOXX` : ""}
                      </span>
                    ))}
                    {!(dash.scoreboard ?? []).some((s) => s.agent === agent) && "no scored predictions yet"}
                  </div>
                </div>
              ))}
            </div>
            {(dash.notes ?? []).length > 0 && (
              <div className="muted" style={{ marginTop: 10, fontSize: 12 }}>
                {(dash.notes ?? []).map((n, i) => <div key={i}>· {n}</div>)}
              </div>
            )}
          </>
        )}
      </div>

      <h2>Weights · how trust moved over time</h2>
      <div className="card scroll">
        {!dash || (dash.weights_history ?? []).length === 0 ? (
          <div className="empty">No weight history yet</div>
        ) : (() => {
          const byDate = new Map<string, Record<string, number>>();
          for (const r of dash.weights_history ?? []) {
            if (!byDate.has(r.date)) byDate.set(r.date, {});
            byDate.get(r.date)![r.agent] = r.weight;
          }
          const dates = [...byDate.keys()].sort().reverse();
          return (
            <table>
              <thead><tr><th>Date</th>{agentNames.map((a) => <th key={a} className="num">{a}</th>)}</tr></thead>
              <tbody>
                {dates.map((dt, i) => {
                  const row = byDate.get(dt)!;
                  const prev = i + 1 < dates.length ? byDate.get(dates[i + 1])! : null;
                  return (
                    <tr key={dt}>
                      <td className="muted">{dt}</td>
                      {agentNames.map((a) => {
                        const w = row[a] ?? 0;
                        const delta = prev ? w - (prev[a] ?? 0) : 0;
                        return (
                          <td key={a} className="num">
                            {(w * 100).toFixed(1)}%
                            {prev && Math.abs(delta) >= 0.0005 && (
                              <span className={cls(delta)} style={{ marginLeft: 6, fontSize: 11 }}>
                                {delta >= 0 ? "+" : ""}{(delta * 100).toFixed(1)}
                              </span>
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          );
        })()}
      </div>

      <h2 id="decisions">Decisions <span>The minutes of every order</span></h2>
      <div className="card">
        {!dash || (dash.history ?? []).length === 0 ? (
          <div className="empty">No decisions recorded yet</div>
        ) : (
          (dash.history ?? []).slice().reverse().map((cycle, ci) => (
            <details key={cycle.date} open={ci === 0} style={{ marginBottom: 12 }}>
              <summary style={{ cursor: "pointer" }}>
                <b>{cycle.date}</b>{cycle.dry_run ? " · dry run" : ""} · {cycle.decisions.length} order{cycle.decisions.length === 1 ? "" : "s"} ·
                weights {Object.entries(cycle.weights).map(([a, w]) => `${a} ${(w * 100).toFixed(0)}%`).join(", ")}
              </summary>
              {(cycle.notes ?? []).map((n, i) => <div key={i} className="muted" style={{ fontSize: 12, margin: "6px 0" }}>· {n}</div>)}
              {cycle.decisions.length === 0 && <div className="muted" style={{ fontSize: 12, margin: "6px 0" }}>no orders this cycle</div>}
              {cycle.decisions.map((d) => (
                <div key={d.ticker + d.side} style={{ margin: "10px 0 14px" }}>
                  <div>
                    <span className={`pill ${d.side.toLowerCase()}`}>{d.side}</span> <b>{d.ticker}</b>{" "}
                    {d.notional != null ? usd(d.notional, 0) : "all"} · conviction{" "}
                    <span className={cls(d.conviction)}>{signed(d.conviction)}</span>
                    {d.target_usd != null && <span className="muted"> · target {usd(d.target_usd, 0)}, held before {usd(d.held_before_usd, 0)}</span>}
                  </div>
                  <div className="scroll">
                    <table style={{ marginTop: 6 }}>
                      <thead><tr>
                        <th>Agent</th><th className="num">Weight</th><th className="num">Direction</th>
                        <th className="num">Confidence</th><th className="num">Contribution</th><th>Why</th>
                      </tr></thead>
                      <tbody>
                        {Object.entries(d.agents).sort((a, b) => Math.abs(b[1].contribution) - Math.abs(a[1].contribution)).map(([a, v]) => (
                          <tr key={a}>
                            <td>{a}</td>
                            <td className="num">{(v.weight * 100).toFixed(0)}%</td>
                            <td className={`num ${cls(v.direction)}`}>{signed(v.direction)}</td>
                            <td className="num">{v.confidence.toFixed(2)}</td>
                            <td className={`num ${cls(v.contribution)}`}>{signed(v.contribution, 3)}</td>
                            <td className="reason">{v.reason}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {d.discussion && (
                    <div style={{ marginTop: 8, fontSize: 13, lineHeight: 1.5 }}>
                      <div><b>Agreement</b> · {d.discussion.agreement}</div>
                      <div><b>Disagreement</b> · {d.discussion.disagreement}</div>
                      <div><b>Verdict</b> · {d.discussion.verdict}</div>
                      <div className="muted"><b>Watch</b> · {d.discussion.watch}</div>
                    </div>
                  )}
                  <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>{d.rule}</div>
                </div>
              ))}
            </details>
          ))
        )}
      </div>

      <h2 id="guardian">Guardian <span>Hourly headline watch on holdings</span></h2>
      <div className="card scroll">
        {!dash?.guardian || dash.guardian.length === 0 ? (
          <div className="empty">No intraday checks yet (runs hourly during the session; a Claude call only when a holding has new headlines)</div>
        ) : (
          <table>
            <thead><tr><th>Time (ET)</th><th>Holdings</th><th>With news</th><th>Events</th></tr></thead>
            <tbody>
              {dash.guardian.slice().reverse().slice(0, 12).map((g, i) => (
                <tr key={i}>
                  <td className="muted">{g.time}</td>
                  <td className="num">{g.holdings}</td>
                  <td className="num">{g.checked}</td>
                  <td className="reason">
                    {g.events.length === 0 ? <span className="muted">nothing material</span> : g.events.map((e, j) => (
                      <div key={j}>
                        <b>{e.ticker}</b> · {e.action}{e.executed ? " (executed)" : ""} · severity {e.severity.toFixed(2)} · {e.reason}
                      </div>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <h2 id="convictions">Convictions <span>Explore the published ranking</span></h2>
      <div className="card">
        <Convictions rows={convictions} agentNames={agentNames} />
      </div>

      <h2 id="positions">Positions <span>{positions.length} open</span></h2>
      <div className="card scroll">
        {positions.length === 0 ? <div className="empty">Flat</div> : (
          <table>
            <thead><tr>
              <th>Symbol</th><th className="num">Qty</th><th className="num">Avg entry</th>
              <th className="num">Price</th><th className="num">Value</th><th className="num">P/L</th>
            </tr></thead>
            <tbody>
              {positions.map((p) => {
                const pl = Number(p.unrealized_pl);
                return (
                  <tr key={p.symbol}>
                    <td><b>{p.symbol}</b></td>
                    <td className="num">{Number(p.qty).toLocaleString()}</td>
                    <td className="num">{usd(Number(p.avg_entry_price))}</td>
                    <td className="num">{usd(Number(p.current_price))}</td>
                    <td className="num">{usd(Number(p.market_value))}</td>
                    <td className={`num ${cls(pl)}`}>{usd(pl)} ({pct(Number(p.unrealized_plpc))})</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      <h2 id="trades">Trade journal <span>What changed and why</span></h2>
      <div className="card scroll">
        {trades === null ? (
          <div className="empty">TRADES_URL / BLOB_READ_WRITE_TOKEN not set — the bot journal is not connected</div>
        ) : trades.length === 0 ? (
          <div className="empty">No trades yet</div>
        ) : (
          <table>
            <thead><tr>
              <th>When (ET)</th><th>Side</th><th>Symbol</th><th className="num">Price</th>
              <th className="num">Size</th><th>Reason</th>
            </tr></thead>
            <tbody>
              {trades.map((t, i) => (
                <tr key={i}>
                  <td className="muted">{when(t.at)}</td>
                  <td><span className={`pill ${t.side.toLowerCase()}`}>{t.side}</span>
                    {t.dry_run && <span className="muted"> dry</span>}</td>
                  <td><b>{t.symbol}</b></td>
                  <td className="num">{t.price != null ? usd(t.price) : "—"}</td>
                  <td className="num">{t.notional != null ? usd(t.notional, 0) : t.qty != null ? `${t.qty} sh` : "—"}</td>
                  <td className="reason">{t.reason ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </main>
  );
}
