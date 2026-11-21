# Extractor (Person 1)

**Model:** Gemini 4 Hydrogen, reading the Scanner's flagged segments as text (no extra video quota).

**Input:** Scanner output.
**Output** (`extract()` in `extractor.py`): one record matching `schemas/strategy_rules.json`, always
checked by `rules.validate()` before it's returned. Code, not the model, decides:

- `strategy_id`: sha1 of the normalized rules (timeframe, entry, exit, stop loss, filters, vague
  terms). Ignores order, case, punctuation, the name, timestamps, source videos and market.
  Re-extracting a video can word the rules differently and give a new id, so always read the id
  from the saved file in `data/strategies/`. Re-extracting a video whose NPC is already born is
  blocked, since it would orphan that NPC.
- `market.tested_on`: the stated market if we have its prices (BTC-USD, ETH-USD, SOL-USD), else BTC-USD.
  `market.stated` keeps what the creator said, so the NPC can say "my guru traded Apple".
- `strategy_name`: a short plain name like "Demand zone retest", never the creator's or channel's
  name. Not part of `strategy_id`. Empty string if unknown.
- `timeframe`: the price file to test on: `5m` for anything under an hour, `1h` for 1 to 4 hours,
  otherwise `1d`. The Backtester can resample up, e.g. 5m into 15m.
- `timestamp_s`: kept if it falls inside a flagged segment, otherwise moved to the nearest flagged
  segment start, so every rule points at a real moment.
- `vague_terms`: only terms with two or three meanings are kept.
- One strategy per record: a video that ranks or compares several strategies gets the one taught
  most completely, preferring the creator's own. A survey with no fully taught strategy is Untestable.
- A self-contradictory answer (testable but no entry rule) is asked again, up to 3 tries.
- `testable`: false if the model says so, or if there's no entry rule, or no exit and no stop loss.
  `untestable_reason` is then always filled in.
