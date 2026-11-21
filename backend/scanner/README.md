# Scanner (Person 1)

**Model:** Gemini Decisions API (`gemini-decision-1`). It does not take YouTube links, so it scores
the Watcher's text segments.

**Input:** Watcher segments (see `../watcher/README.md`).

**Output** (`scan()` in `scanner.py`): every segment, plus:

```json
{
  "segment_id": 3, "start_s": 70, "end_s": 90, "speech": "...", "on_screen": "...",
  "flags": {"entry": 0.02, "exit": 0.95, "stop_loss": 0.94, "filter": 0.03, "setup": 0.04, "claim": 0.02},
  "labels": ["exit", "stop_loss"]
}
```

and a `timeline` list of `{segment_id, start_s, label, probability}` for marking rule moments and
bold claims on the video timeline. Segments go in chunks of 10: one Decisions request holds the
chunk's text and asks all six yes/no questions about each segment in it (60 questions), so a
20 minute video takes about 6 requests. A label is set when its probability reaches
`SCAN_THRESHOLD` (default 0.5).

**Question routing** (`router.py`): `route("What was your worst year?")` returns one of `trade`,
`performance`, `period`, `comparison`, `rules`, `video`, `other`, with probabilities. The API uses it
to choose which saved numbers or video moments to ground the NPC's answer in.
