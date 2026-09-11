// Server-only reads from the Alpaca paper account and the bot's journal / dashboard feed.
const BASE = "https://paper-api.alpaca.markets";

function headers() {
  const key = process.env.ALPACA_API_KEY;
  const secret = process.env.ALPACA_SECRET_KEY;
  if (!key || !secret) throw new Error("ALPACA_API_KEY / ALPACA_SECRET_KEY not set");
  return { "APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret };
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { headers: headers(), cache: "no-store" });
  if (!res.ok) throw new Error(`Alpaca ${path}: ${res.status} ${await res.text()}`);
  return res.json();
}

export type Account = {
  equity: string;
  last_equity: string;
  cash: string;
  buying_power: string;
};

export type Position = {
  symbol: string;
  qty: string;
  avg_entry_price: string;
  current_price: string;
  market_value: string;
  unrealized_pl: string;
  unrealized_plpc: string;
};

export type History = {
  timestamp: number[];
  equity: (number | null)[];
  profit_loss_pct: (number | null)[];
};

export type Trade = {
  at: string;
  symbol: string;
  side: "BUY" | "SELL";
  reason: string | null;
  price: number | null;
  notional: number | null;
  qty: number | null;
  dry_run: boolean;
};

export type AgentView = { direction: number; confidence: number; horizon: number; reason: string };
export type AgentDecision = AgentView & { weight: number; contribution: number };

export type Decision = {
  ticker: string;
  side: string;
  notional: number | null;
  conviction: number;
  target_usd: number | null;
  held_before_usd: number;
  agents: Record<string, AgentDecision>;
  rule: string;
  discussion?: { agreement: string; disagreement: string; verdict: string; watch: string };
};

export type CycleRecord = {
  date: string;
  dry_run?: boolean;
  weights: Record<string, number>;
  notes?: string[];
  decisions: Decision[];
};

export type Backtest = {
  generated: string;
  period: { start: string; end: string; trading_days: number };
  agents: string[];
  portfolio: { total_return: number; soxx_return: number; spy_return: number; ann_vol: number; sharpe: number; max_drawdown: number; avg_gross: number; avg_names: number; turnover_per_day: number; tracking_corr_soxx: number | null };
  rank_portfolio?: { description: string; total_return: number; excess_vs_soxx: number; sharpe: number };
  ic_10d: { learned: number | null; equal_prior: number | null; days: number };
  model_final: Record<string, { n_obs: number; lambda: number; cv_ic: number | null; agent_ic: Record<string, number | null>; w_conf: Record<string, number> }>;
  curve: { date: string; portfolio: number; rank?: number; soxx: number; spy: number; gross: number; n: number }[];
  caveats: string[];
};

export type GuardianCheck = {
  time: string; holdings: number; checked: number;
  events: { time: string; ticker: string; new_headlines: number; material: boolean; severity: number; action: string; reason: string; executed: boolean }[];
};

export type Dashboard = {
  guardian?: GuardianCheck[];
  backtest?: Backtest | null;
  benchmarks?: Record<string, [string, number][]>;
  decisions?: Decision[];
  history?: CycleRecord[];
  generated: string;
  date: string;
  dry_run?: boolean;
  equity?: number;
  cash?: number;
  universe_size?: number;
  weights: Record<string, number>;
  weights_hedge?: Record<string, number>;
  model?: Record<string, { n_obs: number; n_dates: number; lambda: number; scale: number; cv_ic: number | null; reliability: number; agent_ic: Record<string, number | null> }>;
  weights_history?: { date: string; agent: string; weight: number }[];
  scoreboard?: { agent: string; horizon: number; n: number; hit_rate: number | null; mean_abnormal_signed: number | null }[];
  convictions?: { ticker: string; conviction: number; target_usd: number | null; agents: Record<string, AgentView> }[];
  orders?: { ticker: string; side: string; notional: number | null; reason: string }[];
  notes?: string[];
};

export const getAccount = () => get<Account>("/v2/account");
export const getPositions = () => get<Position[]>("/v2/positions");
export const getHistory = () =>
  get<History>("/v2/account/portfolio/history?period=3M&timeframe=1D");

