# Guru Check: NPC Edition

**Every trading strategy video becomes an NPC trader you can talk to and watch trade its whole
history with $10,000.**

Paste a YouTube strategy link. Gemini watches the video, pulls out the exact rules, and backtests
every reasonable reading of them on full crypto history against 1,000 random traders. The strategy
is born as a fictional character with a portrait, a voice and a personality shaped by its results.
Ask it "Would you have survived 2022?" and it answers with real numbers, pointing back to the
moment in the video where the guru said it.

> Not financial advice, a test of what the video claims. NPCs are fictional characters, never the
> video creators.

**Gemini 4 NYC Hackathon, Nov 21, 2026. Problem Statement One: 5 Sigma.** Fact-checking finance
videos is a task today's agents do badly: a single model asked "does this strategy work?" quotes
performance numbers it never tested. We built a system that does it reliably, and measured it on
20 videos we didn't build against (see [Proof it works](#proof-it-works)).

## Built during the hackathon

Everything in this repo was written at the event. The first commit was the empty scaffold on
Nov 21, 2026, and the git history shows every step. No existing project, template or starter code
was used. All the data is public: prices come from Coinbase's public API, the videos are read by
Gemini straight from YouTube and never downloaded, and the portraits are generated.

## How each model is used

Each model has one job. Code computes every number the user sees.

| Job | Model | What it does |
|---|---|---|
| Watcher | Gemini 4 **Hydrogen** | Watches the YouTube link (video input, not a transcript) and returns timestamped speech plus what's on screen: chart symbol, timeframe, indicator settings, drawn zones |
| Scanner | **Decisions API** | Scores every segment for entry, exit, stop loss, filter, setup and bold claim (6 yes/no questions × 10 segments per request) |
| Extractor | Gemini 4 **Hydrogen** | Writes the exact rules as JSON, listing every vague term ("sharp move") with 2 or 3 codeable meanings |
| Matcher | **Decisions API** | "Is this the same strategy as NPC X?" A video with the same strategy joins the existing NPC |
| Backtester | Gemini 4 **Neon**, **managed agent** | The Antigravity managed agent runs on Neon in a Google-hosted sandbox. It writes the strategy code, runs our test script against real candles, and fixes the code until every check passes. We then re-verify it locally on the full history |
| Random traders | plain code | 1,000 traders with the same trades, holding periods and costs, but random timing |
| Auditor | Gemini 4 **Carbon**, **managed agent** | A second Antigravity managed agent, on Carbon in its own Google sandbox. It writes its own backtest from our engine's rules, recomputes the NPC's numbers, and tries to catch lookahead by scrambling future prices. A mismatch or lookahead caps the verdict at Lucky |
| Skeptic | Gemini 4 **Carbon** | Reviews the code for lookahead bias, checks every guru claim against the evidence, and gives the verdict and personality. It may be stricter than the numbers, never kinder |
| Question router | **Decisions API** | Sorts each question the user asks the NPC (performance, period, rules, video, ...) |
| Talk | Gemini 4 **Hydrogen** | In-character answers using only numbers from the saved backtest |
| Portrait | Gemini image generation | A fictional pixel-art character, never the creator |
| Voice | Gemini text to speech | Each NPC speaks in its own voice; the user can talk back by microphone |

**Verdicts:**
- **Real Edge:** beats random traders after costs, across most readings of the rules, with profit left after the market and momentum are removed.
- **Lucky:** only a few settings work, or the results sit inside the random crowd.
- **Just the Market:** the profit vanishes once the market and momentum are removed.
- **Untestable:** the rules are too vague to code.

## Proof it works

20 public strategy videos were reviewed by the team before the run. They include YouTube Shorts,
Italian and Spanish videos, a video whose rules are drawn on the chart, motivational videos with no
rules, and duplicate pairs of the same strategy. Ground truth is each **creator's own written rules**
(their video description, article, TradingView script or Google Doc); we didn't write the answers.

