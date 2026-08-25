"""Central settings. Edit the values below; secrets stay in .env."""
import os

from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("ALPACA_API_KEY")
SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
if not API_KEY or not SECRET_KEY:
    raise RuntimeError("Missing ALPACA_API_KEY / ALPACA_SECRET_KEY in .env")

PAPER = True                     # never flip this without a deliberate decision

# --- what to trade ---
WATCHLIST = [
    # large cap
    "NVDA", "AMD", "INTC", "AVGO", "QCOM", "TXN", "MU", "ADI", "ARM", "TSM",
    "ASML", "STM", "MRVL", "NXPI", "MCHP", "ON", "MPWR", "GFS",
    # equipment
    "AMAT", "LRCX", "KLAC", "TER", "ENTG", "ACLS", "AEIS", "ICHR", "UCTT",
    "COHU", "FORM", "NVMI", "CAMT", "VECO", "AMKR",
    # small / mid cap
    "SWKS", "QRVO", "WOLF", "ALGM", "SITM", "LSCC", "RMBS", "CRUS", "SLAB",
    "POWI", "AOSL", "DIOD", "SYNA", "IMOS", "AXTI", "SNDK", "SMCI",
    "ALAB", "CRDO", "MTSI",
    # sector ETFs
    "SMH", "SOXX", "SOXL",
]

# --- universe ---
# earnings-ai holds the company list; tickers.py extracts the US-listed
# slice for the news stream. Separate from WATCHLIST, which is what trades.
EARNINGS_AI_DIR = "C:/Users/calif/OneDrive/Desktop/earnings-ai"

# The universe (tickers.json) grouped by sector. Every subscribable ticker
# appears in exactly one group; ambiguous names sit where the AI/data-center
# angle puts them (AMD -> GPU, STM -> power semis, AVGO/MRVL -> AI 가속기).
SECTORS = {
    "photonics": [
        "AAOI", "AEHR", "AXTI", "CIEN", "COHR", "FN", "FORM", "GFS",
        "GLW", "LITE", "MRVL", "MTSI", "NOK", "SMTC", "TSEM", "VIAV",
    ],
    "memory": [
        "MU", "RMBS", "SIMO", "SNDK", "STX", "WDC",
    ],
    "cpu": [
        "AMD", "ARM", "INTC", "QCOM",
    ],
    "gpu": [  # includes AI accelerators (custom ASIC)
        "AVGO", "NVDA",
    ],
    "hyperscaler": [
        "AMZN", "GOOGL", "META", "MSFT", "ORCL",
        # neocloud / AI data centers
        "APLD", "CORZ", "CRWV", "IREN", "NBIS",
    ],
    "power_semi": [
        "MPWR", "NVTS", "ON", "POWI", "STM", "VICR", "VSH", "WOLF",
    ],
    "pcb": [
        "TTMI",
        # connectors
        "APH", "TEL",
    ],
    "power_equipment": [
        "BE", "EME", "ETN", "FLNC", "GEV", "NVT", "VRT",
        # cooling / HVAC
        "JCI", "MOD", "TT",
    ],
    "utilities": [  # power generation
        "CEG", "EXC", "VST",
    ],
    "networking": [  # copper networking / interconnect
        "ALAB", "ANET", "CRDO",
    ],
    "server_hardware": [
        "CSCO", "DELL", "HPE", "SMCI",
        # EMS (contract manufacturing)
        "CLS", "FLEX", "JBL",
    ],
    "packaging": [  # OSAT / advanced packaging
        "AMKR", "ASX",
    ],
    "other": [
        # equipment
        "AMAT", "ASML", "CAMT", "COHU", "ENTG", "KEYS", "KLAC", "KLIC",
        "LRCX", "MKSI", "NVMI", "ONTO", "TER", "VECO",
        # foundry
        "TSM",
        # EDA
        "CDNS", "SNPS",
        # analog
        "ADI", "TXN",
        # everything else
        "AAPL", "ADBE", "LIN", "LUMN", "MMM", "SHEL", "SOLS", "UBER",
    ],
}

# --- data ---
LOOKBACK_DAYS = 200              # completed daily bars handed to the strategy

# --- strategy: P/S band ---
PS_BUY_PCT = 20                  # buy when today's P/S is in the bottom 20% of its history
PS_SELL_PCT = 80                 # sell when it is in the top 20%
PS_MIN_HISTORY = 60              # bars of valid P/S needed; Yahoo gives ~5 quarters,
                                 # so a full-TTM band is only ~3-6 months long
MAX_NEW_ENTRIES = 3              # per cycle, the cheapest BUY candidates by P/S percentile

# --- strategy: guidance exit (earnings_stream.py -> guidance.json) ---
GUIDANCE_FILE = "guidance.json"
EPS_VS_SALES_RATIO = 2           # exit if EPS guide cut is >= this x the sales guide raise
GUIDANCE_COOLDOWN_DAYS = 75      # no re-entry after a guidance exit until roughly the next print

# --- execution ---
DRY_RUN = False                  # True = log intended orders, send nothing
POSITION_PCT = 0.10              # each new entry = this share of account equity
MAX_TOTAL_EXPOSURE_USD = 100_000 # total long exposure cap; equity = no leverage.
                                 # overnight margin is only 2x ($200k), not the
                                 # 4x intraday figure, so holding past the close
                                 # above this is what triggers a margin call.
POLL_SECONDS = 60                # price-monitoring interval while market is open
