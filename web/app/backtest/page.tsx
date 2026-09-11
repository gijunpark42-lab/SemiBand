import Link from "next/link";
import BacktestLive from "@/components/BacktestLive";
import Research from "@/components/Research";
import { getBacktestProgress, getResearch } from "@/lib/alpaca";

export const dynamic = "force-dynamic";

export default async function BacktestPage() {
  let initial = null, research: string | null = null;
  try { [initial, research] = await Promise.all([getBacktestProgress(), getResearch()]); } catch { /* shown as empty */ }
  return (
    <main>
      <nav className="tabs"><Link href="/">Dashboard</Link><Link href="/backtest" className="active">Backtest</Link></nav>
      <h1>SemiBand · backtest</h1>
      <p className="sub">Walk-forward replay of the point-in-time agents on the research machine, streamed here as it runs ·
        progress, equity curve, monthly heatmap, agent IC, the overfitting checks once a run finishes, and below that the log of every
        experiment and the decision it led to</p>
      <BacktestLive initial={initial} />
      <h2 id="decisions">Decisions · what each backtest round tested and what was adopted or rejected</h2>
      <div className="card">
        {research ? <Research markdown={research} /> : <div className="empty">Research log not published yet — run <code>python publish_dashboard.py</code></div>}
      </div>
    </main>
  );
}
