import Link from "next/link";
import SiteHeader from "@/components/SiteHeader";
import Decisions from "@/components/Decisions";
import { getDashboard } from "@/lib/alpaca";

export const dynamic = "force-dynamic";

// Every published cycle's order minutes. The dashboard shows the latest cycle only and links here.
export default async function DecisionsPage() {
  let dash = null;
  try { dash = await getDashboard(); } catch { /* shown as empty */ }
  const cycles = (dash?.history ?? []).slice().reverse();
  return (
    <main id="main-content">
      <SiteHeader page="dashboard" />
      <div className="page-heading"><div><span className="eyebrow">Decision log</span>
        <h1>The minutes of every order.</h1>
        <p className="sub">{cycles.length} published cycle{cycles.length === 1 ? "" : "s"}, newest first.</p></div>
        <Link className="button" href="/">← Dashboard</Link>
      </div>
      <div className="card">
        {cycles.length === 0 ? <div className="empty">No decisions recorded yet</div> : <Decisions cycles={cycles} />}
      </div>
    </main>
  );
}