async function blob<T>(url: string | undefined): Promise<T | null> {
  // Files live in a private Blob store: read them with the store token.
  const token = process.env.BLOB_READ_WRITE_TOKEN;
  if (!url || !token) return null;
  const res = await fetch(`${url}?cache=0`, {
    headers: { authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (!res.ok) return null;
  return res.json();
}

export async function getTrades(): Promise<Trade[] | null> {
  const rows = await blob<Trade[]>(process.env.TRADES_URL);
  return rows ? rows.slice().reverse() : null; // newest first
}

export async function getDashboard(): Promise<Dashboard | null> {
  // dashboard.json sits next to trades.json in the same store.
  const url = process.env.DASHBOARD_URL ?? process.env.TRADES_URL?.replace(/trades\.json$/, "dashboard.json");
  return blob<Dashboard>(url);
}

// --- live backtest / sweep progress (backtest.py publish_progress -> semiband-v2/backtest_progress.json) ---
export type CalendarRow = { period: string; portfolio: number; soxx: number; excess: number };
export type SweepResult = {
  name: string; params: Record<string, unknown>; total_return: number; soxx_return: number; excess_vs_soxx: number;
  sharpe: number; max_drawdown: number; ann_vol: number; avg_gross: number; avg_names: number; turnover_per_day: number;
  ic_10d: number | null; days: number; score?: number;
  quintiles_10d?: (number | null)[];
  oos?: { start: string; end: string; days: number; total_return: number; soxx_return: number; sharpe: number; max_drawdown: number } | null;
  is?: { start: string; end: string; days: number; total_return: number; soxx_return: number; sharpe: number; max_drawdown: number } | null;
};
export type Robustness = {
  sharpe: number; sharpe_ci95: [number, number] | null;
  deflated: { dsr: number; n_trials: number; sr0_ann: number; skew: number; kurtosis: number } | null;
  rolling_sharpe_60d: { date: string; sharpe: number }[];
  cost_sensitivity: { bps: number; total_return: number; sharpe: number }[] | null;
  best_quarter_share: number | null;
};
export type BacktestProgress = {
  kind: "backtest" | "sweep";
  status: "loading" | "running" | "done" | "failed";
  tag: string; started: string; updated: string; pct: number; message?: string;
  // backtest
  days?: number; exec?: "close" | "open"; extra?: string[]; cap?: number | null;
  period?: { start: string; end: string; trading_days: number }; tickers?: number; agents?: string[];
  day?: number; total_days?: number; date?: string; elapsed_s?: number; eta_s?: number;
  equity?: number; rank?: number; soxx?: number; spy?: number; gross?: number; names?: number; turnover_per_day?: number;
  ic_10d?: { learned: number | null; equal_prior: number | null };
  quintiles_10d?: (number | null)[];      // mean 10-day abnormal return by conviction quintile, Q1 (lowest) .. Q5
  model?: Record<string, { n_obs: number; cv_ic: number | null; agent_ic: Record<string, number | null>; w_conf: Record<string, number> }>;
  holdings?: string[];
  monthly?: CalendarRow[]; quarterly?: CalendarRow[];
  curve?: { date: string; portfolio: number; rank: number; soxx: number; spy: number; gross: number; n: number }[];
  portfolio?: Backtest["portfolio"]; rank_portfolio?: Backtest["rank_portfolio"];
  robustness?: Robustness; caveats?: string[];
  // sweep
  total?: number; done?: number; results?: SweepResult[];
  pbo?: { pbo: number; combinations: number; median_oos_rank: number } | null;
};

// Local viewer (`npm run dev` / watch_backtest.cmd): read the research machine's files directly, no Blob traffic.
const LOCAL = process.env.NODE_ENV !== "production" || !!process.env.LOCAL_STATE_DIR;
async function localFile(rel: string): Promise<string | null> {
  try {
    const fs = await import("fs/promises");
    const path = await import("path");
    const root = process.env.LOCAL_STATE_DIR ?? path.join(process.cwd(), "..");
    return await fs.readFile(path.join(root, rel), "utf-8");
  } catch { return null; }
}

export async function getBacktestProgress(): Promise<BacktestProgress | null> {
  if (LOCAL) {
    const txt = await localFile("state/backtest_progress.json");
    if (txt) return JSON.parse(txt);
  }
  // backtest.py uploads to semiband-v2/backtest_progress.json in the store TRADES_URL points at (see config.PROGRESS_UPLOAD).
  const origin = process.env.TRADES_URL ? new URL(process.env.TRADES_URL).origin : undefined;
  const url = process.env.BACKTEST_PROGRESS_URL ?? (origin && `${origin}/semiband-v2/backtest_progress.json`);
  return blob<BacktestProgress>(url);
}

// RESEARCH.md (the research log: every idea tried, numbers, verdicts), uploaded by publish_dashboard.py.
export async function getResearch(): Promise<string | null> {
  if (LOCAL) {
    const txt = await localFile("RESEARCH.md");
    if (txt) return txt;
  }
  const token = process.env.BLOB_READ_WRITE_TOKEN;
  const origin = process.env.TRADES_URL ? new URL(process.env.TRADES_URL).origin : undefined;
  if (!origin || !token) return null;
  const res = await fetch(`${origin}/semiband-v2/research.md?cache=0`, { headers: { authorization: `Bearer ${token}` }, cache: "no-store" });
  return res.ok ? res.text() : null;
}
