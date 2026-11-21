"""Talk to an NPC. Gemini Hydrogen answers in character, grounded ONLY in the saved record.

The NPC can't lie about numbers: every figure is passed in from the saved backtest and the
prompt forbids inventing any other. Without GEMINI_API_KEY, a plain template answers instead.
"""

import json
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

FACTS:
{facts}"""


def answer(record: dict, trades: dict | None, question: str, history: list | None = None) -> str:
    f = facts(record, trades)
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return template_answer(f, question)
    contents = []
    for h in (history or [])[-8:]:
        contents.append({"role": "user" if h["role"] == "user" else "model", "parts": [{"text": h["text"]}]})
    contents.append({"role": "user", "parts": [{"text": question}]})
    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM.format(
            name=f["name"], personality=f["personality"], verdict=f["verdict"],
            tested=f["market_tested_on"], facts=json.dumps(f, indent=1))}]},
        "contents": contents,
        # Gemini 4 thinks before answering and thinking counts toward maxOutputTokens, so keep
        # thinking low and leave room for it, or the answer comes back empty (finishReason MAX_TOKENS).
        # Temperature is fixed on Gemini 4 models, so it isn't set.
        "generationConfig": {"maxOutputTokens": 1024, "thinkingConfig": {"thinkingLevel": "low"}},
    }
    req = urllib.request.Request(URL.format(model=MODEL), data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "x-goog-api-key": key})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.load(resp)
        parts = data["candidates"][0].get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
        return text or template_answer(f, question)
    except Exception as e:  # keep the demo alive
        return template_answer(f, question) + f" (offline answer: {type(e).__name__})"


def template_answer(f: dict, q: str) -> str:
    ql = q.lower()
    if f["verdict"] == "Untestable":
        return f"Honestly? Nobody can test me. {f.get('untestable_reason') or ''}".strip()
    if "worst" in ql or "drop" in ql or "lose" in ql:
        w = f.get("worst_moment") or {}
        return f"My worst moment was {w.get('date')}: down {w.get('drawdown_pct')}% after {w.get('losing_streak')} losses in a row."
    for y, v in (f.get("return_by_year_pct") or {}).items():
        if y in ql:
            return f"In {y} I made {v}%."
    if "rule" in ql or "strategy" in ql:
        return "My rules: " + "; ".join(f["rules"][:3])
    return (f"I turned $10,000 into ${f['final_balance']:,.0f}. Just holding would be "
            f"${f['just_holding_final']:,.0f}, and {f['pct_random_traders_did_better']}% of random "
            f"traders beat me. Verdict: {f['verdict']}.")
