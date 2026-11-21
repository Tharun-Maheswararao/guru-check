"""Neon as a managed agent: writes the strategy code and tests it in a Google-hosted sandbox.

The Antigravity managed agent (antigravity-preview-09-2026) runs on gemini-4-neon in a remote Linux
sandbox with Python, pandas and numpy. We mount three files into it:

    /workspace/data/prices.csv     a recent slice of the real candles (inline sources max 1 MB)
    /workspace/data/readings.json  every reading of the vague terms
    /workspace/check.py            our test: every reading runs, positions have the right length,
                                   no lookahead at four cut-off points, some trades, safe imports

The agent writes /workspace/strategy.py, runs check.py, and fixes the code until it prints
ALL CHECKS PASSED, then returns the code. We still re-run every check locally on the full history
(codegen.run_code), so the agent never decides a number on its own.
"""

import json
import time

import pandas as pd

from backend import llm
from backend.config import model_settings

AGENT = "antigravity-preview-09-2026"
NEON = model_settings("NEON", "gemini-4-neon")
TIMEOUT_S = 240
MAX_CSV_BYTES = 950_000  # inline sources are limited to 1 MB per file
DONE = {"completed", "failed", "cancelled", "incomplete", "budget_exceeded"}

CHECK = r'''import ast, importlib.util, json
import numpy as np, pandas as pd

df = pd.read_csv("/workspace/data/prices.csv")
df.index = pd.to_datetime(df["timestamp"], unit="s", utc=True)
df = df[["open", "high", "low", "close", "volume"]].astype(float)
readings = json.load(open("/workspace/data/readings.json"))
src = open("/workspace/strategy.py").read()
ok = True
for node in ast.walk(ast.parse(src)):
    names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
    for name in names:
        if name.split(".")[0] not in {"numpy", "pandas", "math", "datetime"}:
            ok = False
            print(f"FORBIDDEN IMPORT: {name} (only numpy, pandas, math, datetime)")
spec = importlib.util.spec_from_file_location("strategy", "/workspace/strategy.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def positions(d, reading):
    p = np.sign(np.nan_to_num(np.asarray(mod.generate_positions(d.copy(), dict(reading)), dtype=float).reshape(-1)))
    assert len(p) == len(d), f"returned {len(p)} positions for {len(d)} bars"
    return p

traded = 0
for k, reading in enumerate(readings):
    try:
        changes = int(np.count_nonzero(np.diff(positions(df, reading))))
        traded += changes > 0
        print(f"reading {k}: {changes} position changes")
    except Exception as e:
        ok = False
        print(f"reading {k}: ERROR {type(e).__name__}: {e}")
if not traded:
    ok = False
    print("NO TRADES: no reading ever opens a position")
try:
    full = positions(df, readings[0])
    for frac in [0.2, 0.4, 0.6, 0.8]:
        cut = int(len(df) * frac)
        if not np.array_equal(full[:cut], positions(df.iloc[:cut], readings[0])):
            ok = False
            print(f"LOOKAHEAD: positions on the first {cut} bars change when later bars are added")
            break
except Exception as e:
    ok = False
    print(f"LOOKAHEAD CHECK ERROR: {type(e).__name__}: {e}")
print("ALL CHECKS PASSED" if ok else "CHECKS FAILED")
'''

TASK = """You are the Backtester in Guru Check. Your sandbox has:
- /workspace/data/prices.csv: {bars} recent {market} {timeframe} candles (columns timestamp, open,
  high, low, close, volume; timestamp is Unix seconds UTC). The real backtest runs on the full
  history ({full_bars} candles), so the code must be fast and general.
- /workspace/data/readings.json: every reading of the vague terms to support.
- /workspace/check.py: our test script.

Steps:
1. Write /workspace/strategy.py with the function described below.
2. Run `python /workspace/check.py`.
3. Read its output, fix strategy.py, and run it again until it prints ALL CHECKS PASSED.
4. Reply with the final, complete contents of /workspace/strategy.py in one ```python block.

{spec}"""


def sample_csv(df: pd.DataFrame) -> str:
    """The most recent candles that fit in one inline file."""
    rows = len(df)
    while True:
        part = df.iloc[-rows:]
        seconds = (part.index - pd.Timestamp(0, tz="UTC")) // pd.Timedelta(seconds=1)
        text = part.assign(timestamp=seconds)[["timestamp", "open", "high", "low", "close", "volume"]] \
            .to_csv(index=False, float_format="%.6g")
        if len(text.encode()) <= MAX_CSV_BYTES or rows < 500:
            return text
        rows = int(rows * MAX_CSV_BYTES / len(text.encode()) * 0.95)


def write_code(spec: str, rules: dict, df: pd.DataFrame, timeframe: str, readings: list[dict],
               timeout_s: int = TIMEOUT_S) -> tuple[str, dict]:
    """Run the managed agent and return (code, meta). Raises if it fails or runs out of time."""
    csv = sample_csv(df)
    bars = csv.count("\n") - 1
    task = TASK.format(bars=bars, market=rules["market"]["tested_on"], timeframe=timeframe,
                       full_bars=len(df), spec=spec)
    client = llm._client(NEON)
    start = time.time()
    interaction = client.interactions.create(
        agent=AGENT,
        agent_config={"type": "antigravity", "model": NEON.model},
        environment={"type": "remote", "sources": [
            {"type": "inline", "content": csv, "target": "/workspace/data/prices.csv"},
            {"type": "inline", "content": json.dumps(readings), "target": "/workspace/data/readings.json"},
            {"type": "inline", "content": CHECK, "target": "/workspace/check.py"},
        ]},
        background=True,
        input=task,
    )
    while interaction.status not in DONE:
        if time.time() - start > timeout_s:
            try:
                client.interactions.cancel(id=interaction.id)
            except Exception:
                pass
            raise TimeoutError(f"managed agent took longer than {timeout_s}s")
        time.sleep(4)
        interaction = client.interactions.get(interaction.id)
    seconds = time.time() - start
    text = interaction.output_text or ""
    meta = {"via": f"{AGENT} managed agent on {NEON.model}", "interaction_id": interaction.id,
            "environment_id": getattr(interaction, "environment_id", None), "status": interaction.status,
            "sandbox_steps": len(interaction.steps or []), "seconds": round(seconds, 1),
            "sample_bars": bars}
    llm._record("neon_managed", NEON.model, task, text, seconds)
    if interaction.status != "completed":
        raise RuntimeError(f"managed agent ended with status {interaction.status}")
    from backend.backtester.codegen import extract_code  # local import: codegen imports this module
    return extract_code(text), meta
