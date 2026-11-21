# Frontend (Person 3)

Web app, NPC library, voice chat, Simulate replay and portraits. Reads NPC records shaped like
`schemas/npc_record.json`. Every screen shows "Not financial advice, a test of what the video claims."

## Run

```bash
pip install -r requirements.txt
python3 frontend/mock_npcs.py                     # 4 fake NPCs marked DEMO DATA
MOCK_BIRTH=1 GEMINI_API_KEY=... uvicorn backend.api.server:app --reload --port 8000
open http://localhost:8000                        # Chrome, for voice
```

Screens: Library (paste link, birth steps, trader cards), NPC Room (sprite or portrait, speech bubble
with video citation, stats, clickable video timeline, text and voice chat), Simulate (race vs hold
and 1,000 random traders, Pain Moment, ending). Press `M` to mute sounds. Stage script: `DEMO.md`.

## What I need from Persons 1 and 2

1. **NPC record** in `data/npcs/<npc_id>.json`, as `schemas/npc_record.json`, plus these optional
   fields the UI uses: `color` (gold, green, red, cyan, violet), `archetype`,
   `rules_timeline` `[{kind: entry|exit|stop_loss|filters|claim, rule, timestamp_s}]`,
   `market {stated, tested_on}`, `untestable_reason`, and in `results`: `hold_final`,
   `share_random_better`, `n_trades`.
2. **Trades file** at the record's `trades_path`, shaped like `schemas/trades.json`
   (dates, price, equity, hold, random_band p10/p50/p90, trades, pain_moment).
3. **`backend/pipeline.py`** with `birth_npc(url, on_step) -> record`, calling
   `on_step(step, detail)` for each step: watch, scan, extract, match, backtest, randoms, judge, born.
   `backend/npc_store/store.py` has `save_npc(record, trades)` to write both files.

Until 3 exists, run with `MOCK_BIRTH=1`. Talk uses `GEMINI_TALK_MODEL` (Hydrogen model id) and
answers only from the saved numbers; without a key it uses template answers.
