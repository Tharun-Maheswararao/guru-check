"""Person 1 pipeline: link -> Watcher -> Scanner -> Extractor -> Matcher, and NPC birth.

Each stage's output is cached in data/runs/<video_id>/, so a rerun skips finished stages and
doesn't spend more of the daily YouTube quota. The final rules are what the Backtester reads.

birth_npc(url, on_step) is what the API calls (backend/api/server.py). It runs the four Person 1
steps, then hands the rules to Person 2's backtest_and_judge (see BACKTEST_HANDOFF), saves the
NPC and its trades, and returns the record. on_step(step, detail) reports progress to the UI.

    python -m backend.pipeline "https://www.youtube.com/watch?v=..."
    python -m backend.pipeline URL --force          # redo every stage
    python -m backend.pipeline URL --from scan      # redo scan and later stages
"""

import argparse
import importlib
import json
import logging
import time
from pathlib import Path
from typing import Callable

from backend import llm
from backend.config import DATA_DIR
from backend.extractor.extractor import extract
from backend.matcher.matcher import match, match_link
from backend.npc_store.store import Store
from backend.scanner.scanner import fmt_time, scan
from backend.watcher.watcher import canonical_url, video_id, watch

STAGES = ["watch", "scan", "rules", "match"]
UI_STEP = {"watch": "watch", "scan": "scan", "rules": "extract", "match": "match"}
STARTING = {
    "watch": "Hydrogen is watching the video",
    "scan": "Decisions API is scanning for rules and claims",
    "rules": "Hydrogen is writing the exact rules",
    "match": "Checking the library for the same strategy",
}
# Person 2's entry point: backtest_and_judge(rules, on_step) -> (npc_record, trades).
BACKTEST_HANDOFF = "backend.backtester.birth"

OnStep = Callable[[str, str], None]


def _no_step(step: str, detail: str = "") -> None:
    pass


def finished(name: str, result: dict) -> str:
    """One line for the UI saying what a stage found."""
    if name == "watch":
        return f"Watched {fmt_time(result['video']['duration_s'])} of video in {len(result['segments'])} segments"
    if name == "scan":
        flagged = sum(1 for seg in result["segments"] if seg["labels"])
        return f"Found {flagged} rule and claim moments in {len(result['segments'])} segments"
    if name == "rules":
        if not result["testable"]:
            return f"Untestable: {result['untestable_reason']}"
        counts = ", ".join(f"{len(result[k])} {label}" for k, label in
                           [("entry", "entry"), ("exit", "exit"), ("stop_loss", "stop loss")])
        named = f"'{result['strategy_name']}': " if result.get("strategy_name") else ""
        return f"Rules for {named}{counts} rules"
    if result["action"] == "join":
        return "Same strategy as one already in the library"
    return "A new strategy. A new trader will be born"


class RebirthError(RuntimeError):
    """Raised when re-extracting a video that already has a born NPC."""


def run(url: str, data_dir: Path = DATA_DIR, redo_from: str | None = None,
        llm_json: Callable = llm.hydrogen_json, decide: Callable = llm.decide,
        log: Callable[[str], None] = print, on_step: OnStep = _no_step) -> dict:
    url = canonical_url(url)
    store = Store(data_dir)
    run_dir = Path(data_dir) / "runs" / video_id(url)
    redo = set(STAGES[STAGES.index(redo_from):]) if redo_from else set()
    timings: dict[str, float] = {}
    calls_before = llm.CALLS.copy()

    if redo & {"watch", "scan", "rules"}:
        born = store.npc_for_video(url)
        if born is not None:
            # New wording gives a new strategy_id, which would leave this NPC pointing at an orphaned
            # strategy and get a second NPC born for the same video.
            raise RebirthError(
                f"NPC {born['npc_id']} was already born from this video. Re-extracting would give it a "
                f"new strategy_id and a duplicate NPC. To redo it, delete "
                f"{store.npc_dir / (born['npc_id'] + '.json')} first, or use --from match."
            )

    if not redo:
        existing = match_link(url, store)
        if existing:
            log(f"Already in the library: strategy {existing['strategy_id']}, NPC {existing['npc_id']}")
            return {"match": existing, "rules": None, "run_dir": str(run_dir), "timings": {}}

    def stage(name: str, fn: Callable[[], dict]) -> dict:
        path = run_dir / f"{name}.json"
        if path.exists() and name not in redo:
            log(f"{name}: cached")
            result = json.loads(path.read_text())
            on_step(UI_STEP[name], finished(name, result))
            return result
        on_step(UI_STEP[name], STARTING[name])
        start = time.time()
        result = fn()
        timings[name] = round(time.time() - start, 1)
        run_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2))
        log(f"{name}: done in {timings[name]}s")
        on_step(UI_STEP[name], finished(name, result))
        return result

    watched = stage("watch", lambda: watch(url, llm_json=llm_json))
    scanned = stage("scan", lambda: scan(watched, decide=decide))
    rules = stage("rules", lambda: extract(scanned, llm_json=llm_json))
    decision = stage("match", lambda: match(rules, store, decide=decide))

    if decision["action"] == "new":
        store.save_strategy(rules)
    elif decision["action"] == "join":
        store.add_source_video(decision["strategy_id"], rules["source_videos"][0])
    store.detach_video(url, keep_strategy_id=decision["strategy_id"])
    return {"match": decision, "rules": rules, "scan": scanned, "run_dir": str(run_dir),
            "timings": timings, "model_calls": dict(llm.CALLS - calls_before)}


