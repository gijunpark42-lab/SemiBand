import SiteHeader from "@/components/SiteHeader";
import BacktestLive from "@/components/BacktestLive";
import Research from "@/components/Research";
import { getBacktestProgress, getResearch } from "@/lib/alpaca";

export const dynamic = "force-dynamic";

export default async function BacktestPage() {
  let initial = null, research: string | null = null;
  try { [initial, research] = await Promise.all([getBacktestProgress(), getResearch()]); } catch { /* shown as empty */ }
  return (
    <main id="main-content">
      <SiteHeader page="backtest" />
      <div className="page-heading"><div><span className="eyebrow">Research workspace</span>
        <h1>Follow the evidence.</h1>
        <p className="sub">Walk-forward results, agent performance, and the decisions behind each experiment.</p></div>
        <a className="button" href="#decisions">Explore the research log ↓</a>
      </div>
      <BacktestLive initial={initial} />
      <h2 id="decisions">Decisions · what each backtest round tested and what was adopted or rejected</h2>
      <div className="card">
        {research ? <Research markdown={research} /> : <div className="empty">Research log not published yet — run <code>python publish_dashboard.py</code></div>}
      </div>
    </main>
  );
}
