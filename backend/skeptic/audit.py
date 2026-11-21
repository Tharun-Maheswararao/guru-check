"""Second managed agent: the Carbon auditor checks the backtest independently in its own sandbox.

The Antigravity managed agent runs on gemini-4-carbon in a Google-hosted sandbox. It gets the
strategy code, recent real candles, the reading the NPC speaks for, our engine's rules, and our
engine's numbers on that same data. It must:

  1. run the strategy code itself,
  2. write its own backtest from the stated rules and recompute final balance, closed trades and
     max drawdown, then compare them with ours,
  3. try to catch lookahead: change prices after a cut-off and check that earlier positions stay put.

It replies with a JSON verdict. A mismatch or lookahead caps the NPC's verdict at Lucky. The audit
runs in parallel with the Carbon judge, and a failed or slow audit never blocks a birth.
"""

import io
import json
import time

import pandas as pd

from backend import llm
from backend.backtester.engine import COST, START_CASH, run_backtest
from backend.backtester.managed import AGENT, DONE, sample_csv
from backend.config import model_settings

CARBON = model_settings("CARBON", "gemini-4-carbon")
TIMEOUT_S = 200

RULES = f"""Backtest rules our engine uses (reproduce them exactly):
- positions[t] from generate_positions(df, reading) is the position decided at the close of bar t:
  1 long, -1 short, 0 flat (take the sign of whatever the function returns).
- It is held over the NEXT bar: bar t's return uses positions[t-1] (position 0 before the first bar).
- Bar return = close[t] / close[t-1] - 1. A bar's growth = max(1 + held * return, 0) * (1 - {COST} * |positions[t] - positions[t-1]|),
  i.e. the cost of a trade at the close of bar t is charged on bar t (positions[-1] counts as 0).
- Equity starts at {START_CASH:.0f} and multiplies by each bar's growth.
- A closed trade is each run of the same nonzero position that later changes (to flat or the opposite side);
  a run still open on the last bar is not counted.
- Max drawdown = min over bars of equity / running max of equity - 1, in percent (negative)."""

TASK = """You are the independent Auditor in Guru Check. Another model wrote a trading strategy and our
engine backtested it. Check that work yourself, in your sandbox. Files:
- /workspace/strategy.py: the strategy code, defining generate_positions(df, reading)
- /workspace/data/prices.csv: {bars} real {market} {timeframe} candles (timestamp = Unix seconds UTC;
  load with pd.read_csv, set df.index = pd.to_datetime(df.timestamp, unit="s", utc=True), keep open, high,
  low, close, volume as floats)
- /workspace/data/reading.json: the reading to pass as `reading`
- /workspace/data/expected.json: our engine's numbers for this exact data and reading

{rules}

Do all of this by running code:
1. Run generate_positions on the data with the reading.
2. Write YOUR OWN backtest from the rules above (don't trust any other code) and compute final_balance,
   closed_trades and max_drawdown_pct. Compare with expected.json: numbers match if final_balance and
   max_drawdown_pct are within 0.5% (relative) and closed_trades within 1.
3. Hunt for lookahead: at 3 cut points, replace every price AFTER the cut with nonsense (e.g. reverse or
   shuffle them), rerun, and check positions up to the cut are unchanged. Also read the code for
   shift(-k), centered windows, or whole-series max/min.

Reply with only this JSON:
{{"numbers_match": true or false, "recomputed": {{"final_balance": 0, "closed_trades": 0, "max_drawdown_pct": 0}},
  "lookahead_found": true or false, "notes": "one or two plain sentences on what you checked and found"}}"""


def _sample_frame(csv_text: str) -> pd.DataFrame:
    df = pd.read_csv(io.StringIO(csv_text))
    df.index = pd.to_datetime(df["timestamp"], unit="s", utc=True)
    return df[["open", "high", "low", "close", "volume"]].astype(float)


def expected_numbers(code: str, df: pd.DataFrame, reading: dict) -> dict:
    """Our engine's numbers on the sample, from the same sandboxed run the birth uses."""
    from backend.backtester.codegen import run_code

    positions, report = run_code(code, df, [reading])
    if positions[0] is None:
        raise RuntimeError(f"strategy failed on the audit sample: {report}")
    r = run_backtest(df, positions[0])
    return {"final_balance": round(r["final_balance"], 2), "closed_trades": r["n_trades"],
            "max_drawdown_pct": round(r["max_drawdown"], 2)}


def audit(code: str, df: pd.DataFrame, reading: dict, market: str, timeframe: str,
          timeout_s: int = TIMEOUT_S) -> dict:
    """Run the Carbon auditor. Returns its findings plus run details; raises if it fails or is slow."""
    csv = sample_csv(df)
    sample = _sample_frame(csv)
    expected = expected_numbers(code, sample, reading)
    client = llm._client(CARBON)
    task = TASK.format(bars=len(sample), market=market, timeframe=timeframe, rules=RULES)
    start = time.time()
    interaction = client.interactions.create(
        agent=AGENT,
        agent_config={"type": "antigravity", "model": CARBON.model},
        environment={"type": "remote", "sources": [
            {"type": "inline", "content": code, "target": "/workspace/strategy.py"},
            {"type": "inline", "content": csv, "target": "/workspace/data/prices.csv"},
            {"type": "inline", "content": json.dumps(reading), "target": "/workspace/data/reading.json"},
            {"type": "inline", "content": json.dumps(expected), "target": "/workspace/data/expected.json"},
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
            raise TimeoutError(f"auditor took longer than {timeout_s}s")
        time.sleep(4)
        interaction = client.interactions.get(interaction.id)
    seconds = time.time() - start
    text = interaction.output_text or ""
    llm._record("carbon_audit", CARBON.model, task, text, seconds)
    if interaction.status != "completed":
        raise RuntimeError(f"auditor ended with status {interaction.status}")
    found = llm.parse_json(text)
    return {
        "via": f"{AGENT} managed agent on {CARBON.model}",
        "numbers_match": bool(found.get("numbers_match")),
        "lookahead_found": bool(found.get("lookahead_found")),
        "recomputed": found.get("recomputed"), "expected": expected,
        "notes": str(found.get("notes", ""))[:600],
        "interaction_id": interaction.id, "sandbox_steps": len(interaction.steps or []),
        "seconds": round(seconds, 1), "sample_bars": len(sample),
    }


def failed_audit(audit_result: dict | None) -> str | None:
    """Why the audit should cap the verdict, or None if it passed or didn't run."""
    if not audit_result or audit_result.get("status") == "unavailable":
        return None
    if audit_result.get("lookahead_found"):
        return "The independent auditor found the strategy code peeking at future prices."
    if not audit_result.get("numbers_match"):
        return "The independent auditor's own backtest didn't reproduce our numbers."
    return None
