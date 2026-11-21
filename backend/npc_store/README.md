# NPC store (shared)

`store.py` keeps the library as JSON files under `data/` (gitignored):

```
data/npcs/<npc_id>.json             one NPC record (schemas/npc_record.json), written at birth
data/strategies/<strategy_id>.json  one strategy rules record, written when a new strategy is extracted
data/runs/<video_id>/               cached Watcher, Scanner, Extractor and Matcher output per video
```

Person 2: new strategies to backtest are the files in `data/strategies/` without an NPC yet.
Save the born NPC with `Store().save_npc(record)`, using the same `strategy_id`.

Talking and simulating read from here and never rerun the backtest.
