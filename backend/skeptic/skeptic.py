"""Skeptic: Gemini 4 Carbon reviews the code and the claims, gives the verdict and the personality.

Code first works out the strongest verdict the numbers allow (evidence_verdict). Carbon reads the
strategy code, the lookahead check, every reading's results, the random traders and the market
check, and the guru's claims. It may be stricter than the evidence verdict, never kinder, so the
NPC can't be talked into an edge the numbers don't show.
"""

import json
import re
import time

from backend import llm
from backend.config import model_settings

CARBON = model_settings("CARBON", "gemini-4-carbon")
VERDICTS = ["Real Edge", "Lucky", "Just the Market", "Untestable"]
RANK = {"Untestable": 0, "Lucky": 1, "Just the Market": 2, "Real Edge": 3}
COLORS = {"Real Edge": "green", "Lucky": "gold", "Just the Market": "red", "Untestable": "violet"}


def evidence_verdict(testable: bool, primary: dict | None, readings: list[dict], factors: dict | None,
                     lookahead_free: bool | None) -> tuple[str, str]:
    """The best verdict the numbers support, with the reason in one sentence."""
    if not testable or primary is None:
        return "Untestable", "The rules can't be turned into code that trades."
    if primary["trades_total"] == 0:
        return "Untestable", "The rules never triggered a single trade on the full history."
    beats = primary["random_percentile"]
    good = [r for r in readings if r["random_percentile"] >= 75]
    share_good = len(good) / max(1, len(readings))
    alpha_ok = bool(factors) and factors["alpha_t"] >= 1.5 and factors["alpha_annual_pct"] >= 2
    if lookahead_free is False:
        return "Lucky", "The code may peek at future prices, so no result here can count as an edge."
    if beats >= 90 and share_good >= 2 / 3 and alpha_ok:
        return "Real Edge", (f"Beats {beats:.0f}% of random traders after costs, in {len(good)} of "
                             f"{len(readings)} readings, with profit left after market and momentum.")
    if beats >= 75 and share_good >= 0.5 and not alpha_ok:
        return "Just the Market", (f"Beats {beats:.0f}% of random traders, but the profit disappears once "
                                   f"the market and momentum are removed.")
    if beats >= 75:
        return "Lucky", f"Only {len(good)} of {len(readings)} readings of the rules beat most random traders."
    return "Lucky", f"Beats only {beats:.0f}% of random traders, inside the random crowd."


SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": VERDICTS},
        "verdict_reason": {"type": "string"},
        "code_review": {"type": "object", "properties": {
            "lookahead_risk": {"type": "string", "enum": ["low", "medium", "high"]},
            "matches_rules": {"type": "boolean"},
            "notes": {"type": "string"}}, "required": ["lookahead_risk", "matches_rules", "notes"]},
        "claim_checks": {"type": "array", "items": {"type": "object", "properties": {
            "claim": {"type": "string"}, "timestamp_s": {"type": "number"},
            "status": {"type": "string", "enum": ["supported", "contradicted", "not testable"]},
            "note": {"type": "string"}}, "required": ["claim", "timestamp_s", "status", "note"]}},
        "name": {"type": "string"},
        "archetype": {"type": "string"},
        "personality": {"type": "string"},
    },
    "required": ["verdict", "verdict_reason", "code_review", "claim_checks", "name", "archetype", "personality"],
}

PROMPT = """You are the Skeptic in Guru Check, a game that fact checks trading videos. A strategy from
a YouTube video was coded and backtested. Judge it honestly from the evidence below, then design the
fictional game character (NPC) that will represent it.

STRATEGY RULES:
{rules}

GURU'S CLAIMS (with video times in seconds):
{claims}

EVIDENCE (computed by code; every number is exact):
{evidence}

STRATEGY CODE (written by another model; the readings switch between the vague term meanings):
```python
{code}
```

Tasks:
1. Review the code. Does it implement the rules? Any lookahead bias (using future prices)? The
   automatic lookahead test result is in the evidence.
2. Check each claim against the evidence: supported, contradicted, or not testable here (e.g. a
   claim about a different market or period). Quote numbers only from the evidence.
3. Verdict, one of: "Real Edge" (beats random traders after costs across most readings and keeps
   profit after market and momentum), "Lucky" (only a few settings work, or results sit inside the
   random crowd), "Just the Market" (profit vanishes once market and momentum are removed),
   "Untestable" (rules too vague to code). The evidence verdict is the best the numbers allow:
   {evidence_verdict}. You may be stricter if the code doesn't match the rules, never kinder.
   verdict_reason: one or two plain sentences a player understands.
4. The NPC: an invented character, never the video creator or any real person, and not their name.
   name: a playful two word name (e.g. "Steady Steve", "Risky Rita"). archetype: "The <adjective>
   <trader type>" (e.g. "The Patient Trend Follower", "The Nervous Scalper"). personality: two
   sentences shaped by the results (an NPC that lost to random traders might be defensive but honest;
   one with a real edge calm and dry). No em dashes.

Return only JSON."""


def _fallback_name(rules: dict) -> str:
    words = re.findall(r"[A-Za-z]+", rules.get("strategy_name") or "Mystery Trader")
    return " ".join(w.capitalize() for w in words[:2]) or "Mystery Trader"


def judge(rules: dict, evidence: dict, code: str, verdict_cap: tuple[str, str]) -> dict:
    """Carbon's review, with the verdict never above verdict_cap. Falls back to code on failure."""
    claims = [{"claim": c["text"], "timestamp_s": c["timestamp_s"]} for c in rules.get("claims", [])]
    shown_rules = {k: rules.get(k) for k in ["strategy_name", "market", "timeframe", "entry", "exit",
                                              "stop_loss", "filters", "vague_terms", "testable", "untestable_reason"]}
    prompt = PROMPT.format(rules=json.dumps(shown_rules, indent=1), claims=json.dumps(claims, indent=1),
                           evidence=json.dumps(evidence, indent=1), code=(code or "(no code)")[:14000],
                           evidence_verdict=f"{verdict_cap[0]} ({verdict_cap[1]})")

    def call() -> dict:
        start = time.time()
        interaction = llm._client(CARBON).interactions.create(
            model=CARBON.model, store=False, input=[{"type": "text", "text": prompt}],
            generation_config={"thinking_level": "medium"},
            response_format={"type": "text", "mime_type": "application/json", "schema": SCHEMA})
        text = interaction.output_text or ""
        llm._record("carbon_judge", CARBON.model, prompt, text, time.time() - start)
        return llm.parse_json(text)

    try:
        out = llm._retry(call, attempts=3)
    except Exception as e:
        out = {"verdict": verdict_cap[0], "verdict_reason": verdict_cap[1],
               "code_review": {"lookahead_risk": "medium", "matches_rules": True,
                               "notes": f"Skeptic unavailable ({type(e).__name__}); verdict from the numbers only."},
               "claim_checks": [], "name": _fallback_name(rules), "archetype": "The Untested Trader",
               "personality": "Plain spoken and a little unsure of itself. Lets the numbers do the talking."}

    if out.get("verdict") not in RANK or RANK[out["verdict"]] > RANK[verdict_cap[0]]:
        out["verdict"], out["verdict_reason"] = verdict_cap  # never kinder than the evidence
    out["name"] = " ".join(str(out.get("name") or _fallback_name(rules)).split()[:3])
    out["color"] = COLORS[out["verdict"]]
    return out
