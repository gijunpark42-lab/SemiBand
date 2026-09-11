import { NextResponse } from "next/server";
import { getBacktestProgress } from "@/lib/alpaca";

// Polled by /backtest every few seconds while a backtest or sweep runs on the research machine.
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const progress = await getBacktestProgress();
    return NextResponse.json(progress, { headers: { "cache-control": "no-store" } });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
