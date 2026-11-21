"""Scanner: scores each Watcher segment with the Decisions API.

Segments are sent in chunks of CHUNK_SIZE: one Decisions request holds the chunk's text and asks
every flag question about every segment in it (6 labels x 10 segments = 60 questions). That keeps a
20 minute video to about 6 requests, and neighbouring segments give each other context.

Output keeps every segment, adds `flags` (yes probability per label) and `labels` (flags at or
above the threshold), and a `timeline` of marked moments.
"""

from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from backend import llm
from backend.config import SCAN_THRESHOLD

LABELS = {
    "entry": llm.yes_no(
        "Does this part of a trading video state or show a rule for when to ENTER (open) a trade?",
        "States a concrete entry condition or trigger, e.g. 'buy when the 50 EMA crosses above the 200 EMA'.",
        "No entry condition; only context, commentary, or results.",
    ),
    "exit": llm.yes_no(
        "Does this part state or show a rule for when to EXIT a trade or take profit?",
        "States a take-profit target or exit condition, e.g. 'sell when RSI goes above 70'.",
        "No exit or take-profit condition.",
    ),
    "stop_loss": llm.yes_no(
        "Does this part state or show where to place a STOP LOSS or when to cut a losing trade?",
        "States a stop-loss level or rule, e.g. 'stop just below the swing low'.",
        "No stop-loss rule.",
    ),
    "filter": llm.yes_no(
        "Does this part state a condition that must hold before taking a trade, such as a trend filter, "
        "a time-of-day rule, a minimum risk to reward, or position sizing?",
        "States a filter, precondition, or sizing rule.",
        "No filter, precondition, or sizing rule.",
    ),
    "setup": llm.yes_no(
        "Does this part say which market, chart timeframe, or indicator settings the strategy uses?",
        "Names the market or symbol, the candle timeframe, or exact indicator settings.",
        "Does not name the market, timeframe, or indicator settings.",
    ),
    "claim": llm.yes_no(
        "Does this part make a bold claim about how well the strategy performs?",
        "Claims a win rate, return, profit, or reliability, e.g. '80 percent win rate' or 'never loses'.",
        "No performance claim.",
    ),
}

# Labels that make a segment worth sending to the Extractor.
RULE_LABELS = {"entry", "exit", "stop_loss", "filter", "setup"}


def fmt_time(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def segment_text(seg: dict) -> str:
    lines = [f"[{fmt_time(seg['start_s'])} - {fmt_time(seg['end_s'])}]"]
    if seg.get("speech"):
        lines.append(f"Speech: {seg['speech']}")
    if seg.get("on_screen"):
        lines.append(f"On screen: {seg['on_screen']}")
    return "\n".join(lines)


CHUNK_SIZE = 10


def chunk_text(chunk: list[dict]) -> str:
    return "\n\n".join(f"Segment S{seg['segment_id']} {segment_text(seg)}" for seg in chunk)


def chunk_questions(chunk: list[dict]) -> dict:
    """Every label question, scoped to each segment in the chunk. Keys look like s12__entry."""
    questions = {}
    for seg in chunk:
        for label, q in LABELS.items():
            questions[f"s{seg['segment_id']}__{label}"] = {
                **q, "instructions": f"Consider only segment S{seg['segment_id']}. {q['instructions']}"}
    return questions


def score_chunk(chunk: list[dict], decide: Callable = llm.decide) -> dict[int, dict[str, float]]:
    answers = decide(chunk_text(chunk), chunk_questions(chunk))
    return {seg["segment_id"]: {label: round(float(answers[f"s{seg['segment_id']}__{label}"]["noul"]), 3)
                                for label in LABELS}
            for seg in chunk}


def scan(watch_output: dict, decide: Callable = llm.decide, threshold: float = SCAN_THRESHOLD,
         chunk_size: int = CHUNK_SIZE, workers: int = 4) -> dict:
    segments = watch_output["segments"]
    chunks = [segments[i:i + chunk_size] for i in range(0, len(segments), chunk_size)]
    scores: dict[int, dict[str, float]] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for result in pool.map(lambda c: score_chunk(c, decide), chunks):
            scores.update(result)

    scanned, timeline = [], []
    for seg in segments:
        flags = scores[seg["segment_id"]]
        labels = [label for label, p in flags.items() if p >= threshold]
        scanned.append({**seg, "flags": flags, "labels": labels})
        for label in labels:
            timeline.append({"segment_id": seg["segment_id"], "start_s": seg["start_s"],
                             "label": label, "probability": flags[label]})
    return {"video": watch_output["video"], "threshold": threshold, "segments": scanned,
            "timeline": timeline}


def flagged_segments(scan_output: dict) -> list[dict]:
    """Segments the Extractor should read: any rule or claim label."""
    return [s for s in scan_output["segments"] if s["labels"]]
