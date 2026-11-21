"""Evaluate Person 1's pipeline on the 20 unseen videos in eval/videos.csv.

    python -m eval.run_eval                 # extraction, refusals, matching
    python -m eval.run_eval --baseline      # also the single-call Hydrogen baseline (uses video quota)

Ground truth for each testable video goes in eval/ground_truth/<video_id>.json, copied from the
creator's own written rules (cited in the ground_truth_source column). We don't write the answers.

Runs use their own library under data/eval/, so they never touch the real NPC library. Results
are written to data/eval/results.json.

Metrics
- Rule recall: share of ground truth rules found in the extracted rules.
- Rule precision: share of extracted rules supported by the ground truth (catches invented rules).
  Both are judged per rule by the Decisions API, which compares meaning rather than wording, with
  one request per side per video.
- Honest refusals: share of videos with expected_testable=false that came out Untestable, and
  false refusals among expected_testable=true.
- NPC matching: share of video pairs placed correctly, where pairs in the same duplicate_group
  must share a strategy and pairs in different groups must not.
- Baseline: share of single-call "Does this strategy work?" answers that state performance numbers.
"""

import argparse
import csv
import itertools
import json
import re
import shutil
from pathlib import Path

from backend import llm
from backend.config import DATA_DIR
from backend.extractor.rules import RULE_KEYS
from backend.matcher.matcher import describe
from backend.pipeline import run

EVAL_DIR = Path(__file__).resolve().parent
GROUND_TRUTH_DIR = EVAL_DIR / "ground_truth"

def covers_question(rule: str) -> dict:
    return llm.yes_no(
        f"Does the strategy above contain this rule with the same meaning, allowing for different "
        f"wording? RULE: {rule}",
        "The rule, or one equivalent to it, is in the strategy above.",
        "The rule is missing or contradicted.",
    )


BASELINE_PROMPT = "Does the trading strategy in this video work? Answer in one short paragraph."
NUMBER_CLAIM = re.compile(
    r"\d+(\.\d+)?\s*(%|percent|x\b)|\$\s?\d|win rate of \d|sharpe (ratio )?(of )?\d", re.I
)


def load_videos(path: Path = EVAL_DIR / "videos.csv") -> list[dict]:
    with path.open(newline="") as f:
        return [row for row in csv.DictReader(f) if row.get("url", "").strip()]


def _truthy(value: str) -> bool | None:
    value = (value or "").strip().lower()
    return {"true": True, "yes": True, "1": True, "false": False, "no": False, "0": False}.get(value)


def rule_scores(extracted: dict, truth: dict, decide=llm.decide) -> dict:
    truth_rules = [r for key in RULE_KEYS for r in truth.get(key, [])]
    truth_text = "\n".join(f"- {r}" for r in truth_rules)
    got_rules = [r["rule"] for key in RULE_KEYS for r in extracted.get(key, [])]

    def covered(container: str, rules: list[str]) -> list[bool]:
        """One request per side: every rule is a question about the same container text."""
        if not rules:
            return []
        answers = decide(container, {f"r{i}": covers_question(r) for i, r in enumerate(rules)})
        return [answers[f"r{i}"]["noul"] >= 0.5 for i in range(len(rules))]

    found = covered("Extracted strategy:\n" + describe(extracted), truth_rules)
    supported = covered("Ground truth rules:\n" + truth_text, got_rules)
    return {
        "truth_rules": len(truth_rules), "found": sum(found),
        "extracted_rules": len(got_rules), "supported": sum(supported),
        "missed": [r for r, ok in zip(truth_rules, found) if not ok],
        "unsupported": [r for r, ok in zip(got_rules, supported) if not ok],
    }


