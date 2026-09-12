# Descriptive attribution addendum — 2026-09-12

The original five variants, financing/cost scenarios and acceptance screen remain frozen. After the recent results were available and before stress completion, the user clarified that the concern was selected-stock performance being diluted by cash at account level, rather than a higher numerical leverage ceiling. This is a post-declaration descriptive analysis, not a new tested/adoptable variant or a change of objective after results.

For cap-tier costs and the primary 5% financing scenario, use the exact same realized names, relative weights and next-open returns. Define gross `g`, price return `p`, normalized sleeve `s=p/g` for positive gross, benchmark return `b`, account trading debit `c` and financing debit `f`. On zero-exposure dates set `s=0` for the accounting identity, but exclude those dates from the normalized sleeve's performance comparison and show SOXX on the same active dates.

Report full and OOS account return, sleeve-before-cost return, matched-active-date SOXX and mean exposure/cash. The unit-gross sleeve does not model its own turnover, liquidity, financing or changed volatility control and is not an executable alternative. A matched-gross benchmark uses `g*b`; an implementation-neutral diagnostic deducts the same realized `c+f` as the stock portfolio, explicitly not claiming those are SOXX's own transaction costs.

Reconcile the exact daily arithmetic identity `account-b = g*(s-b) + (g-1)*b - c - f`. Average its terms in basis points/day for full periods and on exactly matched days where baseline gross is below 20%, retaining zero-exposure days. Do not add compounded return gaps as if they were an exact cumulative attribution. Low-exposure-day results are conditional descriptive statistics, not continuous performance.

Small Sharpe gaps do not prove inferiority. Keep declared screen failures separate from a deliberate higher-total-return/higher-drawdown preference. The PAPER account's two sessions cannot establish selected-stock edge. No new variant, threshold, floor, model fitting, market snapshot, adoption decision or operational action is introduced by this addendum.
