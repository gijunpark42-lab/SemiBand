import Link from "next/link";
import BacktestLive from "@/components/BacktestLive";
import { getBacktestProgress } from "@/lib/alpaca";

export const dynamic = "force-dynamic";

export default async function BacktestPage() {
  let initial = null;
  try { initial = await getBacktestProgress(); } catch { initial = null; }
  return (
    <main>
      <nav className="topnav"><Link href="/">← dashboard</Link></nav>
      <h1>SemiBand · backtest live</h1>
      <p className="sub">Walk-forward replay of the point-in-time agents on the research machine, streamed here after every weekly refit ·
        equity curve, monthly heatmap, agent IC, and the overfitting checks once the run finishes</p>
      <BacktestLive initial={initial} />
    </main>
  );
}
