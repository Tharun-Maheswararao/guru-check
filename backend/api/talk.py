"""Talk to an NPC. Gemini Hydrogen answers in character, grounded ONLY in the saved record.

The NPC can't lie about numbers: every figure is passed in from the saved backtest and the
prompt forbids inventing any other. Without GEMINI_API_KEY, a plain template answers instead.
"""

import json
import re
import os
import urllib.request

MODEL = os.environ.get("GEMINI_TALK_MODEL", "gemini-4-hydrogen")
URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def _fmt_ts(s):
    s = int(s or 0)
    return f"{s // 60}:{s % 60:02d}"


def facts(record: dict, trades: dict | None) -> dict:
    r = record.get("results") or {}
    f = {
        "name": record.get("name"), "archetype": record.get("archetype"),
        "personality": record.get("personality"), "verdict": record.get("verdict"),
        "video_title": (record.get("source_videos") or [{}])[0].get("title"),
        "market_stated": (record.get("market") or {}).get("stated"),
        "market_tested_on": (record.get("market") or {}).get("tested_on"),
        "rules": [f"{x['kind']}: {x['rule']} (video {_fmt_ts(x['timestamp_s'])})"
                  for x in record.get("rules_timeline", [])],
        "untestable_reason": record.get("untestable_reason"),
        "start_cash": 10000,
        "final_balance": r.get("final_balance"), "max_drawdown_pct": r.get("max_drawdown"),
        "win_rate_pct": r.get("win_rate"), "n_trades": r.get("n_trades"),
        "beat_pct_of_random_traders": r.get("random_percentile"),
        "pct_random_traders_did_better": r.get("share_random_better"),
        "just_holding_final": r.get("hold_final"),
        "demo_data": bool(record.get("demo")),
        "verdict_reason": record.get("verdict_reason"),
        "claim_checks": record.get("claim_checks"),
        "results_by_reading_of_vague_rules": record.get("readings"),
        "tested": record.get("tested"),
        "market_and_momentum_check": record.get("factor_check"),
    }
    if trades:
        pm = trades.get("pain_moment") or {}
        f["worst_moment"] = {"date": pm.get("date"), "drawdown_pct": pm.get("drawdown_pct"),
                             "losing_streak": pm.get("losing_streak")}
        # yearly returns so "how did you do in 2022?" has a real answer
        yearly, first = {}, {}
        for d, v in zip(trades["dates"], trades["equity"]):
            y = d[:4]
            first.setdefault(y, v)
            yearly[y] = round(100 * (v / first[y] - 1), 1)
        f["return_by_year_pct"] = yearly
    return f


SYSTEM = """You are {name}, a fictional pixel-art NPC trader in the game Guru Check. You are the
strategy from a YouTube trading video, brought to life. Personality: {personality}

Hard rules:
- Use ONLY numbers that appear in FACTS. Never invent a number, date or trade. If FACTS lacks it, say you don't know.
- When you mention a rule, cite the video time, like "the video says this at 4:12".
- Be honest about your verdict ({verdict}), even if it hurts your ego.
- If market_stated differs from market_tested_on, say you were tested on {tested}.
- Never give financial advice. Never claim to be the real video creator.
- Speak in 1 to 3 short sentences, in character, first person.
{focus}
FACTS:
{facts}"""

# What to lean on for each kind of question. The kind comes from the Decisions API router
# (backend/scanner/router.py), which sorts the question in one fast request.
FOCUS = {
    "trade": "The user asks about a specific trade or moment. Use the trades in FACTS (date, side, price, rule, video time).",
    "performance": "The user asks about overall results. Use final_balance, max_drawdown_pct, win_rate_pct and n_trades.",
    "period": "The user asks about a period. Use return_by_year_pct and worst_moment.",
    "comparison": "The user asks how you compare. Use just_holding_final, beat_pct_of_random_traders and pct_random_traders_did_better.",
    "rules": "The user asks about your rules. Explain them from rules, citing each video time.",
    "video": "The user asks what the video said. Cite rules and the guru's claims with their video times, and compare the claims to your real results.",
    "other": "The user is off topic. Answer briefly in character, then steer back to your strategy and results.",
}


def route_question(question: str) -> dict | None:
    """Sort the question with the Decisions API. None if it isn't available, so talk still works."""
    try:
        from backend.scanner.router import route
        return route(question)
    except Exception:
        return None


def talk(record: dict, trades: dict | None, question: str, history: list | None = None) -> dict:
    """Route the question, then answer it. Returns {"answer", "route", "offline"} for the API.

    offline is None when Hydrogen answered, "no_key" when the server has no GEMINI_API_KEY, or
    "gemini_error" when the call failed; then a question-aware template answers from the same facts.
    """
    turn = sum(1 for h in (history or []) if h.get("role") != "user")
    if not os.environ.get("GEMINI_API_KEY"):
        return {"answer": template_answer(facts(record, trades), question, turn), "route": None, "offline": "no_key"}
    routed = route_question(question)
    kind = routed["route"] if routed else None
    try:
        return {"answer": answer(record, trades, question, history, kind), "route": kind, "offline": None}
    except Exception:
        return {"answer": template_answer(facts(record, trades), question, turn), "route": kind,
                "offline": "gemini_error"}


