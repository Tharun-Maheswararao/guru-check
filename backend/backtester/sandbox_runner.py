"""Runs Neon's strategy code in a separate, locked-down Python process.

    python -I sandbox_runner.py CODE.py PRICES.csv READINGS.json OUT_DIR [MAX_BARS]

The code may import only numpy, pandas, math and datetime, and gets no open/eval/exec. The parent
process starts this with an empty environment (no API keys) and a time limit. For each reading it
writes OUT_DIR/positions_<k>.npy, and it writes OUT_DIR/report.json with errors and the lookahead
check: reading 0 is run again on data cut off at several points, and every position, including the
one on the last bar before the cut, must match the full run. Code that peeks even one bar ahead
gives a different last position when that bar is missing.
"""

import builtins
import json
import sys
import traceback

import numpy as np
import pandas as pd

ALLOWED = {"numpy", "pandas", "math", "datetime"}
CUTS = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]  # cut-off points for the lookahead check
BLOCKED = {"open", "eval", "exec", "compile", "input", "breakpoint", "__import__", "exit", "quit", "help"}


def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name.split(".")[0] not in ALLOWED:
        raise ImportError(f"import of {name!r} is not allowed in strategy code")
    return builtins.__import__(name, globals, locals, fromlist, level)


def load_strategy(code: str):
    safe = {k: getattr(builtins, k) for k in dir(builtins) if k not in BLOCKED}
    safe["__import__"] = _safe_import
    namespace = {"__builtins__": safe, "__name__": "strategy"}
    exec(compile(code, "strategy.py", "exec"), namespace)
    if "generate_positions" not in namespace:
        raise NameError("strategy code must define generate_positions(df, reading)")
    return namespace["generate_positions"]


def positions_for(fn, df: pd.DataFrame, reading: dict) -> np.ndarray:
    raw = fn(df.copy(), dict(reading))
    pos = np.asarray(raw, dtype=float).reshape(-1)
    if len(pos) != len(df):
        raise ValueError(f"returned {len(pos)} positions for {len(df)} bars")
    return np.sign(np.nan_to_num(pos)).astype(np.int8)


def main() -> None:
    code_path, prices_path, readings_path, out_dir = sys.argv[1:5]
    df = pd.read_csv(prices_path)
    df.index = pd.to_datetime(df["timestamp"], unit="s", utc=True)
    df = df[["open", "high", "low", "close", "volume"]].astype(float)
    readings = json.load(open(readings_path))
    report = {"errors": {}, "lookahead_free": None, "trades_per_reading": {}}
    try:
        fn = load_strategy(open(code_path).read())
    except Exception:
        report["load_error"] = traceback.format_exc(limit=3)[-2000:]
        json.dump(report, open(f"{out_dir}/report.json", "w"))
        return
    for k, reading in enumerate(readings):
        try:
            pos = positions_for(fn, df, reading)
            np.save(f"{out_dir}/positions_{k}.npy", pos)
            report["trades_per_reading"][k] = int(np.count_nonzero(np.diff(pos.astype(int))))
            if k == 0:
                report["lookahead_free"] = True
                for frac in CUTS:
                    cut = max(2, int(len(df) * frac))
                    early = positions_for(fn, df.iloc[:cut], reading)
                    if not np.array_equal(pos[:cut], early):
                        report["lookahead_free"] = False
                        report["lookahead_first_diff_bar"] = int(np.flatnonzero(pos[:cut] != early)[0])
                        break
        except Exception:
            report["errors"][k] = traceback.format_exc(limit=3)[-2000:]
    json.dump(report, open(f"{out_dir}/report.json", "w"))


if __name__ == "__main__":
    main()
