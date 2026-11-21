"""Extractor: flagged segments -> strategy rules (schemas/strategy_rules.json).

Hydrogen writes the rules from the Scanner's flagged segments (text only, so it doesn't use more
of the daily YouTube video quota). Code then fixes the market, timeframe, ids and testability, so
the Backtester always gets a record that passes rules.validate().
"""

from typing import Any, Callable

from backend import llm
from backend.extractor import rules as R
from backend.scanner.scanner import flagged_segments, segment_text

PROMPT = """You turn a trading video into exact, codeable strategy rules for a backtest.
Below are the parts of the video that mention rules or claims, with timestamps.
Video title: {title}

{segments}

Some videos review, compare or rank several different strategies. Never mix rules from
different strategies into one. Pick the ONE strategy the video teaches most completely (it has an
entry and an exit or stop loss), preferring the one the creator says they use or recommend, and
extract only that strategy's rules, filters, vague terms and claims.

Write the rules exactly as the video teaches them. Do not invent rules, numbers or indicators
that are not in the video. Every rule and claim cites timestamp_s, the start time in seconds of
the part it came from.

- strategy_name: a short plain name for the strategy, 2 to 6 words, describing how it trades
  (e.g. "Demand zone retest", "London open break of structure", "Golden cross"). Never include the
  creator's name, channel name, or a branded course name.
- market_stated: the market or symbol the creator trades, as said or as shown on the chart they
  demonstrate on (e.g. "AAPL", "BTC", "EURUSD", "AMD (example chart)", "any market"). Just the
  symbol, under 30 characters, no explanation. Use "" only if it is neither said nor shown.
- timeframe_stated: the candle timeframe the entries are taken on, as said or as shown on the chart
  (e.g. "15m", "4h", "1D", "daily"). Just the timeframe, no explanation. Use "" only if it is
  neither said nor shown.
- entry, exit, stop_loss, filters: lists of {{"rule": "...", "timestamp_s": N}}. One condition per
  rule, with exact settings where given (e.g. "RSI(14) crosses above 30").
- vague_terms: every word or phrase in the rules that a programmer could read more than one way
  ("sharp move", "strong trend", "near support"). Give each two or three reasonable, codeable
  meanings, e.g. {{"term": "sharp move", "meanings": ["candle > 1.5 ATR", "candle > 2 ATR", "candle > 2.5 ATR"]}}.
- claims: claims about how well THIS strategy performs, said or shown on screen,
  {{"text": "80 percent win rate", "timestamp_s": N}}. Leave out sponsor segments and ads, and
  results of other traders, products or services (e.g. a copy trading app's top trader).
- testable: false if the entry or exit can't be turned into code even with the vague term meanings,
  e.g. "buy when it feels strong", or if the video teaches no strategy, or if it only surveys
  strategies without fully teaching any one of them. Then give untestable_reason
  in one sentence. Otherwise true and untestable_reason ""."""


_RULES = {"type": "array", "items": {"type": "object", "properties": {
    "rule": {"type": "string"}, "timestamp_s": {"type": "number"}}, "required": ["rule", "timestamp_s"]}}
SCHEMA = {
    "type": "object",
    "properties": {
        "strategy_name": {"type": "string"},
        "market_stated": {"type": "string"},
        "timeframe_stated": {"type": "string"},
        "entry": _RULES, "exit": _RULES, "stop_loss": _RULES, "filters": _RULES,
        "vague_terms": {"type": "array", "items": {"type": "object", "properties": {
            "term": {"type": "string"}, "meanings": {"type": "array", "items": {"type": "string"}}},
            "required": ["term", "meanings"]}},
        "claims": {"type": "array", "items": {"type": "object", "properties": {
            "text": {"type": "string"}, "timestamp_s": {"type": "number"}}, "required": ["text", "timestamp_s"]}},
        "testable": {"type": "boolean"},
        "untestable_reason": {"type": "string", "description": "empty string when testable"},
    },
    "required": ["strategy_name", "market_stated", "timeframe_stated", "entry", "exit", "stop_loss", "filters",
                 "vague_terms", "claims", "testable", "untestable_reason"],
}


def _snap(ts: float, spans: list[tuple[float, float]]) -> float:
    """Keep a time inside a flagged segment; otherwise move it to the nearest flagged segment start."""
    if not spans or any(start <= ts <= end for start, end in spans):
        return ts
    return min((start for start, _ in spans), key=lambda start: abs(start - ts))