def answer(record: dict, trades: dict | None, question: str, history: list | None = None,
           kind: str | None = None) -> str:
    """Hydrogen's in-character answer. Raises if Gemini fails or returns nothing."""
    f = facts(record, trades)
    if kind == "trade" and trades:
        f["trades"] = [{k: t.get(k) for k in ("date", "side", "price", "rule", "timestamp_s", "pnl_pct")}
                       for t in trades.get("trades", [])[-12:]]
    focus = f"\nThis question: {FOCUS[kind]}\n" if kind in FOCUS else ""
    key = os.environ["GEMINI_API_KEY"]
    contents = []
    for h in (history or [])[-8:]:
        contents.append({"role": "user" if h["role"] == "user" else "model", "parts": [{"text": h["text"]}]})
    contents.append({"role": "user", "parts": [{"text": question}]})
    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM.format(
            name=f["name"], personality=f["personality"], verdict=f["verdict"],
            tested=f["market_tested_on"], focus=focus, facts=json.dumps(f, indent=1))}]},
        "contents": contents,
        # Gemini 4 thinks before answering and thinking counts toward maxOutputTokens, so keep
        # thinking low and leave room for it, or the answer comes back empty (finishReason MAX_TOKENS).
        # Temperature is fixed on Gemini 4 models, so it isn't set.
        "generationConfig": {"maxOutputTokens": 1024, "thinkingConfig": {"thinkingLevel": "low"}},
    }
    req = urllib.request.Request(URL.format(model=MODEL), data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "x-goog-api-key": key})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    parts = data["candidates"][0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
    if not text:
        raise RuntimeError("Hydrogen returned no text")
    return text


def _money(v) -> str:
    return f"${v:,.0f}" if isinstance(v, (int, float)) else "an unknown amount"


def template_answer(f: dict, q: str, turn: int = 0) -> str:
    """Offline answer from the saved facts only, matched to what was asked. Used without Gemini.

    Every number comes from FACTS, like the Gemini answers. Questions it can't place get a
    different fact each turn instead of the same summary.
    """
    ql = q.lower()
    has = lambda *words: any(re.search(r"\b" + re.escape(w), ql) for w in words)  # word starts only
    rules = f.get("rules") or []
    claims = f.get("claim_checks") or []
    if f["verdict"] == "Untestable":
        if has("rule", "strategy", "how"):
            return "My rules: " + ("; ".join(rules[:3]) if rules else "there aren't any I can code. That's the problem.")
        return f"Honestly? Nobody can test me. {f.get('untestable_reason') or f.get('verdict_reason') or ''}".strip()

    if re.fullmatch(r"\W*(hi|hello|hey|yo|sup|who are you)\b.{0,15}", ql):
        return (f"I'm {f['name']}, {f.get('archetype') or 'a trader'} from \"{f.get('video_title')}\". "
                f"Ask me about my rules, my worst year, or whether I beat the random traders.")
    for y, v in (f.get("return_by_year_pct") or {}).items():
        if y in ql:
            return f"In {y} I made {v}%."
    if has("worst", "drop", "drawdown", "lose", "lost", "pain", "survive"):
        w = f.get("worst_moment") or {}
        return (f"My worst moment was {w.get('date')}: down {w.get('drawdown_pct')}% after "
                f"{w.get('losing_streak')} losses in a row.")
    if has("real", "edge", "luck", "verdict", "work", "legit", "good", "scam"):
        return f"My verdict is {f['verdict']}. {f.get('verdict_reason') or ''}".strip()
    if has("random", "hold", "holding", "compare", "beat", "better"):
        return (f"Just holding would have made {_money(f.get('just_holding_final'))} against my "
                f"{_money(f.get('final_balance'))}, and {f.get('pct_random_traders_did_better')}% of "
                f"1,000 random traders did better than me.")
    if has("trade", "win", "how many", "often"):
        return (f"I made {f.get('n_trades')} trades and won {f.get('win_rate_pct')}% of them. "
                f"My worst drop was {f.get('max_drawdown_pct')}%.")
    if has("claim", "guru", "video", "said", "promise", "true"):
        if claims:
            c = claims[turn % len(claims)]
            return f"The video claimed \"{c['claim']}\". My backtest says: {c['status']}. {c['note']}"
        return "The video made no claims I could check."
    if has("rule", "strategy", "how do you", "when do you", "buy", "sell", "entry", "exit", "stop"):
        return "My rules: " + "; ".join(rules[:3])
    tested = (f.get("tested") or {})
    rotation = [
        (f"I turned $10,000 into {_money(f.get('final_balance'))}, while just holding made "
         f"{_money(f.get('just_holding_final'))}. Verdict: {f['verdict']}."),
        f"I only talk numbers from my backtest. My verdict is {f['verdict']}: {f.get('verdict_reason') or ''}".strip(),
        (f"I was tested on {f.get('market_tested_on')} from {tested.get('start', 'the start')} to "
         f"{tested.get('end', 'today')}, {f.get('n_trades')} trades, {f.get('win_rate_pct')}% wins."),
        "Try asking me about my worst year, my rules, or whether I beat the random traders.",
    ]
    return rotation[turn % len(rotation)]
