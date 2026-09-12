import test from "node:test";
import assert from "node:assert/strict";
import { buildComparison, marketDate, parseDailyBars, sessionComplete } from "../lib/performance.ts";

const timestamp = (iso) => Date.parse(iso) / 1000;
const equity = [
  { t: timestamp("2026-09-10T00:00:00Z"), v: 1000000 }, // Sep 9 account close
  { t: timestamp("2026-09-11T00:00:00Z"), v: 999583.2 },
  { t: timestamp("2026-09-12T00:00:00Z"), v: 1006860.73 },
];

test("the requested open 100 to latest 105 example returns +5%, never close-to-close", () => {
  const result = buildComparison(equity, { SOXX: [["2026-09-10", 102], ["2026-09-11", 105]] }, { SOXX: 100 });
  assert.ok(Math.abs(result.lines.SOXX.at(-1) - 0.05) < 1e-10);
  assert.ok(Math.abs(result.lines.SOXX[1] - 0.02) < 1e-10);
  assert.equal(result.lines.SOXX[0], 0);
});

test("verified Alpaca opening prices restore all three real benchmark returns", () => {
  const result = buildComparison(equity, {
    SOXX: [["2026-09-10", 517.43], ["2026-09-11", 527.07]],
    SPY: [["2026-09-10", 757.83], ["2026-09-11", 764.29]],
    QQQ: [["2026-09-10", 708.69], ["2026-09-11", 714.88]],
  }, { SOXX: 518.32, SPY: 758.03, QQQ: 707.55 });
  assert.equal((result.lines.SOXX.at(-1) * 100).toFixed(2), "1.69");
  assert.equal((result.lines.SPY.at(-1) * 100).toFixed(2), "0.83");
  assert.equal((result.lines.QQQ.at(-1) * 100).toFixed(2), "1.04");
  assert.equal((result.lines.Portfolio.at(-1) * 100).toFixed(2), "0.69");
  assert.equal(result.portfolioBaselineDate, "2026-09-09");
});

test("missing opening prices never fall back to a closing-price baseline", () => {
  const result = buildComparison(equity, { SOXX: [["2026-09-10", 100], ["2026-09-11", 110]], SPY: [["2026-09-11", 102]] }, { SOXX: null, SPY: null });
  assert.equal(result.lines.SOXX.at(-1), null);
  assert.equal(result.lines.SPY.at(-1), null);
});

test("available series end on the same session when a benchmark is stale", () => {
  const result = buildComparison(equity, { SOXX: [["2026-09-10", 101]], SPY: [["2026-09-10", 101], ["2026-09-11", 103]] }, { SOXX: 100, SPY: 100 });
  assert.equal(result.endDate, "2026-09-10");
  assert.equal(result.latestDates.Portfolio, "2026-09-11");
  assert.ok(Math.abs(result.lines.SPY.at(-1) - 0.01) < 1e-10);
});

test("UTC-midnight equity and daily bars use New York market dates in both DST seasons", () => {
  assert.equal(marketDate(timestamp("2026-09-12T00:00:00Z")), "2026-09-11");
  assert.equal(marketDate(timestamp("2026-01-07T00:00:00Z")), "2026-01-06");
  assert.equal(marketDate(timestamp("2026-09-10T04:00:00Z")), "2026-09-10");
});

test("parser preserves the exact Sept 10 open and excludes unfinished daily bars", () => {
  const payload = { bars: { SOXX: [
    { t: "2026-09-10T04:00:00Z", o: 100, c: 102 },
    { t: "2026-09-11T04:00:00Z", o: 103, c: 105 },
  ] } };
  const duringSession = parseDailyBars(payload, new Date("2026-09-11T19:00:00Z"));
  assert.equal(duringSession.openingPrices.SOXX, 100);
  assert.deepEqual(duringSession.series.SOXX, [["2026-09-10", 102]]);
  const afterClose = parseDailyBars(payload, new Date("2026-09-11T20:30:00Z"));
  assert.deepEqual(afterClose.series.SOXX, [["2026-09-10", 102], ["2026-09-11", 105]]);
  assert.equal(sessionComplete(new Date("2026-01-06T21:10:00Z")), false);
  assert.equal(sessionComplete(new Date("2026-01-06T21:20:00Z")), true);
});

test("a real flat return is zero, but bad quotes and missing symbols are unavailable", () => {
  const data = parseDailyBars({ bars: { SOXX: [{ t: "2026-09-10T04:00:00Z", o: 100, c: 100 }], SPY: [{ t: "invalid", o: 1, c: 2 }] } }, new Date("2026-09-12T12:00:00Z"));
  const result = buildComparison(equity, data.series, data.openingPrices);
  assert.equal(result.lines.SOXX.at(-1), 0);
  assert.equal(result.lines.SPY.at(-1), null);
  assert.equal(data.openingPrices.QQQ, null);
});
