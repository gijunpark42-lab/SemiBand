import EquityChart from "@/components/EquityChart";
import Performance from "@/components/Performance";
import Pipeline, { ROLES } from "@/components/Pipeline";
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
  } catch (e) {
    return (
      <main>
        <h1>SemiBand · paper</h1>
        <div className="card empty">
          Alpaca not reachable — set ALPACA_API_KEY / ALPACA_SECRET_KEY in the Vercel project env and redeploy.
          <div className="muted" style={{ marginTop: 8, fontSize: 12 }}>{String(e)}</div>
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

  return (
    <main>
      <h1>SemiBand · paper</h1>
      <p className="sub">Self-weighting agent ensemble on the earnings-ai supply-chain universe · Alpaca paper ·{" "}
        {new Date().toLocaleString("en-US", { timeZone: "America/New_York" })} ET</p>

      <div className="tiles">
        <div className="tile">
          <div className="label">Equity</div>
          <div className="value">{usd(equity)}</div>
          <div className={`delta ${cls(dayPl)}`}>{usd(dayPl)} ({pct(dayPct)}) today</div>
        </div>
        <div className="tile">
          <div className="label">Invested</div>
          <div className="value">{usd(invested, 0)}</div>
          <div className="delta muted">{positions.length} position{positions.length === 1 ? "" : "s"}</div>
        </div>
        <div className="tile">
          <div className="label">Open P/L</div>
          <div className={`value ${cls(openPl)}`}>{usd(openPl)}</div>
          <div className="delta muted">{invested ? pct(openPl / (invested - openPl)) : "—"} on cost</div>
        </div>
        <div className="tile">
          <div className="label">Cash</div>
          <div className="value">{usd(Number(account.cash), 0)}</div>
        </div>
      </div>

      <h2>Equity · last 3 months</h2>
      <div className="card"><EquityChart points={points} /></div>

      <h2>Performance · portfolio vs SOXX / SPY / QQQ since the study started</h2>
      <div className="card">
        {dash?.benchmarks && (dash.history ?? []).length > 0 ? (
          <Performance equity={points} benchmarks={dash.benchmarks}
            startDate={(dash.history ?? []).map((h) => h.date).sort()[0]} />
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
                learner refit weekly on outcomes known at the time · 5 bps per unit turnover
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

      <h2>How it works · data → 11 agents → weighted blend → orders → scoring</h2>
      <div className="card">
        <Pipeline />
        <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
          Analysis starts at 05:50 PT every trading day and orders go out right after the 09:30 ET open. Agents do not talk to each other; each hands in its own opinion (direction -1..+1, confidence 0..1).
          Weights start as an equal blend and are refit every day by Bayesian ridge stacking on the scored predictions (abnormal return vs SOXX at 5, 10 and 20 trading days); an agent that is reliably wrong ends up with a negative weight and is used as a contrarian signal. The minutes of every order are under Decisions.
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

      <h2>Agents · who the ensemble trusts</h2>
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

      <h2>Decisions · how each order was made</h2>
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

      <h2>Convictions · today&apos;s ranking</h2>
      <div className="card scroll">
        {convictions.length === 0 ? <div className="empty">No convictions published yet</div> : (
          <table>
            <thead><tr>
              <th>#</th><th>Symbol</th><th className="num">Conviction</th><th className="num">Target</th>
              {agentNames.map((a) => <th key={a} className="num">{a}</th>)}
            </tr></thead>
            <tbody>
              {convictions.slice(0, 40).map((c, i) => (
                <tr key={c.ticker}>
                  <td className="muted">{i + 1}</td>
                  <td><b>{c.ticker}</b></td>
                  <td className={`num ${cls(c.conviction)}`}>{signed(c.conviction)}</td>
                  <td className="num">{c.target_usd != null ? usd(c.target_usd, 0) : "—"}</td>
                  {agentNames.map((a) => {
                    const v = c.agents[a];
                    return (
                      <td key={a} className={`num ${v ? cls(v.direction) : "muted"}`} title={v?.reason ?? ""}>
                        {v ? `${signed(v.direction)} · ${v.confidence.toFixed(2)}` : "—"}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <h2>Positions</h2>
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

      <h2>Trades · why</h2>
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
