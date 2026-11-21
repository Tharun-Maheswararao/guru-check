"""Gemini 4 Neon writes the strategy as Python; the sandbox runner executes it.

Neon writes one generate_positions(df, reading) for the whole strategy, with a branch for every
meaning of every vague term, so each reading of the rules is the same code with a different switch.
If the code crashes or peeks at future bars, Neon gets the error and one more try.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd

from backend import llm
from backend.config import DATA_DIR, model_settings

NEON = model_settings("NEON", "gemini-4-neon")
RUNNER = Path(__file__).with_name("sandbox_runner.py")
TIMEOUT_S = 300

PROMPT = """Write a Python function that turns these trading rules into positions, for a backtest.

RULES (from a YouTube video, as JSON):
{rules}

Data: {bars} candles of {market} at {timeframe} timeframe, {start} to {end} (UTC).

Write exactly this function:

def generate_positions(df, reading):
    # df: pandas DataFrame, DatetimeIndex in UTC, float columns open, high, low, close, volume.
    # reading: dict mapping each vague term to ONE of its listed meanings (exact strings):
{reading_keys}
    # Return a list or numpy array of len(df) ints: the position to hold from the close of bar t,
    # 1 = long, -1 = short, 0 = flat.

Hard requirements:
- No lookahead: positions[t] may only use rows 0..t. Never use shift(-k), centered windows, future
  rows, or the whole series' max/min. If you resample to a higher timeframe, use only completed
  higher-timeframe bars: shift the resampled series by one bar before forward filling it back.
- Implement every rule: entries, exits, stop loss and filters. Track stops and targets in a loop over
  bars using that bar's high/low; when hit, go flat at that bar.
- Implement every meaning of every vague term with `if reading[term] == "<meaning>":` branches.
- Trade long and short only if the rules do. Use full position size (1 or -1).
- If a rule names a session or time (e.g. London open), use the UTC index (London open is 08:00
  Europe/London, about 07:00 or 08:00 UTC).
- If a level is drawn by hand in the video (zones, swing points), define it mechanically from past
  bars, as simply as the rules allow.
- Imports: only numpy, pandas, math, datetime. No file, network or print calls.
- Keep it fast: loops over up to 400,000 bars must finish in about a minute.

