"""Helpers for the strategy rules format in schemas/strategy_rules.json."""

import hashlib
import json
import re

from backend.config import DEFAULT_TEST_MARKET, TESTABLE_MARKETS, TIMEFRAMES

RULE_KEYS = ["entry", "exit", "stop_loss", "filters"]

_MARKET_ALIASES = {
    "BTC-USD": ["btc", "bitcoin", "xbt"],
    "ETH-USD": ["eth", "ethereum", "ether"],
    "SOL-USD": ["sol", "solana"],
}


def normalize_text(text: str) -> str:
    text = re.sub(r"[^a-z0-9.%<>=+\- ]", " ", str(text).lower())
    text = re.sub(r"\.(?!\d)", " ", text)  # keep decimal points like 1.5 or .5, drop other periods
    return re.sub(r"\s+", " ", text).strip()


def strategy_id(record: dict) -> str:
    """sha1 of the normalized rules. Same rules in any order or casing give the same id.

    The name, source videos, timestamps, claims and the market are left out, so the same rules taught in
    two videos share an id. Different wording still gives different ids; the Matcher handles that.
    """
    payload = {"timeframe": record.get("timeframe", "")}
    for key in RULE_KEYS:
        payload[key] = sorted(normalize_text(r["rule"]) for r in record.get(key, []))
    payload["vague_terms"] = sorted(
        [normalize_text(v["term"]), sorted(normalize_text(m) for m in v.get("meanings", []))]
        for v in record.get("vague_terms", [])
    )
    if record.get("testable") is False:
        # Untestable videos often have no rules at all, so their rules hash alike. Tie the id to the
        # video so two vague videos never collapse into one NPC.
        payload["videos"] = sorted(str(v.get("url", "")) for v in record.get("source_videos", []))
    return hashlib.sha1(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def tested_on(stated_market: str) -> str:
    """Pick the crypto market to test on: the stated one if we have its prices, else BTC."""
    words = set()
    for word in re.split(r"[^a-z]+", str(stated_market).lower()):
        words.add(word)
        words.add(re.sub(r"(usdt|usdc|usd|perp)$", "", word))  # BTCUSDT -> btc
    for market, aliases in _MARKET_ALIASES.items():
        if words & set(aliases):
            return market
    return DEFAULT_TEST_MARKET


def coerce_timeframe(stated: str) -> str:
    """Map any stated candle timeframe onto the price data we have: 5m, 1h or 1d.

    Under an hour tests on 5m candles, 1 to 4 hours on 1h, and anything longer, or unknown, on 1d.
    The Backtester can resample up from these, e.g. 5m into 15m or 1h into 4h.
    """
    text = str(stated).lower().strip()
    text = re.sub(r"^([mhdw])(\d+)$", r"\2\1", text)  # forex style H1, M15, D1
    if text in TIMEFRAMES:
        return text
    match = re.match(r"(\d+)\s*(m|min|minute|minutes|h|hr|hour|hours|d|day|daily|w|week|weekly)?", text)
    if "hour" in text and not match:
        return "1h"
    if not match:
        return "1d"
    n, unit = int(match.group(1)), (match.group(2) or "m")
    if unit.startswith("m"):
        return "5m"
    if unit.startswith("h"):
        return "1h" if n <= 4 else "1d"
    return "1d"


def validate(record: dict) -> list[str]:
    """Return a list of problems with a strategy rules record. Empty means valid."""
    errors = []
    expected = ["strategy_id", "strategy_name", "source_videos", "market", "timeframe", *RULE_KEYS,
                "vague_terms", "claims", "testable", "untestable_reason"]
    for key in expected:
        if key not in record:
            errors.append(f"missing {key}")
    if errors:
        return errors
    if not isinstance(record["strategy_name"], str):
        errors.append("strategy_name must be a string (empty if unknown)")
    if not re.fullmatch(r"[0-9a-f]{40}", record["strategy_id"]):
        errors.append("strategy_id is not a sha1 hex string")
    if not record["source_videos"] or not all("url" in v for v in record["source_videos"]):
        errors.append("source_videos needs at least one entry with a url")
    if set(record["market"]) != {"stated", "tested_on"}:
        errors.append("market must have exactly stated and tested_on")
    elif record["market"]["tested_on"] not in TESTABLE_MARKETS:
        errors.append(f"market.tested_on must be one of {TESTABLE_MARKETS}")
    if record["timeframe"] not in TIMEFRAMES:
        errors.append(f"timeframe must be one of {TIMEFRAMES}")
    for key in [*RULE_KEYS, "claims"]:
        text_key = "text" if key == "claims" else "rule"
        for item in record[key]:
            if not isinstance(item.get(text_key), str) or not item[text_key].strip():
                errors.append(f"{key} item without {text_key}")
            if not isinstance(item.get("timestamp_s"), (int, float)):
                errors.append(f"{key} item without numeric timestamp_s")
    for vague in record["vague_terms"]:
        if not vague.get("term") or not 2 <= len(vague.get("meanings", [])) <= 3:
            errors.append(f"vague term {vague.get('term')!r} needs two or three meanings")
    if not isinstance(record["testable"], bool):
        errors.append("testable must be true or false")
    elif record["testable"] and record["untestable_reason"] is not None:
        errors.append("untestable_reason must be null when testable")
    elif not record["testable"] and not record["untestable_reason"]:
        errors.append("untestable_reason is required when not testable")
    return errors
