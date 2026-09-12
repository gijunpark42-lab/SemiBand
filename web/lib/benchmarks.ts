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
