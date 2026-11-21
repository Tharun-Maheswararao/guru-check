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

`birth_npc` is in `backend/pipeline.py` now. It runs Watcher, Scanner, Extractor and Matcher, then
waits for Person 2's `backend/backtester/birth.py`. Until that exists, run with `MOCK_BIRTH=1`.

## Gemini features

- **Rules on the timeline during birth.** As soon as the rules exist, the job's `preview` has the
  strategy name, video length and `rules_timeline`, and the birth screen pins them and reads them
  out one by one while the backtest runs.
- **Question routing.** `/talk` first sorts the question with the Decisions API
  (`backend/scanner/router.py`: trade, performance, period, comparison, rules, video, other) and tells
  Hydrogen what to focus on. The response includes `route`.
- **Portraits.** New NPCs get a Gemini image (`gemini-nano-banana-2.1`) at birth, saved to
  `data/portraits/`. The prompt forbids resembling any real person. Backfill existing NPCs with
  `python -m backend.api.portrait`. Turn off with `PORTRAITS=0`; the pixel sprite is the fallback.
- **Voice.** NPC answers are spoken by Gemini text to speech (`gemini-3.8-flash-lite-tts`, one voice
  per NPC color), falling back to the browser voice. Turn it off with `GEMINI_VOICE=0`.
  - **The audio starts early.** `/talk` starts making the audio as soon as the answer exists, split
    into the first sentence and the rest. The UI shows the text the moment the voice starts, so the
    two arrive together, with at most a 6 second wait before the text appears anyway.
  - Press `M` to mute.

Talk uses `GEMINI_TALK_MODEL` (Hydrogen model id) and answers only from the saved numbers; without a
key it uses template answers.
