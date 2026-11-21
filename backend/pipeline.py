"""Person 1 pipeline: link -> Watcher -> Scanner -> Extractor -> Matcher.

Each stage's output is cached in data/runs/<video_id>/, so a rerun skips finished stages and
doesn't spend more of the daily YouTube quota. The final rules are what the Backtester reads.

    python -m backend.pipeline "https://www.youtube.com/watch?v=..."
    python -m backend.pipeline URL --force          # redo every stage
    python -m backend.pipeline URL --from scan      # redo scan and later stages
"""

import argparse
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


def run(url: str, data_dir: Path = DATA_DIR, redo_from: str | None = None,
        llm_json: Callable = llm.hydrogen_json, decide: Callable = llm.decide,
        log: Callable[[str], None] = print) -> dict:
    url = canonical_url(url)
    store = Store(data_dir)
    run_dir = Path(data_dir) / "runs" / video_id(url)
    redo = set(STAGES[STAGES.index(redo_from):]) if redo_from else set()
    timings: dict[str, float] = {}
    calls_before = llm.CALLS.copy()

    if not redo:
        existing = match_link(url, store)
        if existing:
            log(f"Already in the library: strategy {existing['strategy_id']}, NPC {existing['npc_id']}")
            return {"match": existing, "rules": None, "run_dir": str(run_dir), "timings": {}}

    def stage(name: str, fn: Callable[[], dict]) -> dict:
        path = run_dir / f"{name}.json"
        if path.exists() and name not in redo:
            log(f"{name}: cached")
            return json.loads(path.read_text())
        start = time.time()
        result = fn()
        timings[name] = round(time.time() - start, 1)
        run_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2))
        log(f"{name}: done in {timings[name]}s")
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
    result = run(args.url, redo_from="watch" if args.force else args.redo_from)
    print()
    print(summary(result))


if __name__ == "__main__":
    main()
