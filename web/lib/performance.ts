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
