import Link from "next/link";

export default function SiteHeader({ page }: { page: "dashboard" | "backtest" }) {
  return (
    <header className="site-header">
      <Link href="/" className="brand" aria-label="SemiBand home">
        <span className="brand-mark" aria-hidden="true">S<span> /</span></span>
        <span>SemiBand<span className="brand-caption">Research terminal</span></span>
      </Link>
      <nav className="tabs" aria-label="Main navigation">
        <Link href="/" className={page === "dashboard" ? "active" : ""}
          aria-current={page === "dashboard" ? "page" : undefined}>Dashboard</Link>
        <Link href="/backtest" className={page === "backtest" ? "active" : ""}
          aria-current={page === "backtest" ? "page" : undefined}>Backtest</Link>
      </nav>
      <span className="paper-badge"><span aria-hidden="true" />Paper account</span>
    </header>
  );
}
