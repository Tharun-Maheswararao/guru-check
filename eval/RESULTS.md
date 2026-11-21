# Evaluation results

Run on Nov 21, 2026 with `python -m eval.run_eval --baseline --fresh` on the 20 videos in
`videos.csv`, which the team reviewed before the run. The ground truth is the creators' own written
rules (in `ground_truth/`, one file per video with the source link). Full output:
`data/eval/results.json`, which is local and not committed.

## Headline numbers

| Metric | Result | What it means |
|---|---|---|
| Pipeline errors | **0 of 20** | Every video ran end to end, including 2 YouTube Shorts and Italian and Spanish videos |
| Rule recall | **60%** (54 of 90) | Share of the creator's written rules we extracted |
| Rule precision | **69%** (72 of 104) | Share of our extracted rules that the creator's rules support |
| Honest refusals | **2 of 3** | Vague videos correctly marked Untestable (see the AwakeFX note below) |
| False refusals | **0 of 17** | Real strategies wrongly marked Untestable |
| Matching, all pairs | **96%** (182 of 190) | Pairs of videos correctly kept apart or joined |
| Duplicates joined | **1 of 8** | Pairs teaching the "same" strategy that joined one NPC |
| Baseline states performance numbers | **55%** (11 of 20) | One Hydrogen call asked "Does this strategy work?" answered with return or win-rate figures it never tested |

The whole run took 5 minutes 45 seconds, with 5 videos processed in parallel.

## How the baseline compares

A single model call quotes performance numbers for 11 of 20 videos, though nothing was tested. A Guru
Check NPC states only numbers from its own saved backtest, with costs, 1,000 random traders and a
market check, and it says when it was tested on a different market than the video's.

## Failures and what we changed

- **Duplicates are matched strictly (1 of 8).** The Matcher asks whether a backtest of both
  strategies "would place essentially the same trades".
  - Two golden cross videos with identical rules joined, with a score of 0.97.
  - The RSI(2) videos use different thresholds (5/95 against 30/70) and the turtle videos different channels. The Matcher scored those pairs 0.01 to 0.27, so each became its own NPC.
  - This is a design choice: a looser "same core idea" question would join more pairs, but the NPC would then speak for settings it never tested. We haven't changed the Matcher after seeing these results.
- **Two vague videos were joined into one NPC.** With no rules, both hashed to the same
  `strategy_id`. *Fixed after this run:* untestable strategies now get an id tied to their video and
  never join. This pair is one of the 8 wrong pairs in the matching numbers above.
- **AwakeFX Silver Bullet (rules drawn on the chart).** It was labelled "expected Untestable", but we
  extracted a testable fair value gap strategy from what's drawn on screen. The label may be too
  strict; we count it as a miss anyway.
- **Low recall on three videos.**
  - Rayner's golden cross (1 of 8): his article adds discretionary pullback rules the video doesn't spell out.
  - Rayner's Bollinger system (1 of 8): the article may be an updated version of the video.
  - TradeSmart's Bollinger Bands + RSI (2 of 7): the ground truth is a Pine script with more detail than the video.

  The ground truth notes in `videos.csv` flag all three.
- **Non-English videos** (Italian Donchian, Spanish RSI 2) ran and came out testable, as expected.
  They have no written rules, so they aren't in the recall numbers.
