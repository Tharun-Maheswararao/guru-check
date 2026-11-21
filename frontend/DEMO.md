# Demo script (3 minutes)

Before going on stage: real NPCs born, `data/npcs/demo-*` deleted, Chrome, sound on, mic allowed.
Run `python -m backend.api.portrait` so every NPC has a portrait. Keep one fully born NPC as a
labelled backup in case a live birth runs slow.
Birth one fresh video in the background while talking, so the live birth is the finale.

1. **Hook (15s).** "Trading YouTube makes big claims. We turn every strategy video into a game character, then make it prove itself."
2. **Library (20s).** Show the roster and verdict badges. "Each trader is a strategy from a real video, tested on the full history of crypto prices."
3. **NPC Room (60s).** Open the Lucky trader. Read its opening line. Ask by voice: "How did you do in 2022?" then "Is your strategy real?". Point at the citation and click a timeline pin to jump to that second of the video. "Every number it says comes from the saved backtest, it can't make one up."
4. **Simulate (50s).** Hit SIMULATE at x4. Gold is the strategy, cyan is just holding, the gray cloud is 1,000 random traders. At the Pain Moment, ask the room: keep going or quit? Show where each path ended and the verdict.
5. **Live birth (25s).** Paste the new link, show the steps: Hydrogen watches, Decisions API scans, Hydrogen writes the rules and they pop onto the video timeline, Neon backtests, Carbon judges, Gemini draws the portrait. Open the newborn NPC.
6. **Proof (10s).** "On 20 unseen videos, picked and checked against the creators' own written rules: 0 crashes, 60% of their rules found, 69% of ours backed by their rules, no real strategy wrongly refused. A plain single model call quoted performance numbers for 11 of 20 videos without testing anything. Our NPCs only quote their own backtests." (Details and failures: `eval/RESULTS.md`.)

Backup: if the network fails, run with `MOCK_BIRTH=1` and use already-born NPCs. Press `M` to mute sounds.
