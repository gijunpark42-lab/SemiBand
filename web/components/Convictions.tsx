"use client";

import { Fragment, useId, useState } from "react";
import type { Dashboard } from "@/lib/alpaca";

type Conviction = NonNullable<Dashboard["convictions"]>[number];
const signed = (v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(2)}`;
const usd = (v: number) => v.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

export default function Convictions({ rows, agentNames }: { rows: Conviction[]; agentNames: string[] }) {
  const [query, setQuery] = useState("");
  const [targetsOnly, setTargetsOnly] = useState(false);
  const [limit, setLimit] = useState(40);
  const [expanded, setExpanded] = useState<string | null>(null);
  const id = useId();
  const matching = rows.map((row, i) => ({ ...row, rank: i + 1 })).filter((row) =>
    row.ticker.toLowerCase().includes(query.trim().toLowerCase()) && (!targetsOnly || (row.target_usd ?? 0) > 0));
  const visible = matching.slice(0, limit);

  if (rows.length === 0) return <div className="empty">No convictions published yet. Rankings appear after a cycle completes.</div>;

  return (
    <div>
      <div className="ranking-toolbar">
        <div className="search-field">
          <label htmlFor={`${id}-search`}>Find a symbol</label>
          <input id={`${id}-search`} type="search" placeholder="Search published symbols, e.g. NVDA"
            value={query} onChange={(e) => { setQuery(e.target.value); setLimit(40); }} autoComplete="off" />
        </div>
        <label className="filter-check">
          <input type="checkbox" checked={targetsOnly}
            onChange={(e) => { setTargetsOnly(e.target.checked); setLimit(40); }} />
          With a target allocation
        </label>
        <span className="results-count" role="status">{visible.length} of {matching.length} symbols</span>
      </div>
      <div className="scroll" tabIndex={0} role="region" aria-label="Conviction rankings">
        <table className="ranking-table">
          <caption className="sr-only">Published conviction ranking. Expand agent views for each symbol&apos;s reasoning.</caption>
          <thead><tr>
            <th scope="col">Rank</th><th scope="col">Symbol</th><th scope="col" className="num">Conviction</th>
            <th scope="col" className="num">Target</th><th scope="col" className="num">Agent views</th>
          </tr></thead>
          <tbody>
            {visible.map((row) => {
              const open = expanded === row.ticker;
              const panelId = `${id}-${row.ticker}`;
              return (
                <Fragment key={row.ticker}>
                  <tr>
                    <td className="muted">{row.rank}</td>
                    <th scope="row" className="symbol">{row.ticker}</th>
                    <td className={`num ${row.conviction >= 0 ? "up" : "down"}`}>{signed(row.conviction)}</td>
                    <td className="num">{row.target_usd == null ? "—" : usd(row.target_usd)}</td>
                    <td className="num">
                      <button type="button" className="text-button" aria-expanded={open} aria-controls={panelId}
                        aria-label={`${open ? "Hide" : "Show"} agent views for ${row.ticker}`}
                        onClick={() => setExpanded(open ? null : row.ticker)}>
                        {Object.keys(row.agents).length} views <span aria-hidden="true">{open ? "−" : "+"}</span>
                      </button>
                    </td>
                  </tr>
                  <tr id={panelId} hidden={!open} className="agent-detail-row">
                    <td colSpan={5}>
                      {open && <div className="agent-details">
                        <p className="detail-heading">{row.ticker} · direction × confidence</p>
                        {agentNames.map((agent) => {
                          const view = row.agents[agent];
                          return <div className="agent-view" key={agent}>
                            <b>{agent}</b>
                            <span className={view ? view.direction >= 0 ? "up" : "down" : "muted"}>
                              {view ? `${signed(view.direction)} × ${view.confidence.toFixed(2)}` : "No opinion"}
                            </span>
                            <p>{view?.reason || "No published reasoning for this cycle."}</p>
                          </div>;
                        })}
                      </div>}
                    </td>
                  </tr>
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
      {matching.length === 0 && <div className="empty">
        <p>No symbols match these filters.</p>
        <button type="button" className="button" onClick={() => { setQuery(""); setTargetsOnly(false); setLimit(40); }}>Clear filters</button>
      </div>}
      {matching.length > limit && <div className="ranking-footer">
        <span className="muted">Rank follows the published cycle.</span>
        <button type="button" className="button" onClick={() => setLimit(limit + 40)}>Show 40 more</button>
      </div>}
    </div>
  );
}