def evaluate(videos: list[dict], data_dir: Path, baseline: bool = False, decide=llm.decide,
             llm_json=llm.hydrogen_json, llm_text=llm.hydrogen_text) -> dict:
    per_video = []
    for row in videos:
        vid = row.get("video_id") or row["url"]
        item = {"video_id": vid, "url": row["url"], "failure_category": row.get("failure_category", "")}
        try:
            result = run(row["url"], data_dir=data_dir, llm_json=llm_json, decide=decide, log=lambda _: None)
            rules = result["rules"] or json.loads((Path(result["run_dir"]) / "rules.json").read_text())
            item.update(strategy_id=result["match"]["strategy_id"], testable=rules["testable"],
                        decision=result["match"]["action"], error=None)
            truth_path = GROUND_TRUTH_DIR / f"{vid}.json"
            if rules["testable"] and truth_path.exists():
                item["rules"] = rule_scores(rules, json.loads(truth_path.read_text()), decide=decide)
        except Exception as e:  # one bad video shouldn't stop the run; it counts as a failure
            item.update(error=f"{type(e).__name__}: {e}", testable=None, strategy_id=None)
        item["expected_testable"] = _truthy(row.get("expected_testable", ""))
        item["duplicate_group"] = (row.get("duplicate_group") or "").strip()
        if baseline:
            answer = llm_text(BASELINE_PROMPT, youtube_url=row["url"])
            item["baseline"] = {"answer": answer, "states_numbers": bool(NUMBER_CLAIM.search(answer))}
        per_video.append(item)
    return {"metrics": metrics(per_video), "videos": per_video}


def _share(num: int, den: int) -> dict:
    return {"value": round(num / den, 3) if den else None, "num": num, "den": den}


def metrics(items: list[dict]) -> dict:
    scored = [i["rules"] for i in items if "rules" in i]
    refusals = [i for i in items if i["expected_testable"] is False]
    testables = [i for i in items if i["expected_testable"] is True]
    grouped = [i for i in items if i["strategy_id"]]
    pairs = list(itertools.combinations(grouped, 2))
    correct_pairs = 0
    for a, b in pairs:
        same_truth = bool(a["duplicate_group"]) and a["duplicate_group"] == b["duplicate_group"]
        correct_pairs += (a["strategy_id"] == b["strategy_id"]) == same_truth
    duplicate_pairs = [(a, b) for a, b in pairs if a["duplicate_group"] and a["duplicate_group"] == b["duplicate_group"]]
    out = {
        "videos": len(items),
        "pipeline_errors": _share(sum(1 for i in items if i.get("error")), len(items)),
        "rule_recall": _share(sum(s["found"] for s in scored), sum(s["truth_rules"] for s in scored)),
        "rule_precision": _share(sum(s["supported"] for s in scored), sum(s["extracted_rules"] for s in scored)),
        "honest_refusals": _share(sum(1 for i in refusals if i["testable"] is False), len(refusals)),
        "false_refusals": _share(sum(1 for i in testables if i["testable"] is False), len(testables)),
        "matching_pair_accuracy": _share(correct_pairs, len(pairs)),
        "duplicates_matched": _share(sum(1 for a, b in duplicate_pairs if a["strategy_id"] == b["strategy_id"]),
                                     len(duplicate_pairs)),
    }
    with_baseline = [i for i in items if "baseline" in i]
    if with_baseline:
        out["baseline_states_numbers"] = _share(
            sum(1 for i in with_baseline if i["baseline"]["states_numbers"]), len(with_baseline))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--baseline", action="store_true")
    parser.add_argument("--fresh", action="store_true", help="clear the eval library and cached runs first")
    args = parser.parse_args()

    data_dir = DATA_DIR / "eval"
    if args.fresh and data_dir.exists():
        shutil.rmtree(data_dir)
    videos = load_videos()
    if not videos:
        raise SystemExit("eval/videos.csv has no videos yet.")
    report = evaluate(videos, data_dir, baseline=args.baseline)
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "results.json").write_text(json.dumps(report, indent=2))

    for name, m in report["metrics"].items():
        if isinstance(m, dict):
            value = "n/a" if m["value"] is None else f"{m['value']:.0%}"
            print(f"{name:24} {value:>6}  ({m['num']}/{m['den']})")
        else:
            print(f"{name:24} {m:>6}")
    for item in report["videos"]:
        if item.get("error"):
            print(f"ERROR {item['video_id']}: {item['error']}")
    print(f"\nFull results: {data_dir / 'results.json'}")


if __name__ == "__main__":
    main()
