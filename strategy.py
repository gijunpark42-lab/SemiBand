"""YOUR RULES GO HERE.

Right now this is empty on purpose: the bot only watches prices and never
trades. Nothing will be ordered until you put logic in decide().

decide() is called once per symbol per cycle. Return "BUY", "SELL", or None.

    bars      DataFrame of COMPLETED daily bars, oldest -> newest.
              columns: open / high / low / close / volume / trade_count / vwap
              Today is NOT in here -- use `price` for today.
    price     live last-traded price right now (IEX real-time)
    position  the open Alpaca Position for this symbol, or None if flat
"""


def decide(symbol, bars, price, position):
    return None
