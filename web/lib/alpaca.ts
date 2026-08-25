// Server-only reads from the Alpaca paper account and the bot's trade journal.
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
  price: number;
  notional: number | null;
  qty: number | null;
  dry_run: boolean;
};

export const getAccount = () => get<Account>("/v2/account");
export const getPositions = () => get<Position[]>("/v2/positions");
export const getHistory = () =>
  get<History>("/v2/account/portfolio/history?period=3M&timeframe=1D");

export async function getTrades(): Promise<Trade[] | null> {
  // trades.json lives in a private Blob store: read it with the store token.
  const url = process.env.TRADES_URL;
  const token = process.env.BLOB_READ_WRITE_TOKEN;
  if (!url || !token) return null;
  const res = await fetch(`${url}?cache=0`, {
    headers: { authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (!res.ok) return null;
  const rows: Trade[] = await res.json();
  return rows.slice().reverse(); // newest first
}
