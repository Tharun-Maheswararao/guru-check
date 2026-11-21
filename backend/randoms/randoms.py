"""1,000 random traders: plain code, the same every time, never written by a model.

Each random trader makes as many trades as the strategy, holds each one for one of the strategy's
own holding periods, keeps its long/short mix, pays the same costs, and trades the same market over
the same history. Only the timing is random. If the strategy can't beat that, its timing has no edge.
"""

import numpy as np

from backend.backtester.engine import COST, START_CASH

N_TRADERS = 1000


def race(close: np.ndarray, trades: list[dict], checkpoints: np.ndarray, n: int = N_TRADERS,
         seed: int = 7) -> dict:
    """Final balances and p10/p50/p90 equity at each checkpoint for n random traders."""
    closed = [t for t in trades if t["b"] > t["a"]]
    bars = len(close)
    if not closed:
        flat = np.full(len(checkpoints), START_CASH)
        return {"finals": np.full(n, START_CASH), "band": {q: flat for q in ["p10", "p50", "p90"]}}
    rng = np.random.default_rng(seed)
    durations = np.array([t["b"] - t["a"] for t in closed])
    sides = np.array([t["side"] for t in closed])
    k = len(closed)
    free = max(0, bars - 1 - int(durations.sum()))
    finals = np.empty(n)
    curves = np.empty((n, len(checkpoints)))
    for i in range(n):
        order = rng.permutation(k)
        d, s = durations[order], sides[rng.permutation(k)]
        gaps = rng.multinomial(free, np.full(k + 1, 1 / (k + 1)))[:k]
        starts = np.cumsum(gaps + np.concatenate([[0], d[:-1]]))
        ends = starts + d
        growth = close[ends] / close[starts]
        mult = np.where(s > 0, growth, 2 - growth) * (1 - COST) ** 2  # a short gains as price falls
        mult = np.maximum(mult, 0.0)
        wealth = START_CASH * np.cumprod(mult)
        finals[i] = wealth[-1]
        # Equity at each checkpoint: closed trades so far, times the open trade marked to market.
        done = np.searchsorted(ends, checkpoints, side="right")
        base = np.where(done > 0, wealth[np.maximum(done - 1, 0)], START_CASH)
        nxt = np.minimum(done, k - 1)
        inside = (done < k) & (starts[nxt] < checkpoints)
        live = close[checkpoints] / close[starts[nxt]]
        live = np.where(s[nxt] > 0, live, 2 - live) * (1 - COST)
        curves[i] = np.where(inside, base * np.maximum(live, 0.0), base)
    band = {q: np.percentile(curves, p, axis=0) for q, p in [("p10", 10), ("p50", 50), ("p90", 90)]}
    return {"finals": finals, "band": band}


def percentile_beaten(strategy_final: float, finals: np.ndarray) -> float:
    """Share of random traders (percent) that ended with less money than the strategy."""
    return float(100 * np.mean(finals < strategy_final))
