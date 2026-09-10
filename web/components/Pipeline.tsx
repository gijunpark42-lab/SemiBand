// How the ensemble works: data → 11 agents → weighted conviction → portfolio → orders → scoring → weights.
// Pure SVG, server-rendered, colours from the page's CSS variables so it follows light/dark.

type Box = { x: number; y: number; w: number; h: number; title: string; sub?: string; tone?: "src" | "rule" | "llm" | "core" };

const W = 1000, H = 380;

const SOURCES: Box[] = [
  { x: 16, y: 26, w: 190, h: 40, title: "earnings-ai supply-chain map", sub: "graph/merged_graph.json · exposure.json", tone: "src" },
  { x: 16, y: 82, w: 190, h: 40, title: "Curated call metrics", sub: "company_metrics.json (guidance · backlog · supply)", tone: "src" },
  { x: 16, y: 138, w: 190, h: 40, title: "Prices", sub: "yfinance daily closes · SOXX benchmark", tone: "src" },
  { x: 16, y: 194, w: 190, h: 40, title: "Financials · earnings dates", sub: "yfinance info · earnings calendar", tone: "src" },
  { x: 16, y: 250, w: 190, h: 40, title: "Headlines", sub: "yfinance news · last 3 weeks", tone: "src" },
];

const AGENTS: (Box & { from: number[] })[] = [
  { x: 270, y: 14, w: 170, h: 26, title: "supply_chain", sub: "transitions · capacity · freshness", tone: "rule", from: [0, 1] },
  { x: 270, y: 46, w: 170, h: 26, title: "neighbors", sub: "are customers/suppliers hot", tone: "rule", from: [0] },
  { x: 270, y: 78, w: 170, h: 26, title: "fundamentals", sub: "growth · margins · valuation", tone: "rule", from: [3] },
  { x: 270, y: 110, w: 170, h: 26, title: "technical", sub: "20/60-day momentum · trend", tone: "rule", from: [2] },
  { x: 270, y: 142, w: 170, h: 26, title: "mean_reversion", sub: "fade 5-day overextension", tone: "rule", from: [2] },
  { x: 270, y: 174, w: 170, h: 26, title: "events", sub: "pre-earnings risk / post drift", tone: "rule", from: [3, 2] },
  { x: 270, y: 206, w: 170, h: 26, title: "risk", sub: "volatility · drawdown brake", tone: "rule", from: [2] },
  { x: 270, y: 238, w: 170, h: 26, title: "macro", sub: "regime × beta (VIX, rates, trend)", tone: "rule", from: [2] },
  { x: 270, y: 278, w: 170, h: 26, title: "llm_supply", sub: "Claude · supply-chain report", tone: "llm", from: [0] },
  { x: 270, y: 310, w: 170, h: 26, title: "llm_guidance", sub: "Claude · the company's own calls", tone: "llm", from: [0, 1] },
  { x: 270, y: 342, w: 170, h: 26, title: "llm_news", sub: "Claude · catalysts", tone: "llm", from: [4] },
];

const ENSEMBLE: Box = { x: 520, y: 118, w: 190, h: 90, title: "Weighted blend (Hedge)", sub: "Σ weight × direction × confidence ÷ Σ weight = conviction", tone: "core" };
const PORTFOLIO: Box = { x: 770, y: 90, w: 214, h: 60, title: "Portfolio", sub: "conviction ≥ 0.15 · top 15 · 10% per name · 150% gross", tone: "core" };
const BROKER: Box = { x: 770, y: 176, w: 214, h: 60, title: "Alpaca paper orders", sub: "at the 09:30 ET open · moderator writes the minutes", tone: "core" };
const SCORE: Box = { x: 520, y: 300, w: 464, h: 60, title: "Score → update weights", sub: "abnormal return vs SOXX after 5 · 10 · 20 trading days · right agents up, wrong agents down (floor 2%)", tone: "core" };

function fill(tone?: Box["tone"]) {
  if (tone === "llm") return "color-mix(in srgb, var(--line) 18%, var(--surface))";
  if (tone === "rule") return "color-mix(in srgb, var(--up) 14%, var(--surface))";
  if (tone === "core") return "color-mix(in srgb, var(--ink) 6%, var(--surface))";
  return "var(--surface)";
}

function BoxEl({ b }: { b: Box }) {
  const small = b.h <= 26;
  return (
    <g>
      <rect x={b.x} y={b.y} width={b.w} height={b.h} rx={6} fill={fill(b.tone)} stroke="var(--border)" />
      <text x={b.x + 10} y={b.y + (small ? 17 : 22)} fontSize={small ? 11.5 : 12.5} fontWeight={600} fill="var(--ink)">
        {b.title}
        {small && b.sub && <tspan fontWeight={400} fill="var(--ink-3)" fontSize={10.5}>{"  " + b.sub}</tspan>}
      </text>
      {!small && b.sub && (
        <text x={b.x + 10} y={b.y + 40} fontSize={10.5} fill="var(--ink-2)">{b.sub}</text>
      )}
    </g>
  );
}

function Arrow({ x1, y1, x2, y2, dashed }: { x1: number; y1: number; x2: number; y2: number; dashed?: boolean }) {
  const mx = (x1 + x2) / 2;
  return (
    <path d={`M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`} fill="none"
      stroke={dashed ? "var(--ink-3)" : "var(--border)"} strokeWidth={1.4} strokeDasharray={dashed ? "4 4" : undefined}
      markerEnd="url(#arrow)" />
  );
}

