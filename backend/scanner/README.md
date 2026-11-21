# Scanner (Person 1)

**Model:** Decisions API. It does not take YouTube links, so it scores the Watcher's text segments.

**Input:** Watcher segments (see `../watcher/README.md`).
**Output:** each segment with flags that feed the Extractor:
entry rule, exit rule, stop loss, filter, bold claim.

The same API also routes the user's questions to the NPC (shared with `api/`).
