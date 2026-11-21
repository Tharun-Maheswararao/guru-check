"""Matcher: is this strategy one we already have?

1. Same link: a video already in the library opens its NPC right away, before any model call.
2. Same rules: an identical strategy_id joins that strategy.
3. Similar rules: the closest saved strategies by word overlap go to the Decisions API, which
   asks "is this the same strategy?". At or above MATCH_THRESHOLD the video joins that strategy.
4. Otherwise a new NPC is born.

Untestable strategies only use steps 1 and 2, since vague rules can't be compared meaningfully.
"""

import re
from typing import Callable

from backend import llm
from backend.config import MATCH_CANDIDATES, MATCH_THRESHOLD
from backend.extractor.rules import RULE_KEYS, normalize_text
from backend.npc_store.store import Store
from backend.watcher.watcher import video_id

def same_strategy_question(candidate: str) -> dict:
    return llm.yes_no(
        f"The New strategy and Candidate {candidate} were extracted from two different trading videos. "
        f"Is Candidate {candidate} the same trading strategy as the New strategy, meaning a backtest of "
        "either would place essentially the same trades? Ignore wording, the order of rules, and which "
        "market the creator traded.",
        "Same entry logic, same exit and stop logic, and same key settings, possibly worded differently.",
        "Different indicators, settings, entry or exit logic, so the trades would differ.",
    )


_STOP = {"the", "a", "an", "of", "to", "and", "or", "when", "at", "on", "in", "is", "be", "it",
         "for", "with", "above", "below", "than", "price"}


def describe(rules: dict) -> str:
    lines = [f"Timeframe: {rules['timeframe']}"]
    names = {"entry": "Entry", "exit": "Exit", "stop_loss": "Stop loss", "filters": "Filters"}
    for key in RULE_KEYS:
        if rules[key]:
            lines.append(f"{names[key]}: " + "; ".join(r["rule"] for r in rules[key]))
    for v in rules.get("vague_terms", []):
        lines.append(f"'{v['term']}' could mean: " + " or ".join(v["meanings"]))
    return "\n".join(lines)


def _tokens(rules: dict) -> set[str]:
    text = " ".join(normalize_text(r["rule"]) for key in RULE_KEYS for r in rules[key])
    return {t for t in re.split(r"[ ]+", text) if t and t not in _STOP}


def similarity(a: dict, b: dict) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    jaccard = len(ta & tb) / len(ta | tb)
    return round(jaccard + (0.1 if a["timeframe"] == b["timeframe"] else 0.0), 3)


def match_link(url: str, store: Store) -> dict | None:
    """Step 1. Returns an `open` decision if this video is already in the library."""
    npc = store.npc_for_video(url)
    if npc is not None:
        return {"action": "open", "reason": "same_link", "npc_id": npc["npc_id"],
                "strategy_id": npc.get("strategy_id")}
    strategy = store.strategy_for_video(url)
    if strategy is not None:
        # Extracted before but no NPC born yet (e.g. backtest still running).
        return {"action": "open", "reason": "same_link", "npc_id": None,
                "strategy_id": strategy["strategy_id"]}
    return None


def match(rules: dict, store: Store, decide: Callable = llm.decide,
          threshold: float = MATCH_THRESHOLD, max_candidates: int = MATCH_CANDIDATES) -> dict:
    """Steps 2 to 4 for a freshly extracted strategy."""
    sid = rules["strategy_id"]
    own = {video_id(s["url"]) for s in rules["source_videos"]}
    # Leave out strategies saved from this same video, e.g. when the match stage is rerun.
    saved = [s for s in store.strategies()
             if not own & {video_id(v["url"]) for v in s.get("source_videos", [])}]

    def joined(target_sid: str, reason: str, score: float | None, candidates: list) -> dict:
        npc = store.npc_for_strategy(target_sid)
        return {"action": "join", "reason": reason, "strategy_id": target_sid,
                "npc_id": npc["npc_id"] if npc else None, "score": score, "candidates": candidates}

    if any(s["strategy_id"] == sid for s in saved):
        return joined(sid, "same_rules", 1.0, [])

    candidates = []
    if rules["testable"]:
        ranked = sorted(
            (s for s in saved if s.get("testable")),
            key=lambda s: similarity(rules, s), reverse=True,
        )[:max_candidates]
        if ranked:
            # One request compares the new strategy with every candidate.
            text = f"New strategy:\n{describe(rules)}" + "".join(
                f"\n\nCandidate C{i}:\n{describe(other)}" for i, other in enumerate(ranked, 1))
            questions = {f"same_c{i}": same_strategy_question(f"C{i}") for i in range(1, len(ranked) + 1)}
            answers = decide(text, questions)
            for i, other in enumerate(ranked, 1):
                candidates.append({"strategy_id": other["strategy_id"], "similarity": similarity(rules, other),
                                   "same_probability": round(float(answers[f"same_c{i}"]["noul"]), 3)})
        best = max(candidates, key=lambda c: c["same_probability"], default=None)
        if best and best["same_probability"] >= threshold:
            return joined(best["strategy_id"], "same_strategy", best["same_probability"], candidates)

    return {"action": "new", "reason": "no_match", "strategy_id": sid, "npc_id": None,
            "score": None, "candidates": candidates}