export default function Pipeline() {
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="SemiBand pipeline" style={{ display: "block" }}>
      <defs>
        <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z" fill="var(--ink-3)" />
        </marker>
      </defs>

      {/* data -> agents */}
      {AGENTS.map((a) => a.from.map((i) => {
        const s = SOURCES[i];
        return <Arrow key={a.title + i} x1={s.x + s.w} y1={s.y + s.h / 2} x2={a.x} y2={a.y + a.h / 2} />;
      }))}
      {/* agents -> ensemble */}
      {AGENTS.map((a) => (
        <Arrow key={"e" + a.title} x1={a.x + a.w} y1={a.y + a.h / 2} x2={ENSEMBLE.x} y2={ENSEMBLE.y + ENSEMBLE.h / 2} />
      ))}
      {/* ensemble -> portfolio -> broker */}
      <Arrow x1={ENSEMBLE.x + ENSEMBLE.w} y1={ENSEMBLE.y + ENSEMBLE.h / 2} x2={PORTFOLIO.x} y2={PORTFOLIO.y + PORTFOLIO.h / 2} />
      <path d={`M${PORTFOLIO.x + PORTFOLIO.w / 2},${PORTFOLIO.y + PORTFOLIO.h} L${BROKER.x + BROKER.w / 2},${BROKER.y}`}
        stroke="var(--border)" strokeWidth={1.4} markerEnd="url(#arrow)" />
      {/* broker -> score (days later) -> ensemble (feedback) */}
      <path d={`M${BROKER.x + BROKER.w / 2},${BROKER.y + BROKER.h} L${BROKER.x + BROKER.w / 2},${SCORE.y}`}
        stroke="var(--ink-3)" strokeWidth={1.4} strokeDasharray="4 4" markerEnd="url(#arrow)" />
      <path d={`M${SCORE.x + 60},${SCORE.y} L${SCORE.x + 60},${ENSEMBLE.y + ENSEMBLE.h}`}
        stroke="var(--ink-3)" strokeWidth={1.4} strokeDasharray="4 4" markerEnd="url(#arrow)" />
      <text x={SCORE.x + 66} y={ENSEMBLE.y + ENSEMBLE.h + 46} fontSize={10.5} fill="var(--ink-3)">feedback, days later</text>

      {/* group labels */}
      <text x={16} y={16} fontSize={10.5} fill="var(--ink-3)" fontWeight={600}>Data (all free)</text>
      <text x={270} y={8} fontSize={10.5} fill="var(--ink-3)" fontWeight={600}>8 rule agents</text>
      <text x={270} y={272} fontSize={10.5} fill="var(--ink-3)" fontWeight={600}>3 Claude agents (subscription)</text>

      {SOURCES.map((b) => <BoxEl key={b.title} b={b} />)}
      {AGENTS.map((b) => <BoxEl key={b.title} b={b} />)}
      <BoxEl b={ENSEMBLE} />
      <BoxEl b={PORTFOLIO} />
      <BoxEl b={BROKER} />
      <BoxEl b={SCORE} />
    </svg>
  );
}

export const ROLES: { agent: string; role: string; sees: string; speaks: string; cost: string }[] = [
  { agent: "supply_chain", role: "What the map says", sees: "The company's own generation-transition wins/losses, sold-out capacity, freshness of its guidance, supply/guidance wording in the curated metrics", speaks: "Every name on the map", cost: "free" },
  { agent: "neighbors", role: "The map, one hop out", sees: "Whether its customers and suppliers are hot right now (sold out, gained content, spoke recently). Customers weigh more than suppliers", speaks: "Names with neighbours", cost: "free" },
  { agent: "fundamentals", role: "Financials", sees: "Revenue growth, operating margin, forward P/E, P/S, analyst target upside", speaks: "Names with data", cost: "free" },
  { agent: "technical", role: "Trend following", sees: "20/60-day momentum vs SOXX, 50/200-day averages, RSI", speaks: "Every name", cost: "free" },
  { agent: "mean_reversion", role: "Fading", sees: "5-day overextension vs SOXX, 20-day z-score. The opposite temperament of technical", speaks: "Every name", cost: "free" },
  { agent: "events", role: "Earnings calendar", sees: "Earnings within 7 days = event risk / reported within 14 days = drift in the direction of the surprise", speaks: "Only when either applies", cost: "free" },
  { agent: "risk", role: "The brake", sees: "20-day volatility ≥ 1.4× the universe median, or a 60-day drawdown 15 pts deeper than SOXX", speaks: "Only when risk is elevated, always negative", cost: "free" },
  { agent: "macro", role: "Market regime", sees: "SOXX vs 50-day, SPY vs 200-day, VIX level, 20-day move in the 10-year yield → one regime score, expressed through each name's 60-day beta to SOXX", speaks: "Every name; high-beta names get the sign of the regime, low-beta the opposite", cost: "free" },
  { agent: "llm_supply", role: "Supply-chain analyst", sees: "The per-name supply-chain report (suppliers, customers, deals, transitions) and whether the price already reflects it", speaks: "Every name", cost: "Claude" },
  { agent: "llm_guidance", role: "Guidance analyst", sees: "The company's 12 latest call statements plus the curated metrics: guidance raised or cut, backlog, margin direction", speaks: "Names with statements in the last 180 days", cost: "Claude" },
  { agent: "llm_news", role: "Catalyst watch", sees: "Three weeks of headlines", speaks: "Names with headlines", cost: "Claude" },
  { agent: "moderator", role: "Minutes (no vote)", sees: "All ten opinions and the weights", speaks: "Agreement / disagreement / verdict / what to watch, for every order", cost: "Claude" },
];
