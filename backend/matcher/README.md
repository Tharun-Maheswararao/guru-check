# Matcher (Person 1)

**Model:** Decisions API.

**Input:** a new strategy rules record plus the closest saved strategies from `npc_store/`.
**Output:** either an existing `npc_id` (match score above about 90 percent, the link joins
that NPC) or a signal to birth a new NPC.

Same-link matching is a plain lookup and must always work, even if cross-video matching is cut.
