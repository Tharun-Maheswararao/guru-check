# Demo script (3 minute live demo + 2 minutes Q&A)

Judging (Round One): Live Demo 35%, Proof It Works 25%, Creativity 20%, Gemini 4 and Decisions API
use 20%. Judges want real, unrehearsed inputs, so **a judge picks the video**.

**Submission is due at 5:00 PM**, with a public repo, a one-minute demo video, and every team member
added on the submission page.

## Before going on stage

- Real NPCs are born and have portraits (`python -m backend.api.portrait`). No `data/npcs/demo-*`.
- Use Chrome with sound on and the microphone allowed. `M` mutes the sound effects.
- Have a few public strategy videos ready to offer if a judge doesn't have one.
- A brand-new birth takes 2 to 5 minutes; a live test from a pasted link took 3 min 38 s. Hydrogen
  watches (about 40 to 55s), the Neon managed agent codes and tests in its sandbox (1 to 3 min), and
  Carbon judges (about 30 to 60s). **Start it in the first 20 seconds.** If the network or quota is struggling, start the server with `BACKTEST_AGENT=direct`,
  which takes about a minute less and skips the sandbox.
- Keep one fully born NPC as a labelled backup in case the live birth runs over.

## Script

1. **Start the live birth (20s).** "Trading YouTube makes big claims. Pick any strategy video." Paste
   the judge's link and press START. "Gemini 4 Hydrogen is watching it right now, the actual video, not
   a transcript." Leave it running.
2. **NPC Room (55s).** Open an already-born trader. Read its opening line. Ask by voice: "Would you have
   survived 2022?" then "Is your strategy real?". Point at the video citation and click a timeline pin.
   "Every number it says comes from its saved backtest. It can't make one up."
3. **Simulate (40s).** Press SIMULATE at x4. Gold is the strategy, cyan is just holding, the gray cloud
   is 1,000 random traders. At the Pain Moment, ask the room: keep going or quit? Then show the verdict.
4. **Back to the birth (40s).** Walk through the steps on screen:
   - The Decisions API scored every moment of the video.
   - Hydrogen wrote the rules, and they popped onto the video timeline.
   - The Neon managed agent wrote and tested the code in its Google sandbox until our lookahead checks passed.
   - 1,000 random traders raced it.
   - Carbon judged the guru's claims.

   Open the newborn NPC and ask it one question. (If it's still running, finish on the backup.)
5. **Proof (25s).** "We tested on 20 videos we didn't build against, checked against the creators' own
   written rules: 0 crashes, 60% of their rules found, 69% of ours backed by theirs, no real strategy
   wrongly refused. A single model call quoted performance numbers for 11 of 20 videos without testing
   anything. We asked our NPCs 25 number questions: all 105 numbers they said match their saved
   backtests. Where it still fails, like strict duplicate matching, is in our results file."

## Likely questions

- **Why should we believe the numbers?**
  - Code computes them, not a model.
  - Costs are 0.15% per side.
  - The lookahead test reruns the code on data cut off at several points.
  - The NPC speaks for the median reading, not the best.
  - Carbon can't give a kinder verdict than the evidence.
- **Why crypto?** It's free, full-history public data. When a video trades stocks, forex or gold,
  the NPC says it was tested on Bitcoin instead.
- **What does the managed agent add?** Neon runs code in its own sandbox and fixes it until our
  checks pass, instead of guessing in one shot. We still re-verify locally on the full history.
- **What was built today?** All of it. See the README and the git history.

Backup: if the network fails, start the server with `MOCK_BIRTH=1` and use already-born NPCs.