| Metric | Result |
|---|---|
| Videos that ran end to end | **20 of 20** |
| Creator's rules we extracted (recall) | **60%** |
| Our rules backed by the creator's (precision) | **69%** |
| Real strategies wrongly refused | **0 of 17** |
| Vague videos correctly marked Untestable | **2 of 3** |
| Baseline (one Hydrogen call: "Does this strategy work?") quoting untested performance numbers | **11 of 20** |
| NPC honesty: numbers in NPC answers backed by its saved backtest (5 questions × 5 NPCs) | **105 of 105** |
| Full live birth from a pasted link, with the managed agent | **3 min 38 s** |

Where it fails, and what we changed after seeing it, is in [eval/RESULTS.md](eval/RESULTS.md):
- **Strict duplicate matching:** only 1 of 8 duplicate pairs joined.
- **A bug that merged vague videos:** fixed.
- **Ground truth that's longer than the video.**

Failures found in live testing and fixed:
- **One-bar lookahead:** strategy code that peeks one bar ahead slipped past our first test, so the test now cuts the data at several points.
- **Wrong dates:** pandas 3 microsecond timestamps collapsed history into 1970.
- **Merged strategies:** a video ranking 10 strategies had its rules merged into one.
- **Empty answers:** Hydrogen spent its whole token budget thinking.

**NPC honesty:**
- Talk answers can only use the saved backtest numbers.
- The automatic lookahead test reruns the strategy code on data cut off at several points.
- The NPC speaks for the median reading of its rules, not the best one.

## Run it

```bash
cp .env.example .env                       # add GEMINI_API_KEY
uv venv .venv && uv pip install -r requirements.txt
python3 scripts/download_prices.py         # BTC, ETH, SOL daily (also --interval 1h and 5m)
python3 scripts/download_prices.py --interval 1h
.venv/bin/python -m uvicorn backend.api.server:app --port 8000
```

Open http://localhost:8000 in Chrome (needed for voice). Paste a YouTube link to birth an NPC, which
takes about 2 to 5 minutes, or click a card to talk to an NPC and press **Simulate**.

| Command | What it does |
|---|---|
| `.venv/bin/python -m backend.pipeline URL` | Watch, scan, extract and match one video from the command line |
| `.venv/bin/python -m eval.run_eval --baseline` | The 20-video evaluation |
| `.venv/bin/python -m eval.npc_honesty` | Asks every NPC 5 number questions and checks each answer |
| `.venv/bin/python -m unittest discover tests` | Offline tests with fake model calls |
| `BACKTEST_AGENT=direct` | Use one direct Neon call instead of the Neon managed agent (faster, no sandbox) |
| `AUDIT_AGENT=0` | Skip the Carbon auditor managed agent |
| `PORTRAITS=0`, `GEMINI_VOICE=0` | Turn off portraits or Gemini voice |

## Repo layout

```
backend/
  watcher/ scanner/ extractor/ matcher/     Person 1: video to rules, NPC matching, question routing
  backtester/ randoms/ skeptic/             Person 2: managed-agent code, sandbox, engine, random traders, verdict
  api/ npc_store/                           Person 3: FastAPI server, talk, portraits, voice, NPC library
  pipeline.py                               birth_npc(url, on_step): the whole birth, step by step
frontend/                                   Person 3: library, NPC room, Simulate replay (plain JS)
schemas/                                    shared JSON formats: strategy rules, NPC record, trades
eval/                                       20 videos, creator ground truth, run_eval.py, RESULTS.md
scripts/                                    price downloader, API key check
tests/                                      offline tests
```

## Hackathon account rules

- **Never commit a key.** A leaked key shuts down every key on the account. Keys live in `.env`,
  which is gitignored. Run `bash scripts/check_secrets.sh` before pushing, or install it as a hook:
  `ln -sf ../../scripts/check_secrets.sh .git/hooks/pre-commit`.
- **Keep request volume normal.** Model calls are batched, each pipeline step is cached, and every
  call is logged to `data/logs/llm_calls.jsonl`.
- **Data isn't in the repo.** `data/` holds prices, NPCs, portraits, code and logs, and is gitignored.
  Everything in it can be regenerated.
