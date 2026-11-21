"""The "Just the Market" check: does any profit survive once market and momentum are removed?

The Kenneth French factors describe US stocks, so for crypto we build the two that matter from the
same price history: the market itself (holding the coin) and time-series momentum (holding it only
after it rose over the last 30 days, and shorting after it fell). The strategy's daily returns are
regressed on both. A strategy whose profit is all beta has an alpha near zero.
"""

import numpy as np
import pandas as pd


def factor_check(df: pd.DataFrame, bar_ret: np.ndarray, lookback_days: int = 30) -> dict:
    strat = pd.Series(bar_ret, index=df.index)
    daily = (1 + strat).resample("1D").prod() - 1
    market = df["close"].resample("1D").last().pct_change()
    trend = np.sign(df["close"].resample("1D").last().pct_change(lookback_days)).shift(1)
    momentum = trend * market
    data = pd.concat([daily, market, momentum], axis=1, keys=["s", "m", "mom"]).dropna()
    if len(data) < 60 or data["s"].std() == 0:
        return {"alpha_annual_pct": 0.0, "alpha_t": 0.0, "beta_market": 0.0, "beta_momentum": 0.0,
                "r2": 0.0, "days": len(data)}
    X = np.column_stack([np.ones(len(data)), data["m"], data["mom"]])
    y = data["s"].to_numpy()
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ coef
    dof = max(1, len(y) - X.shape[1])
    sigma2 = resid @ resid / dof
    se = np.sqrt(np.diag(sigma2 * np.linalg.pinv(X.T @ X)))
    r2 = 1 - (resid @ resid) / max(1e-12, ((y - y.mean()) ** 2).sum())
    return {
        "alpha_annual_pct": round(float(coef[0] * 365 * 100), 2),
        "alpha_t": round(float(coef[0] / se[0]) if se[0] > 0 else 0.0, 2),
        "beta_market": round(float(coef[1]), 2),
        "beta_momentum": round(float(coef[2]), 2),
        "r2": round(float(r2), 3),
        "days": int(len(data)),
    }
