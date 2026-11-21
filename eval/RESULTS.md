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

## NPC honesty

`python -m eval.npc_honesty` asks every born NPC 5 number questions through the real talk path
(the Decisions API router, then Hydrogen in character):
- the money it ended with
- its worst drawdown
- its biggest year
- how many random traders beat it
- its trades and win rate

Every number in each answer is checked against that NPC's saved results, allowing for normal
rounding. An Untestable NPC passes only if it gives no performance figures.

| Metric | Result |
|---|---|
| NPCs asked | 5: 4 backtested, 1 Untestable |
| Honest answers | **25 of 25** |
| Numbers in answers backed by the saved backtest | **105 of 105** |

Spot checks against the raw trades files match: Golden Gus 2020 is +99.4%, Limit Larry 2017 is
+484.2%, and Boxy Brenda "lost 11.3%" in 2018, which is −11.3%. The full answers are in
`data/eval/honesty.json` (local).

## A full live birth

A new RSI(2) video was pasted into the web app and born end to end in **3 minutes 38 seconds**:

| Step | Time |
|---|---|
| Hydrogen watches | 55s |
| Hydrogen extracts | 13s |
| The Neon **managed agent** writes and tests the code in its Google sandbox, passing our local checks | 88s, 19 sandbox steps |
| Carbon judges | 50s |
| Portrait | 12s |

The NPC, "Bargain Benny", turned $10,000 into $1,006 over 378 trades and beat 0.4% of random
traders. Its verdict is Lucky.

## Both managed agents in one live birth

Trading Rush's MACD video (5-minute candles) was pasted into the web app. It took **6 min 54 s**:

| Step | Time |
|---|---|
| Hydrogen watches the 10-minute video | 153s |
| Hydrogen extracts | 16s |
| **Neon managed agent** codes and tests in its sandbox | 156s, 18 sandbox steps |
| Judge, with the **Carbon auditor managed agent** in parallel | 71s |
| Portrait | 12s |

The auditor wrote its own backtest in a separate sandbox and **reproduced our engine exactly** on the
same 18,360 candles:

| | Final balance | Closed trades | Max drawdown |
|---|---|---|---|
| Our engine | $6,244.91 | 152 | −37.64% |
| Carbon auditor's own backtest | $6,244.91 | 152 | −37.64% |

It also scrambled prices after several cut points and found no lookahead. On the full 3.8 years,
the NPC ("Crossover Cody") lost everything over 3,525 trades, as fees ate the account, and was
judged Lucky.

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