class BacktesterNotConnected(RuntimeError):
    """Person 2's backtest_and_judge isn't available yet."""


def npc_fields(rules: dict) -> dict:
    """The NPC record fields that come from the strategy rules (Person 1's part of the record).

    rules_timeline is what the NPC Room pins on the video timeline and what the NPC cites.
    """
    timeline = [{"kind": kind, "rule": r["rule"], "timestamp_s": r["timestamp_s"]}
                for kind in ["entry", "exit", "stop_loss", "filters"] for r in rules[kind]]
    timeline += [{"kind": "claim", "rule": c["text"], "timestamp_s": c["timestamp_s"]} for c in rules["claims"]]
    return {
        "strategy_id": rules["strategy_id"],
        "strategy_name": rules.get("strategy_name", ""),
        "source_videos": rules["source_videos"],
        "market": rules["market"],
        "rules_timeline": sorted(timeline, key=lambda x: x["timestamp_s"]),
        "untestable_reason": rules["untestable_reason"],
    }


def _load_backtest_and_judge() -> Callable:
    try:
        module = importlib.import_module(BACKTEST_HANDOFF)
        return module.backtest_and_judge
    except (ImportError, AttributeError) as e:
        raise BacktesterNotConnected(
            f"The backtester isn't connected yet: add backtest_and_judge(rules, on_step) -> "
            f"(npc_record, trades) in {BACKTEST_HANDOFF.replace('.', '/')}.py ({e})"
        ) from e


def birth_preview(rules: dict, run_dir: Path) -> dict:
    """What the birth screen shows while the backtest runs: the rules pinned on the video timeline."""
    fields = npc_fields(rules)
    video = dict(fields["source_videos"][0])
    if not video.get("duration_s") and (run_dir / "watch.json").exists():
        video["duration_s"] = json.loads((run_dir / "watch.json").read_text())["video"]["duration_s"]
    return {"video": video, "strategy_name": fields["strategy_name"], "market": fields["market"],
            "testable": rules["testable"], "untestable_reason": rules["untestable_reason"],
            "rules_timeline": fields["rules_timeline"]}


