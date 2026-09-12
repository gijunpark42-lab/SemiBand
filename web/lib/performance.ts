export type EquityPoint = { t: number; v: number };
export type DailySeries = Record<string, [string, number][]>;
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
export function buildComparison(equity: EquityPoint[], benchmarks: DailySeries, openingPrices: Record<string, number | null>) {
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
  // The first point is the opening baseline; later points are normal daily closes.
  const dates = shared.length ? [BENCHMARK_START, ...shared] : [];
  const lines = Object.fromEntries(names.map((name) => [name, dates.map((date, i) => {
    const base = bases[name];
    const value = maps[name].get(date);
    if (!available.includes(name) || base == null) return null;
    return i === 0 ? 0 : value == null ? null : value / base - 1;
  })]));
  const latestDates = Object.fromEntries(names.map((name) => [name, [...maps[name].keys()].sort().at(-1) ?? null]));
  return { dates, lines, latestDates, endDate: shared.at(-1) ?? null, portfolioBaselineDate: portfolioBaseline?.[0] ?? null, bases };
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
