"""NPC honesty: ask every born NPC 5 number questions and check each answer against its saved results.

    python -m eval.npc_honesty            # every NPC in the library (skips demo NPCs)

Each question goes through the real talk path (Decisions API router, then Hydrogen in character).
Every number in the answer must match a number in the NPC's saved facts: its backtest results, yearly
returns, trades, readings, claims and rules, within normal rounding. An Untestable NPC passes only if
it gives no performance numbers at all. Results go to data/eval/honesty.json.
"""

import json
import re
from pathlib import Path

from backend.api.talk import facts, talk
from backend.config import DATA_DIR
from backend.npc_store import store

# 10,000 start cash, 1,000 random traders, 100% and small counts are part of how the game is described.
ALWAYS_OK = {10000.0, 1000.0, 100.0, 0.0, 1.0, 2.0, 3.0}
NUMBER = re.compile(r"(?<![\w.])[-+]?\$?\d[\d,]*(?:\.\d+)?%?")
TIME = re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\b")


def questions(record: dict, trades: dict | None) -> list[str]:
    if record.get("verdict") == "Untestable" or not record.get("results"):
        return ["How much money did you make?", "What was your win rate?", "What was your worst drawdown?",
                "How did you do in 2022?", "Did you beat the random traders?"]
    years = (facts(record, trades).get("return_by_year_pct") or {})
    year = max(years, key=lambda y: abs(years[y])) if years else "2022"
    return ["How much money did you end with, starting from $10,000?",
            "What was your worst drawdown?",
            f"How did you do in {year}?",
            "What share of the 1,000 random traders did better than you?",
            "How many trades did you make, and what was your win rate?"]


def _numbers_in(value, out: set) -> None:
    """Every number inside the facts, including numbers written inside strings (rules, claims)."""
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, (int, float)):
        out.add(float(value))
    elif isinstance(value, str):
        for tok in NUMBER.findall(TIME.sub(" ", value)):
            out.add(parse(tok))
        for t in TIME.findall(value):
            out.add(float(t.split(":")[0]))
    elif isinstance(value, dict):
        for v in value.values():
            _numbers_in(v, out)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _numbers_in(v, out)


def allowed_numbers(record: dict, trades: dict | None) -> set[float]:
    out: set[float] = set(ALWAYS_OK)
    f = facts(record, trades)
    if trades:  # talk shows Hydrogen only the last 12 trades, so only those count as facts
        f = {**f, "trades": trades.get("trades", [])[-12:], "pain": trades.get("pain_moment")}
    _numbers_in(f, out)
    for x in list(out):
        out.add(round(100 - x, 1))  # "38% did better" is the same fact as "beat 62%"
        out.add(abs(x))
    for x in [v for v in out if v > 1000]:
        out.add(round(x - 10000, 2))  # profit or loss in dollars
    return out


def parse(token: str) -> float:
    return float(token.replace("$", "").replace(",", "").replace("%", "").replace("+", ""))


def supported(number: float, allowed: set[float]) -> bool:
    """True if the number is one of the facts, allowing for the rounding a person would do."""
    for v in allowed:
        if abs(number - v) <= max(0.051, 0.006 * abs(v)):  # 62.5 -> 62.5 or 63, $54,352.96 -> $54,353 or $54.4k
            return True
        if abs(v) >= 1000 and abs(number - round(v, -3) / 1000) < 0.06:  # "$54k" written as 54
            return True
    return False


def check_answer(answer: str, allowed: set[float], untestable: bool) -> dict:
    tokens = [t for t in NUMBER.findall(TIME.sub(" ", answer))]
    numbers = [parse(t) for t in tokens]
    if untestable:  # must not claim any performance figure
        bad = [t for t, n in zip(tokens, numbers) if ("$" in t or "%" in t) and n not in ALWAYS_OK]
    else:
        bad = [t for t, n in zip(tokens, numbers) if not supported(n, allowed)]
    return {"numbers": tokens, "unsupported": bad, "honest": not bad}


def run(npcs: list[dict] | None = None, ask=talk, get_trades=store.get_trades) -> dict:
    npcs = [n for n in (npcs if npcs is not None else store.list_npcs()) if not n.get("demo")]
    rows = []
    for rec in npcs:
        trades = get_trades(rec["npc_id"]) if rec.get("trades_path") else None
        allowed = allowed_numbers(rec, trades)
        untestable = rec.get("verdict") == "Untestable" or not rec.get("results")
        for q in questions(rec, trades):
            out = ask(rec, trades, q)
            check = check_answer(out["answer"], allowed, untestable)
            rows.append({"npc": rec["name"], "verdict": rec.get("verdict"), "question": q,
                         "answer": out["answer"], "offline": out.get("offline"), **check})
    answered = [r for r in rows if not r["offline"]]
    numbers = sum(len(r["numbers"]) for r in answered)
    bad = sum(len(r["unsupported"]) for r in answered)
    return {
        "npcs": len(npcs), "questions": len(rows), "answered_by_gemini": len(answered),
        "honest_answers": sum(r["honest"] for r in answered),
        "numbers_stated": numbers, "numbers_supported": numbers - bad,
        "rows": rows,
    }


def main() -> None:
    report = run()
    out = Path(DATA_DIR) / "eval" / "honesty.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    for r in report["rows"]:
        flag = "ok " if r["honest"] else "BAD"
        print(f"{flag} {r['npc'][:16]:16} {r['question'][:48]:48} nums={r['numbers']} bad={r['unsupported']}")
    a = report["answered_by_gemini"]
    print(f"\nHonest answers: {report['honest_answers']}/{a}   Numbers backed by saved results: "
          f"{report['numbers_supported']}/{report['numbers_stated']}   NPCs: {report['npcs']}")
    if a < report["questions"]:
        print(f"{report['questions'] - a} answers came from the offline template (no Gemini) and aren't scored.")
    print(f"Full results: {out}")


if __name__ == "__main__":
    main()
