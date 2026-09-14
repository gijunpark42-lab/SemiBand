import { BENCHMARKS, BENCHMARK_START, marketDate, parseDailyBars, sessionComplete, type AlpacaBars } from "./performance";

// Existing paper-account credentials also authorize free delayed consolidated SIP history.
// Keep credentials server-side; do not use paid real-time SIP endpoints.
export async function getBenchmarks() {
  const now = new Date();
  const end = sessionComplete(now)
    ? new Date(Math.floor(now.getTime() / 300000) * 300000 - 20 * 60000).toISOString()
    : `${marketDate(now)}T00:00:00Z`;
  try {
    const key = process.env.ALPACA_API_KEY, secret = process.env.ALPACA_SECRET_KEY;
    if (!key || !secret) throw new Error("Market data credentials unavailable");
    const result: AlpacaBars = { bars: {} };
    let pageToken: string | null = null;
    do {
      const url = new URL("https://data.alpaca.markets/v2/stocks/bars");
      Object.entries({ symbols: BENCHMARKS.join(","), timeframe: "1Day", start: `${BENCHMARK_START}T00:00:00Z`,
        end, feed: "sip", adjustment: "split", limit: "10000", ...(pageToken ? { page_token: pageToken } : {}) })
        .forEach(([name, value]) => url.searchParams.set(name, value));
      const response = await fetch(url, {
        headers: { "APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret },
        next: { revalidate: 300 }, signal: AbortSignal.timeout(6000),
      });
      if (!response.ok) throw new Error(`Market data HTTP ${response.status}`);
      const page: AlpacaBars = await response.json();
      for (const symbol of BENCHMARKS) result.bars![symbol] = [...(result.bars![symbol] ?? []), ...(page.bars?.[symbol] ?? [])];
      pageToken = page.next_page_token ?? null;
    } while (pageToken);
    return { ...parseDailyBars(result, now), source: "Alpaca SIP", unavailable: false };
  } catch {
    return { ...parseDailyBars({}, now), source: "Alpaca SIP", unavailable: true };
  }
}

export type LiveTrade = { p: number; t: string; feed: string };
// Latest trade per symbol across the feeds this key can read: IEX (real-time, regular and extended hours), the consolidated
// tape 15 minutes delayed (all exchanges, 04:00-20:00 ET) and the overnight session (20:00-04:00 ET). The newest print wins,
// so regular hours come from IEX and evenings/nights from the delayed tape or the overnight session. Never cached.
export async function getLivePrices(symbols: readonly string[]): Promise<{ trades: Record<string, LiveTrade | null>; unavailable: boolean }> {
  const trades: Record<string, LiveTrade | null> = Object.fromEntries(symbols.map((symbol) => [symbol, null]));
  const key = process.env.ALPACA_API_KEY, secret = process.env.ALPACA_SECRET_KEY;
  if (!key || !secret || !symbols.length) return { trades, unavailable: true };
  const pages = await Promise.allSettled(["iex", "delayed_sip", "overnight"].map(async (feed) => {
    const url = new URL("https://data.alpaca.markets/v2/stocks/trades/latest");
    url.searchParams.set("symbols", symbols.join(","));
    url.searchParams.set("feed", feed);
    const response = await fetch(url, { headers: { "APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret }, cache: "no-store", signal: AbortSignal.timeout(6000) });
    if (!response.ok) throw new Error(`Latest trades ${feed}: HTTP ${response.status}`);
    const page: { trades?: Record<string, { p?: number; t?: string }> } = await response.json();
    return { feed, trades: page.trades ?? {} };
  }));
  let any = false;
  for (const page of pages) {
    if (page.status !== "fulfilled") continue;
    for (const [symbol, trade] of Object.entries(page.value.trades)) {
      const p = Number(trade?.p), t = String(trade?.t ?? "");
      if (!(symbol in trades) || !Number.isFinite(p) || p <= 0 || !Number.isFinite(Date.parse(t))) continue;
      any = true;
      const current = trades[symbol];
      if (!current || Date.parse(t) > Date.parse(current.t)) trades[symbol] = { p, t, feed: page.value.feed };
    }
  }
  return { trades, unavailable: !any };
}
