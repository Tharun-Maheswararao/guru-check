# Evaluation

20 strategy videos picked before hacking and never used while building.

## videos.csv columns

| column | meaning |
|---|---|
| `video_id` | short name, also the ground truth file name |
| `url` | YouTube link |
| `title` | video title |
| `documented_strategy` | e.g. golden cross, RSI reversion, or `vague` |
| `ground_truth_source` | link to the creator's own written rules |
| `expected_testable` | `true`, or `false` for vague videos that should come out Untestable |
| `duplicate_group` | same value for videos teaching the same strategy, blank otherwise |
| `failure_category` | e.g. fast short with music, non English, rules only on chart drawings |
| `notes` | anything else |

For each testable video, copy the creator's written rules into `ground_truth/<video_id>.json`,
shaped like `ground_truth/EXAMPLE.json`. We don't write the answers ourselves.

## Run

```bash
.venv/bin/python -m eval.run_eval              # rule recall and precision, refusals, matching
.venv/bin/python -m eval.run_eval --baseline   # adds the single Hydrogen call baseline
.venv/bin/python -m eval.run_eval --fresh      # clears the eval library and cached runs first
```

Each video goes through the YouTube quota once, then its run is cached in `data/eval/runs/`.
`--baseline` reads each video once more. Results go to `data/eval/results.json`.

Runnable strategies and NPC honesty need the Backtester and Voice, so they aren't measured here yet.