Return only the code in one ```python block."""

FIX = """

Your previous attempt:
```python
{code}
```
It had this problem:
{problem}

Fix it and return the full corrected code in one ```python block."""


def extract_code(text: str) -> str:
    blocks = re.findall(r"```(?:python)?\s*\n(.*?)```", text, re.S)
    code = max(blocks, key=len) if blocks else text
    if "def generate_positions" not in code:
        raise ValueError("Neon's answer has no generate_positions function")
    return code.strip() + "\n"


def write_code(rules: dict, df: pd.DataFrame, timeframe: str,
               previous: tuple[str, str] | None = None) -> str:
    """Ask Neon for the strategy code. previous = (code, problem) asks it to fix an earlier attempt."""
    keys = "\n".join(f"    #   {json.dumps(v['term'])}: one of {json.dumps(v['meanings'])}"
                     for v in rules.get("vague_terms", [])) or "    #   (no vague terms: reading is {})"
    shown = {k: rules[k] for k in ["timeframe", "entry", "exit", "stop_loss", "filters", "vague_terms"]}
    shown["market"] = rules["market"]
    prompt = PROMPT.format(rules=json.dumps(shown, indent=1), bars=len(df), market=rules["market"]["tested_on"],
                           timeframe=timeframe, start=df.index[0].date(), end=df.index[-1].date(),
                           reading_keys=keys)
    if previous:
        prompt += FIX.format(code=previous[0], problem=previous[1][:3000])

    def call() -> str:
        start = time.time()
        interaction = llm._client(NEON).interactions.create(
            model=NEON.model, store=False, input=[{"type": "text", "text": prompt}],
            generation_config={"thinking_level": "medium"})
        text = interaction.output_text or ""
        llm._record("neon_code", NEON.model, prompt, text, time.time() - start)
        return text

    return extract_code(llm._retry(call, attempts=3))


def run_code(code: str, df: pd.DataFrame, readings: list[dict]) -> tuple[list[np.ndarray | None], dict]:
    """Run the code for every reading in the sandbox. Returns positions per reading and the report."""
    with tempfile.TemporaryDirectory(prefix="guru-sandbox-") as tmp:
        tmp = Path(tmp)
        (tmp / "strategy.py").write_text(code)
        # Unix seconds, whatever unit pandas stores the index in (pandas 3 uses microseconds).
        seconds = (df.index - pd.Timestamp(0, tz="UTC")) // pd.Timedelta(seconds=1)
        df.assign(timestamp=seconds).to_csv(tmp / "prices.csv", index=False)
        (tmp / "readings.json").write_text(json.dumps(readings))
        env = {"PATH": os.environ.get("PATH", ""), "HOME": str(tmp), "PYTHONHASHSEED": "0"}
        try:
            subprocess.run([sys.executable, "-I", str(RUNNER), str(tmp / "strategy.py"), str(tmp / "prices.csv"),
                            str(tmp / "readings.json"), str(tmp)],
                           cwd=tmp, env=env, timeout=TIMEOUT_S, capture_output=True, text=True)
        except subprocess.TimeoutExpired:
            return [None] * len(readings), {"errors": {}, "timeout": True, "load_error": f"timed out after {TIMEOUT_S}s"}
        report_path = tmp / "report.json"
        report = json.loads(report_path.read_text()) if report_path.exists() else {"load_error": "runner crashed"}
        positions = [np.load(tmp / f"positions_{k}.npy") if (tmp / f"positions_{k}.npy").exists() else None
                     for k in range(len(readings))]
    return positions, report


def problem_with(positions: list, report: dict) -> str | None:
    """Why the code needs fixing, or None if it's usable."""
    if report.get("timeout"):
        return f"It took longer than {TIMEOUT_S} seconds. Make it faster (vectorize, fewer loops)."
    if report.get("load_error"):
        return "It failed to load:\n" + report["load_error"]
    if all(p is None for p in positions):
        return "It crashed for every reading:\n" + next(iter(report["errors"].values()), "")
    if report.get("lookahead_free") is False:
        return (f"It uses future data: positions on early bars change when later bars are added "
                f"(first at bar {report.get('lookahead_first_diff_bar')}). Use only rows 0..t for positions[t].")
    if all(p is not None and not np.any(p) for p in positions):
        return "It never opens a position on any reading. Check the entry conditions are reachable."
    return None


def code_and_positions(rules: dict, df: pd.DataFrame, timeframe: str, readings: list[dict],
                       attempts: int = 2, save_dir: Path | None = None) -> dict:
    """Neon writes the code, the sandbox runs it, and Neon fixes it once if needed.

    Code saved by an earlier birth of the same strategy is reused if it still passes every check,
    which saves a minute or two when a birth is retried.
    """
    save_dir = Path(save_dir or DATA_DIR / "code")
    code_path = save_dir / f"{rules['strategy_id']}.py"
    if code_path.exists():
        positions, report = run_code(code_path.read_text(), df, readings)
        if problem_with(positions, report) is None:
            return {"code": code_path.read_text(), "code_path": str(code_path), "positions": positions,
                    "report": report, "problem": None, "reused": True}
    code, positions, report, problem = "", [], {}, None
    for _ in range(attempts):
        code = write_code(rules, df, timeframe, (code, problem) if problem else None)
        positions, report = run_code(code, df, readings)
        problem = problem_with(positions, report)
        if problem is None:
            break
    save_dir.mkdir(parents=True, exist_ok=True)
    code_path.write_text(code)
    return {"code": code, "code_path": str(code_path), "positions": positions, "report": report,
            "problem": problem}
