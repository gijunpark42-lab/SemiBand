import EquityChart from "@/components/EquityChart";
import { getAccount, getHistory, getPositions, getTrades } from "@/lib/alpaca";

export const dynamic = "force-dynamic";

const usd = (v: number, digits = 2) =>
  v.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: digits });
const pct = (v: number) => `${v >= 0 ? "+" : ""}${(v * 100).toFixed(2)}%`;
const cls = (v: number) => (v >= 0 ? "up" : "down");
const when = (iso: string) =>
  new Date(iso).toLocaleString("en-US", { timeZone: "America/New_York", month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit" });

export default async function Page() {
  const [account, positions, history, trades] = await Promise.all([
    getAccount(), getPositions(), getHistory(), getTrades(),
  ]);

  const equity = Number(account.equity);
  const lastEquity = Number(account.last_equity);
  const dayPl = equity - lastEquity;
  const dayPct = lastEquity ? dayPl / lastEquity : 0;
  const invested = positions.reduce((s, p) => s + Number(p.market_value), 0);
  const openPl = positions.reduce((s, p) => s + Number(p.unrealized_pl), 0);

  const points = history.timestamp
    .map((t, i) => ({ t, v: history.equity[i] }))
    .filter((p): p is { t: number; v: number } => p.v !== null && p.v > 0);

  return (
    <main>
      <h1>Semi Bot · paper</h1>
      <p className="sub">Alpaca paper account · refreshed on every load ·{" "}
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
          <div className="empty">TRADES_URL not set — the bot journal is not connected</div>
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
                  <td className="num">{usd(t.price)}</td>
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
