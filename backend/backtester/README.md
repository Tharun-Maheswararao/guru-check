# Backtester (Person 2)

**Model:** Gemini 4 Neon, managed agent. Writes strategy code in its sandbox and runs every
meaning of the rules on full crypto history with costs.

**Input:** new strategies in `data/strategies/<strategy_id>.json` (format: `schemas/strategy_rules.json`)
and price files from `scripts/download_prices.py` in `data/prices/<market>_<timeframe>.csv`.

- `timeframe` is `5m`, `1h` or `1d` and names the price file to load. Resample up if the rules need
  15m or 4h candles. 5m files aren't downloaded by default:
  `python3 scripts/download_prices.py --interval 5m` (about 15 minutes per coin; it resumes if stopped).
- Strategies can trade long and short.
- Use `strategy_id` exactly as saved in the file, and save the born NPC with the same id
  (`Store().save_npc(record)` in `backend/npc_store/store.py`).
- `strategy_name` is a short plain name you can use in logs; Person 3 can use it for the NPC.
**Output:** results and trades used in `schemas/npc_record.json`.

## Handoff: how an NPC gets born

`birth_npc(url, on_step)` in `backend/pipeline.py` (what the web app calls) runs Watcher, Scanner,
Extractor and Matcher, then calls **your** function:

```python
# backend/backtester/birth.py
def backtest_and_judge(rules: dict, on_step) -> tuple[dict, dict]:
    on_step("backtest", "Neon agent is backtesting every meaning of the rules")
    ...
    on_step("randoms", "Racing 1,000 random traders")
    ...
    on_step("judge", "Carbon is judging the claims")
    ...
    return npc_record, trades
```

- `rules` is one record shaped like `schemas/strategy_rules.json`, already saved in `data/strategies/`.
  Untestable strategies come through too (`testable: false`): skip the backtest, give the Untestable
  verdict and personality.
- `npc_record` is shaped like `schemas/npc_record.json`, plus the extra fields in
  `frontend/README.md` (`color`, `archetype`, and `hold_final`, `share_random_better`, `n_trades` in
  `results`). It needs a unique `npc_id`.
- `trades` is shaped like `schemas/trades.json`.
- Leave out `strategy_id`, `strategy_name`, `source_videos`, `market`, `rules_timeline` and
  `untestable_reason`: `birth_npc` fills those from the rules. It also saves both files and reports
  the `born` step, so don't save them yourself.

Until `backend/backtester/birth.py` exists, a birth stops at the backtest step with a message saying so.
Rehearse the UI with `MOCK_BIRTH=1` meanwhile.
