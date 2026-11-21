# Backtester (Person 2)

`birth.py: backtest_and_judge(rules, on_step) -> (npc_record, trades)` is Person 2's half of an NPC
birth. `backend/pipeline.py: birth_npc` calls it after the Matcher, then fills in the rule fields,
draws the portrait and saves the NPC.

## What happens

1. **backtest**
   - **Readings.** `engine.build_readings` turns the vague terms into up to 6 readings of the rules: all first meanings, all second, all third, then random mixes.
   - **Neon writes the code.** `codegen.py` has Gemini 4 Neon write one `generate_positions(df, reading)` with a branch for every meaning.
   - **The sandbox runs it.** `sandbox_runner.py` runs the code in a separate Python process with no environment (no API keys) and a 5 minute limit. Only numpy, pandas, math and datetime can be imported, and there's no `open`, `eval` or `exec`.
   - **Lookahead test.** Reading 0 is rerun on data cut off at six points. Every position, including the last one before the cut, must match the full run, which catches even a one-bar peek. If the code crashes, never trades or peeks, Neon gets the problem and one more try.
   - **The engine counts the money.** `engine.run_backtest` holds each signal over the next bar, so a signal never trades its own bar. It charges 0.15% per side (0.10% fee + 0.05% slippage) and computes equity, trades, win rate, drawdown and buy and hold.
2. **randoms**
   - **1,000 random traders.** `backend/randoms/randoms.py` makes as many trades as each reading, with the same holding periods, long/short mix and costs. Only the timing is random.
   - **Market check.** `backend/skeptic/factors.py` regresses daily returns on the market and on 30-day time-series momentum, both built from the same coin (the Kenneth French factors only cover US stocks).
3. **judge**
   - **Evidence verdict.** `skeptic.evidence_verdict` works out the best verdict the numbers allow:
     - **Real Edge:** beats 90% or more of random traders in at least two thirds of the readings, and keeps at least 2% a year of alpha with t ≥ 1.5.
     - **Just the Market:** beats 75% or more, but no alpha.
     - **Lucky:** everything else, and any code that failed the lookahead test.
   - **Carbon judges.** Gemini 4 Carbon reviews the code, checks every claim, writes the verdict reason and designs the fictional NPC: name, archetype and personality. It can be stricter than the evidence verdict, never kinder.

The NPC speaks for the **median** reading (the lower one when even) among readings with at least 5
trades, falling back to any reading that trades. So one lucky setting can't flatter it, and a
reading with one or two trades or none can't speak for it. If
no reading ever trades, the verdict is Untestable and `results` is null. Code saved by an earlier
birth of the same strategy is reused if it still passes every check, which speeds up retries.
The record also keeps every reading's results, the factor check, claim checks, code review and the
saved code (`data/code/<strategy_id>.py`).

## Inputs and outputs

- **Prices:** `data/prices/<market>_<timeframe>.csv` from `scripts/download_prices.py`.
  - A missing timeframe falls back to the next longer one (5m to 1h to 1d).
  - 5m uses the most recent 400,000 bars, about 3.8 years, so a birth stays a few minutes.
- **Record:** `schemas/npc_record.json` plus the fields in `frontend/README.md`, and `verdict_reason`, `readings`, `main_reading`, `factor_check`, `claim_checks`, `code_review`, `lookahead_free`, `tested` and `code_path`.
- **Trades:** `schemas/trades.json`, with 1,500 chart points and at most 600 trade markers.
- **Untestable rules** skip the backtest. Carbon still judges them and shapes the personality, and `results` is null.
