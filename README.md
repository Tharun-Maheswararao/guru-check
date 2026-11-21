# Guru Check: NPC Edition

Every trading strategy video becomes an NPC trader you can talk to and watch trade its whole
history with $10,000.

A user pastes a YouTube strategy link. Gemini watches the video, pulls out the exact rules, and
backtests them on the full history of crypto prices. The strategy is born as an NPC with its own
name, look and personality. A strategy already in the library opens its existing NPC.

> Not financial advice, a test of what the video claims.

## Pipeline

| Step | Component | Model | Owner |
|---|---|---|---|
| 1. Watch | `backend/watcher` | Gemini 4 Hydrogen | Person 1 |
| 2. Scan | `backend/scanner` | Decisions API | Person 1 |
| 3. Extract | `backend/extractor` | Gemini 4 Hydrogen | Person 1 |
| 4. Match | `backend/matcher` | Decisions API | Person 1 |
| 5. Backtest | `backend/backtester` | Gemini 4 Neon, managed agent | Person 2 |
| 6. Random traders | `backend/randoms` | plain code | Person 2 |
| 7. Judge | `backend/skeptic` | Gemini 4 Carbon | Person 2 |
| 8. Birth, talk, simulate | `frontend`, `backend/api` | Hydrogen voice, Gemini image | Person 3 |

Each NPC is stored as one record, so talking and simulating never rerun the backtest.

## Shared formats

These are the contracts between people. Change them only after telling the team.

- [`schemas/strategy_rules.json`](schemas/strategy_rules.json): Extractor output, Backtester input.
- [`schemas/npc_record.json`](schemas/npc_record.json): what Persons 2 and 3 read and write.
- Watcher segments: draft in [`backend/watcher/README.md`](backend/watcher/README.md).

Verdicts are exactly one of `Real Edge`, `Lucky`, `Just the Market`, `Untestable`.

## Repo layout

```
guru-check/
  schemas/          shared JSON formats
  backend/
    watcher/        Person 1
    scanner/        Person 1
    extractor/      Person 1
    matcher/        Person 1
    backtester/     Person 2
    randoms/        Person 2
    skeptic/        Person 2
    npc_store/      shared
    api/            shared
  frontend/         Person 3
  eval/videos.csv   20 test links plus ground truth
  scripts/download_prices.py
```

## Setup

```bash
cp .env.example .env   # then add your keys
python3 scripts/download_prices.py            # BTC, ETH, SOL daily into data/prices/
python3 scripts/download_prices.py --interval 1h
```

All data is free and public and none of it goes in the repo. `data/`, `.env`, `*.csv` (except
`eval/videos.csv`) and `*.parquet` are gitignored.

## Rules

- **No guru clones.** Every NPC is a fictional character with a link to the source video, never the real creator's name, face or voice.
- **The NPC can't lie about numbers.** Every figure it says comes from the saved backtest.
- **Video stays central.** The NPC cites video moments, like "the guru said this at 4:12".
- When a stock or forex strategy is tested on crypto, the NPC says so.
- Never download YouTube videos. Gemini reads the link directly.

## Schedule

Integration at 3:00 PM. Submit by 4:45 PM. If time runs short, cut in this order:

1. Portraits, using simple icons
2. NPC matching across different videos, keeping same link matching
3. Voice, keeping chat
4. Hourly data, keeping daily

NPC birth, honest answers, Simulate and the verdict must stay.
