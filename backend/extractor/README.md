# Extractor (Person 1)

**Model:** Gemini 4 Hydrogen, reading the Scanner's flagged segments as text (no extra video quota).

**Input:** Scanner output.
**Output** (`extract()` in `extractor.py`): one record matching `schemas/strategy_rules.json`, always
checked by `rules.validate()` before it's returned. Code, not the model, decides:

- `strategy_id`: sha1 of the normalized rules (timeframe, entry, exit, stop loss, filters, vague
  terms). Ignores order, case, punctuation, timestamps, source videos and market.
- `market.tested_on`: the stated market if we have its prices (BTC-USD, ETH-USD, SOL-USD), else BTC-USD.
  `market.stated` keeps what the creator said, so the NPC can say "my guru traded Apple".
- `timeframe`: `1h` for anything up to 4 hours, otherwise `1d`, since those are the price files we have.
- `timestamp_s`: kept if it falls inside a flagged segment, otherwise moved to the nearest flagged
  segment start, so every rule points at a real moment.
- `vague_terms`: only terms with two or three meanings are kept.
- `testable`: false if the model says so, or if there's no entry rule, or no exit and no stop loss.
  `untestable_reason` is then always filled in.
