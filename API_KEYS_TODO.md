# Free API keys the agents can use — accounts you need to create

Everything runs today without any of these (yfinance + the earnings-ai map are keyless).
Each key below unlocks a richer input. Paste the key into `.env` (the placeholder line already exists);
the code picks it up automatically when the matching agent is wired to it.

| Key in `.env` | Where to sign up (free) | Free limit | What it would feed |
|---|---|---|---|
| `FRED_API_KEY` | https://fred.stlouisfed.org/docs/api/api_key.html (needs a free FRED account) | 120 req/min | `macro` agent: 10y/2y yields, CPI, unemployment, financial-conditions index |
| `FINNHUB_API_KEY` | https://finnhub.io/register | 60 calls/min | `llm_news`: cleaner company news feed + earnings calendar with estimates |
| `ALPHAVANTAGE_API_KEY` | https://www.alphavantage.co/support/#api-key — earnings-ai already has one in its `.env` (`ALPHAVANTAGE_API_KEY`); the same key can be copied here | 25 req/day | `events`: earnings calendar; news sentiment scores |
| `POLYGON_API_KEY` | https://polygon.io/dashboard/signup | 5 calls/min, end-of-day only | backup price source if yfinance breaks; ticker reference data |
| `EDGAR_USER_AGENT` | no account — SEC only asks for a contact e-mail in the header (already filled in) | ~10 req/s | future `filings` agent: 8-K material events, 10-Q text |

Not worth it right now: NewsAPI (non-commercial only, 24h delay on free), Twelve Data / EODHD (tiny free quotas), Quandl/Nasdaq Data Link (mostly paid now).

Already in place: Alpaca paper keys, Vercel Blob token.
