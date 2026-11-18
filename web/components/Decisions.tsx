import type { CycleRecord } from "@/lib/alpaca";

const usd = (v: number, digits = 2) =>
  v.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: digits });
const cls = (v: number) => (v >= 0 ? "up" : "down");
const signed = (v: number, digits = 2) => `${v >= 0 ? "+" : ""}${v.toFixed(digits)}`;

// The minutes of each cycle's orders, newest first; the first cycle is open. The dashboard passes the latest cycle only,
// /decisions passes every published one, so the long history is sent only to a visitor who asks for it.
export default function Decisions({ cycles }: { cycles: CycleRecord[] }) {
  return (
    <>
      {cycles.map((cycle, ci) => (
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
      ))}
    </>
  );
}
