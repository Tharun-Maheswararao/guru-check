# Extractor (Person 1)

**Model:** Gemini 4 Hydrogen.

**Input:** flagged segments from the Scanner.
**Output:** strategy rules matching `schemas/strategy_rules.json`. Every vague term is listed
with two or three reasonable meanings, and videos that can't be coded set `testable: false`
with an `untestable_reason`.
