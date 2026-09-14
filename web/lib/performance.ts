export type EquityPoint = { t: number; v: number };
export type DailySeries = Record<string, [string, number][]>;
// The live mark: latest trade per benchmark (any session) and the account's live equity, with the newest trade time.
export type LivePoint = { prices: Record<string, number | null>; equity: number | null; time: string };
export const LIVE = "live";
export const BENCHMARKS = ["SOXX", "SPY", "QQQ"] as const;
export const BENCHMARK_START = "2026-09-10";

export function marketDate(time: number | Date): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit" })
    .format(time instanceof Date ? time : new Date(time * 1000));
}

export function sessionComplete(now: Date): boolean {
  const parts = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(now);
  const hour = Number(parts.find((part) => part.type === "hour")?.value);
  const minute = Number(parts.find((part) => part.type === "minute")?.value);
  return hour * 60 + minute >= 16 * 60 + 20;
}

// An explicit opening baseline is never replaced by a closing price or guessed zero.
export function buildComparison(equity: EquityPoint[], benchmarks: DailySeries, openingPrices: Record<string, number | null>, live?: LivePoint) {
  const equityDays = equity.map((point): [string, number] => [marketDate(point.t), point.v])
    .filter(([, value]) => Number.isFinite(value) && value > 0).sort(([a], [b]) => a.localeCompare(b));
  const portfolioBaseline = equityDays.filter(([date]) => date < BENCHMARK_START).at(-1);
  const series: DailySeries = { Portfolio: equityDays, ...benchmarks };
  const names = ["Portfolio", ...BENCHMARKS];
  const bases: Record<string, number | null> = { ...openingPrices, Portfolio: portfolioBaseline?.[1] ?? null };
  const maps = Object.fromEntries(names.map((name) => [name, new Map((series[name] ?? [])
    .filter(([date, value]) => date >= BENCHMARK_START && Number.isFinite(value) && value > 0).sort(([a], [b]) => a.localeCompare(b)))]));
  const available = names.filter((name) => maps[name].size > 0 && bases[name] != null && Number.isFinite(bases[name]) && bases[name]! > 0);
  const shared = [...new Set(available.flatMap((name) => [...maps[name].keys()]))]
    .filter((date) => available.every((name) => maps[name].has(date))).sort();
  // The first point is the opening baseline; later points are normal daily closes; an optional last point is the live
  // mark (latest trade, any session), so the page moves between closes without touching the recorded closes.
  const withLive = !!live && available.length > 0;
  const dates = shared.length || withLive ? [BENCHMARK_START, ...shared, ...(withLive ? [LIVE] : [])] : [];
  const lines = Object.fromEntries(names.map((name) => [name, dates.map((date, i) => {
    const base = bases[name];
    if (!available.includes(name) || base == null) return null;
    if (i === 0) return 0;
    const value = date === LIVE ? (name === "Portfolio" ? live!.equity : live!.prices[name]) : maps[name].get(date);
    return value == null || !Number.isFinite(value) || value <= 0 ? null : value / base - 1;
  })]));
  const latestDates = Object.fromEntries(names.map((name) => [name, [...maps[name].keys()].sort().at(-1) ?? null]));
  return { dates, lines, latestDates, endDate: shared.at(-1) ?? null, portfolioBaselineDate: portfolioBaseline?.[0] ?? null, bases,
    live: withLive ? live! : null };
}

// Which New York session a trade time falls in: extended-hours marks are shown as such, never dressed up as a close.
export function sessionLabel(time: string | number | Date): string {
  const parts = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", hour: "2-digit", minute: "2-digit", hourCycle: "h23" })
    .formatToParts(time instanceof Date ? time : new Date(time));
  const minutes = Number(parts.find((part) => part.type === "hour")?.value) * 60 + Number(parts.find((part) => part.type === "minute")?.value);
  if (minutes >= 9 * 60 + 30 && minutes < 16 * 60) return "regular session";
  if (minutes >= 4 * 60 && minutes < 9 * 60 + 30) return "pre-market";
  if (minutes >= 16 * 60 && minutes < 20 * 60) return "after-hours";
  return "overnight session";
}