def _items(raw: Any, text_key: str, spans: list[tuple[float, float]]) -> list[dict]:
    items = []
    for item in raw or []:
        if isinstance(item, str):
            item = {text_key: item}
        text = str(item.get(text_key) or item.get("rule") or item.get("text") or "").strip()
        if not text:
            continue
        try:
            ts = float(item.get("timestamp_s"))
        except (TypeError, ValueError):
            ts = spans[0][0] if spans else 0.0
        ts = _snap(ts, spans)
        items.append({text_key: text, "timestamp_s": int(ts) if float(ts).is_integer() else ts})
    return items


def _vague_terms(raw: Any) -> list[dict]:
    terms = []
    for v in raw or []:
        meanings = [str(m).strip() for m in v.get("meanings", []) if str(m).strip()]
        if v.get("term") and len(meanings) >= 2:
            terms.append({"term": str(v["term"]).strip(), "meanings": meanings[:3]})
    return terms


def _short(value: Any, limit: int = 30) -> str:
    """Keep a label field short: drop any explanation the model appended after it."""
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    for sep in [" (", ",", ";", " - ", " — "]:
        head = text.split(sep)[0].strip()
        if head and len(head) <= limit:
            return head
    return text[:limit].rstrip()


def _consistent(raw: dict) -> bool:
    """False for a self-contradictory answer: marked testable but with no entry rule."""
    return not (raw.get("testable", True) and not raw.get("entry"))


def build_record(raw: dict, video: dict, spans: list[tuple[float, float]]) -> dict:
    """Turn Hydrogen's answer into a valid strategy rules record."""
    stated = _short(raw.get("market_stated"))
    record = {
        "strategy_id": "",
        "strategy_name": str(raw.get("strategy_name") or "").strip(),
        "source_videos": [{"url": video["url"], "title": video.get("title", ""),
                           "upload_date": video.get("upload_date", ""),
                           "duration_s": video.get("duration_s", 0)}],
        "market": {"stated": stated, "tested_on": R.tested_on(stated)},
        "timeframe": R.coerce_timeframe(_short(raw.get("timeframe_stated"), 12)),
        "entry": _items(raw.get("entry"), "rule", spans),
        "exit": _items(raw.get("exit"), "rule", spans),
        "stop_loss": _items(raw.get("stop_loss"), "rule", spans),
        "filters": _items(raw.get("filters"), "rule", spans),
        "vague_terms": _vague_terms(raw.get("vague_terms")),
        "claims": _items(raw.get("claims"), "text", spans),
        "testable": bool(raw.get("testable", True)),
        "untestable_reason": raw.get("untestable_reason") or None,
    }
    if record["testable"]:
        if not record["entry"]:
            record["testable"], record["untestable_reason"] = False, "The video gives no entry rule."
        elif not record["exit"] and not record["stop_loss"]:
            record["testable"], record["untestable_reason"] = False, "The video gives no exit or stop loss rule."
    if record["testable"]:
        record["untestable_reason"] = None
    elif not record["untestable_reason"]:
        record["untestable_reason"] = "The rules are too vague to code."
    record["strategy_id"] = R.strategy_id(record)
    return record


ATTEMPTS = 3


def extract(scan_output: dict, llm_json: Callable[..., Any] = llm.hydrogen_json) -> dict:
    video = scan_output["video"]
    flagged = flagged_segments(scan_output)
    if not flagged:
        raw = {"testable": False, "untestable_reason": "No trading rules were found in the video."}
        return build_record(raw, video, [])
    text = "\n\n".join(segment_text(s) for s in flagged)
    prompt = PROMPT.format(title=video.get("title") or "unknown", segments=text)
    # Gemini 4 runs at a fixed temperature, so an answer occasionally contradicts itself. Ask again
    # before accepting one that would wrongly make a teachable strategy Untestable.
    for _ in range(ATTEMPTS):
        raw = llm_json(prompt, schema=SCHEMA)
        if _consistent(raw):
            break
    record = build_record(raw, video, [(s["start_s"], s["end_s"]) for s in flagged])
    errors = R.validate(record)
    if errors:
        raise ValueError(f"Extractor built an invalid record: {errors}")
    return record
