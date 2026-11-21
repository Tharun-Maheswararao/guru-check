# Matcher (Person 1)

**Model:** Gemini Decisions API.

`match_link(url, store)` runs first, before any model call: a video already in the library opens its
NPC right away.

`match(rules, store)` runs after extraction and returns one of:

| action | when | what the pipeline does |
|---|---|---|
| `join` (`same_rules`) | identical `strategy_id` already saved | adds the video to that strategy and NPC |
| `join` (`same_strategy`) | Decisions API says "same strategy" at or above `MATCH_THRESHOLD` (0.9) for one of the 3 most similar saved strategies (all 3 compared in one request) | same |
| `new` | otherwise | saves the strategy so Person 2 can backtest and birth an NPC |

The result also carries `strategy_id`, `npc_id` (null if not born yet), `score` and the `candidates`
it compared. Untestable strategies skip the Decisions comparison, since vague rules can't be compared.
