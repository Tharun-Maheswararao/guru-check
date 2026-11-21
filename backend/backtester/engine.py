"""Backtest engine: plain code that turns positions into money. No model touches these numbers.

A strategy gives a target position per bar, -1 (short), 0 (flat) or 1 (long), decided at the close
of bar t using only data up to t. The engine holds that position over the next bar, so a signal can
never trade on the bar that produced it. Every change in position pays COST (fee plus slippage).
"""

import itertools
import random
from pathlib import Path

import numpy as np
import pandas as pd

from backend.config import DATA_DIR

START_CASH = 10_000.0
COST = 0.0015  # 0.10% fee + 0.05% slippage per unit of position change, per side
MAX_BARS = 400_000  # 5m history is cut to the most recent bars so a birth stays a few minutes
CHART_POINTS = 1500  # equity points kept for the Simulate replay
FALLBACK = {"5m": ["5m", "1h", "1d"], "1h": ["1h", "1d"], "1d": ["1d"]}


def load_prices(market: str, timeframe: str, data_dir: Path = DATA_DIR) -> tuple[pd.DataFrame, str]:
    """Candles for a market, falling back to a longer timeframe if that file wasn't downloaded."""
    for tf in FALLBACK.get(timeframe, ["1d"]):
        path = Path(data_dir) / "prices" / f"{market}_{tf}.csv"
        if path.exists():
            df = pd.read_csv(path)
            df.index = pd.to_datetime(df["timestamp"], unit="s", utc=True)
            df = df[["open", "high", "low", "close", "volume"]].astype(float)
            if len(df) > MAX_BARS:
                df = df.iloc[-MAX_BARS:]
            return df, tf
    raise FileNotFoundError(f"No price file for {market}. Run: python3 scripts/download_prices.py")


def build_readings(vague_terms: list[dict], seed: str = "", limit: int = 6) -> list[dict]:
    """Reasonable readings of the rules: one meaning chosen per vague term.

    All first meanings, all second, all third, then random mixes, up to `limit`. With few terms
    every combination is tried.
    """
    if not vague_terms:
        return [{}]
    terms = {v["term"]: v["meanings"] for v in vague_terms}
    combos = int(np.prod([len(m) for m in terms.values()]))
    if combos <= limit:
        return [dict(zip(terms, c)) for c in itertools.product(*terms.values())]
    readings, seen = [], set()

    def add(reading: dict) -> None:
        key = tuple(reading.values())
        if key not in seen:
            seen.add(key)
            readings.append(reading)

    for k in range(3):
        add({t: m[min(k, len(m) - 1)] for t, m in terms.items()})
    rng = random.Random(seed)
    while len(readings) < limit:
        add({t: rng.choice(m) for t, m in terms.items()})
    return readings


def clean_positions(raw, n: int) -> np.ndarray:
    pos = np.asarray(raw, dtype=float).reshape(-1)
    if len(pos) != n:
        raise ValueError(f"strategy returned {len(pos)} positions for {n} bars")
    return np.sign(np.nan_to_num(pos)).astype(np.int8)


def run_backtest(df: pd.DataFrame, positions: np.ndarray) -> dict:
    """Equity, trades and headline numbers for one set of positions."""
    close = df["close"].to_numpy()
    n = len(close)
    ret = np.zeros(n)
    ret[1:] = close[1:] / close[:-1] - 1
    held = np.zeros(n)
    held[1:] = positions[:-1]  # position from the previous close is held over this bar
    change = np.abs(np.diff(np.concatenate([[0.0], positions.astype(float)])))
    # The bar's move, then the cost of any trade at its close, charged on the position's value then.
    growth = np.maximum(1 + held * ret, 0.0) * (1 - COST * change)
    bar_ret = growth - 1
    equity = START_CASH * np.cumprod(growth)

    def pnl(a: int, b: int) -> float:
        before = equity[a - 1] if a > 0 else START_CASH  # equity before the entry cost
        return float(equity[b] / before - 1) if before > 0 else 0.0

    # A trade runs from the bar its position is opened to the bar it is closed or flipped.
    trades = []
    changes = np.flatnonzero(np.diff(np.concatenate([[0], positions.astype(int)])))
    for k, a in enumerate(changes):
        side = int(positions[a])
        if side == 0:
            continue
        b = int(changes[k + 1]) if k + 1 < len(changes) else n - 1
        trades.append({"side": side, "a": int(a), "b": b, "pnl": pnl(int(a), b), "open": k + 1 >= len(changes)})

    peak = np.maximum.accumulate(equity)
    dd = np.where(peak > 0, equity / peak - 1, 0)
    closed = [t for t in trades if not t.get("open")]
    return {
        "equity": equity, "bar_ret": bar_ret, "trades": trades, "positions": positions,
        "final_balance": float(equity[-1]),
        "max_drawdown": float(dd.min() * 100),
        "trough": int(dd.argmin()),
        "win_rate": float(100 * np.mean([t["pnl"] > 0 for t in closed])) if closed else 0.0,
        "n_trades": len(closed),
        "hold_final": float(START_CASH * close[-1] / close[0]),
        "exposure": float(np.mean(positions != 0)),
    }


def lookahead_free(full: np.ndarray, truncated: np.ndarray) -> bool:
    """Positions computed on cut-off data must equal the full run's on the shared bars (but the last)."""
    k = len(truncated) - 1
    return bool(k > 0 and np.array_equal(full[:k], truncated[:k]))


def chart_index(n: int, points: int = CHART_POINTS) -> np.ndarray:
    return np.unique(np.linspace(0, n - 1, min(points, n)).astype(int))
