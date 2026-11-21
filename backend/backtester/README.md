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