def birth_npc(url: str, on_step: OnStep | None = None, data_dir: Path = DATA_DIR,
              llm_json: Callable = llm.hydrogen_json, decide: Callable = llm.decide,
              backtest_and_judge: Callable | None = None,
              on_rules: Callable[[dict], None] | None = None,
              make_portrait: Callable[[dict], str] | None = None) -> dict:
    """Turn a YouTube link into a saved NPC record, reporting each step through on_step.

    - A video already in the library returns its NPC.
    - A video whose strategy matches an NPC already born joins that NPC and returns it.
    - Otherwise Person 2's backtest_and_judge(rules, on_step) backtests, races the random traders,
      judges, and returns (npc_record, trades). It should report the backtest, randoms and judge
      steps. This function fills in the rule fields (npc_fields), saves both files, and reports born.
    - on_rules(preview), if given, gets birth_preview() as soon as the rules exist, so the UI can
      show them on the video timeline while the backtest runs.
    - make_portrait(record) -> path, if given, draws the portrait. If it fails the NPC is still
      born and the UI shows its pixel sprite.
    """
    on_step = on_step or _no_step
    store = Store(data_dir)
    url = canonical_url(url)

    existing = store.npc_for_video(url)
    if existing is not None:
        on_step("born", f"{existing.get('name') or 'This trader'} is already in the library")
        return existing

    result = run(url, data_dir=data_dir, llm_json=llm_json, decide=decide, log=lambda _: None,
                 on_step=on_step)
    decision = result["match"]
    if result["rules"] is None:  # extracted earlier, but no NPC was born yet
        on_step("watch", "Already watched")
        on_step("scan", "Already scanned")
        on_step("extract", "Rules for this video were already extracted")
        on_step("match", "Picking up where the last birth stopped")

    npc = store.npc_for_strategy(decision["strategy_id"])
    if npc is not None:  # joined a strategy whose NPC is already born
        on_step("born", f"Joined {npc.get('name') or 'an existing trader'}, who already trades this strategy")
        return npc

    # Always birth from the saved strategy, which lists every video that joined it.
    rules = store.get_strategy(decision["strategy_id"]) or result["rules"]
    if on_rules is not None:
        on_rules(birth_preview(rules, Path(result["run_dir"])))
    finish = backtest_and_judge or _load_backtest_and_judge_reporting(on_step)
    record, trades = finish(rules, on_step)
    record = {**record, **npc_fields(rules)}
    if make_portrait is not None and not record.get("portrait_path"):
        on_step("born", "Drawing a portrait")
        try:
            record["portrait_path"] = make_portrait(record)
        except Exception:
            pass  # keep the pixel sprite
    store.save_npc(record, trades)
    on_step("born", f"{record.get('name') or 'A new trader'} is born")
    return record


def _load_backtest_and_judge_reporting(on_step: OnStep) -> Callable:
    try:
        return _load_backtest_and_judge()
    except BacktesterNotConnected:
        on_step("backtest", "Backtester isn't connected yet (Person 2)")
        raise


def summary(result: dict) -> str:
    decision, rules = result["match"], result["rules"]
    lines = [f"Decision: {decision['action']} ({decision['reason']}), strategy {decision['strategy_id']}"]
    if decision.get("npc_id"):
        lines.append(f"NPC: {decision['npc_id']}")
    if rules is None:
        return "\n".join(lines)
    lines.append(f"Testable: {rules['testable']}" +
                 ("" if rules["testable"] else f" ({rules['untestable_reason']})"))
    lines.append(f"Market: {rules['market']['stated'] or 'not stated'} -> tested on "
                 f"{rules['market']['tested_on']}, timeframe {rules['timeframe']}")
    for key in ["entry", "exit", "stop_loss", "filters"]:
        for r in rules[key]:
            lines.append(f"  {key:9} {fmt_time(r['timestamp_s']):>7}  {r['rule']}")
    for v in rules["vague_terms"]:
        lines.append(f"  vague     '{v['term']}': " + " | ".join(v["meanings"]))
    for c in rules["claims"]:
        lines.append(f"  claim     {fmt_time(c['timestamp_s']):>7}  {c['text']}")
    if "scan" in result:
        flagged = sum(1 for s in result["scan"]["segments"] if s["labels"])
        lines.append(f"Segments: {len(result['scan']['segments'])}, flagged {flagged}")
    if result["timings"]:
        lines.append("Timings: " + ", ".join(f"{k} {v}s" for k, v in result["timings"].items()))
    if result.get("model_calls"):
        lines.append("Model requests: " + ", ".join(f"{k} {v}" for k, v in result["model_calls"].items()))
    lines.append(f"Files: {result['run_dir']}")
    return "\n".join(lines)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("url")
    parser.add_argument("--force", action="store_true", help="redo every stage")
    parser.add_argument("--from", dest="redo_from", choices=STAGES, help="redo this stage and later ones")
    args = parser.parse_args()
    try:
        result = run(args.url, redo_from="watch" if args.force else args.redo_from)
    except RebirthError as e:
        raise SystemExit(str(e))
    print()
    print(summary(result))


if __name__ == "__main__":
    main()