export type AlpacaBars = { bars?: Record<string, { t: string; o: number; c: number }[]>; next_page_token?: string | null };

export function parseDailyBars(payload: AlpacaBars, now = new Date()) {
  const today = marketDate(now);
  const complete = sessionComplete(now);
  const series: DailySeries = {};
  const openingPrices: Record<string, number | null> = {};
  for (const symbol of BENCHMARKS) {
    const bars = (payload.bars?.[symbol] ?? []).filter((bar) => Number.isFinite(Date.parse(bar.t)));
    const opening = bars.find((bar) => marketDate(new Date(bar.t)) === BENCHMARK_START)?.o;
    openingPrices[symbol] = typeof opening === "number" && Number.isFinite(opening) && opening > 0 ? opening : null;
    series[symbol] = bars.flatMap((bar): [string, number][] => {
      const date = marketDate(new Date(bar.t));
      if (date > today || (date === today && !complete) || !Number.isFinite(bar.c) || bar.c <= 0) return [];
      return [[date, bar.c]];
    }).sort(([a], [b]) => a.localeCompare(b));
  }
  return { series, openingPrices };
}

export type Risk = { n: number; sharpe: number | null; sharpeSe: number | null; vol: number | null; maxDrawdown: number | null;
  beta: number | null; infoRatio: number | null; infoRatioSe: number | null };

const ANNUAL = Math.sqrt(252);
const mean = (xs: number[]) => xs.reduce((sum, x) => sum + x, 0) / xs.length;
const std = (xs: number[]) => { const m = mean(xs); return Math.sqrt(xs.reduce((sum, x) => sum + (x - m) ** 2, 0) / xs.length); };

// Annualised mean / standard deviation of daily returns, with its approximate standard error (Lo 2002, iid returns).
function annualRatio(xs: number[]) {
  const s = std(xs);
  if (!(s > 1e-12)) return { value: null, se: null };
  const daily = mean(xs) / s;
  return { value: daily * ANNUAL, se: Math.sqrt((1 + daily * daily / 2) / xs.length) * ANNUAL };
}

function dailyReturns(line: (number | null)[], end: number): number[] | null {
  const points = line.slice(0, end + 1);
  if (!points.length || points.some((v) => v == null || !Number.isFinite(v))) return null;
  const levels = (points as number[]).map((v) => 1 + v);
  return levels.slice(1).map((v, i) => v / levels[i] - 1);
}

// Risk of one comparison line through index `end` (index 0 = the opening baseline, later indexes = daily closes, never the
// live mark). Same definitions as backtest.py: daily returns, population standard deviation, zero risk-free rate, x sqrt(252).
// Beta and the information ratio are measured against `bench` (SOXX).
export function riskStats(line: (number | null)[], bench: (number | null)[], end: number): Risk {
  const empty: Risk = { n: 0, sharpe: null, sharpeSe: null, vol: null, maxDrawdown: null, beta: null, infoRatio: null, infoRatioSe: null };
  const r = dailyReturns(line, end);
  if (!r || !r.length) return empty;
  let peak = 1, maxDrawdown = 0;
  for (const v of line.slice(0, end + 1) as number[]) { peak = Math.max(peak, 1 + v); maxDrawdown = Math.max(maxDrawdown, 1 - (1 + v) / peak); }
  if (r.length < 2) return { ...empty, n: r.length, maxDrawdown };
  const sharpe = annualRatio(r);
  const b = dailyReturns(bench, end);
  let beta: number | null = null, info: { value: number | null; se: number | null } = { value: null, se: null };
  if (b && b.length === r.length) {
    const mr = mean(r), mb = mean(b), varB = std(b) ** 2;
    beta = varB > 1e-18 ? r.reduce((sum, x, i) => sum + (x - mr) * (b[i] - mb), 0) / r.length / varB : null;
    info = annualRatio(r.map((x, i) => x - b[i]));
  }
  return { n: r.length, sharpe: sharpe.value, sharpeSe: sharpe.se, vol: std(r) * ANNUAL, maxDrawdown, beta,
    infoRatio: info.value, infoRatioSe: info.se };
}
