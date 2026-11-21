# Backtester (Person 2)

**Model:** Gemini 4 Neon, managed agent. Writes strategy code in its sandbox and runs every
meaning of the rules on full crypto history with costs.

**Input:** `schemas/strategy_rules.json` and price files from `scripts/download_prices.py`.
**Output:** results and trades used in `schemas/npc_record.json`.
