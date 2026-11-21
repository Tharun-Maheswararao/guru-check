"""Fake NPCs for building and rehearsing the UI (Person 3). All numbers are made up.

Writes records shaped like schemas/npc_record.json and trades files shaped like
schemas/trades.json into data/npcs/, marked "demo": true (shown as DEMO DATA in the UI).
Delete data/npcs/demo-* before judging.

    python3 frontend/mock_npcs.py
"""

import math
import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.npc_store.store import save_npc  # noqa: E402

N, START = 1200, 10_000


def walk(seed, drift, vol):
    rng, v, out = random.Random(seed), 1.0, []
    for i in range(N):
        v *= math.exp(drift + 0.0015 * math.sin(i / 150) + rng.gauss(0, vol))
        out.append(v)
    return out


def fake_trades_file(seed, edge):
    dates = [(date(2021, 1, 1) + timedelta(days=i)).isoformat() for i in range(N)]
    price = [round(28000 * x, 2) for x in walk(1, 0.0006, 0.033)]
    hold = [round(START * p / price[0], 2) for p in price]
    rng = random.Random(seed)
    trades, equity, cash, units, i = [], [], START, 0.0, 0
    while i < N:
        if units == 0 and rng.random() < 0.03:
            units, entry = cash / price[i], cash
            trades.append({"side": "buy", "i": i, "date": dates[i], "price": price[i], "rule": "entry rule", "timestamp_s": 252})
        elif units and rng.random() < 0.08:
            cash = units * price[i] * (1 + edge)
            trades.append({"side": "sell", "i": i, "date": dates[i], "price": price[i], "rule": "exit rule",
                           "timestamp_s": 301, "pnl_pct": round(100 * (cash / entry - 1), 1)})
            units = 0
        equity.append(round(cash if not units else units * price[i], 2))
        i += 1
    peak, worst, wi = equity[0], 0, 0
    for k, v in enumerate(equity):
        peak = max(peak, v)
        if v / peak - 1 < worst:
            worst, wi = v / peak - 1, k
    band = {q: [round(START * x, 2) for x in walk(9 + j, 0.0002, 0.012 * (j + 1))] for j, q in enumerate(["p10", "p50", "p90"])}
    band["p10"] = [min(a, b) for a, b in zip(band["p10"], band["p50"])]
    band["p90"] = [max(a, b) for a, b in zip(band["p90"], band["p50"])]
    sells = [t for t in trades if t["side"] == "sell"]
    tf = {"market": "BTC-USD", "interval": "1d", "start_cash": START, "dates": dates, "price": price,
          "equity": equity, "hold": hold, "random_band": band, "trades": trades,
          "pain_moment": {"i": wi, "date": dates[wi], "drawdown_pct": round(100 * worst, 1), "losing_streak": 3}}
    res = {"final_balance": equity[-1], "max_drawdown": round(100 * worst, 1),
           "win_rate": round(100 * sum(t["pnl_pct"] > 0 for t in sells) / max(len(sells), 1), 1),
           "n_trades": len(sells), "hold_final": hold[-1], "random_percentile": 62.0, "share_random_better": 38.0}
    return tf, res


NPCS = [
    ("demo-sunny-sam", "Sunny Sam", "gold", "The Overconfident Swing Trader", "Lucky", 0.01,
     "THIS RSI TRICK NEVER LOSES", "Loud, cheerful, quick to brag, slowly admits luck.",
     [("entry", "Buy when RSI drops under 30", 252), ("exit", "Sell when RSI goes over 70", 301), ("claim", "This never loses", 30)]),
    ("demo-steady-steve", "Steady Steve", "green", "The Patient Trend Follower", "Real Edge", 0.03,
     "The only moving average strategy you need", "Calm, dry humor, always talks about patience.",
     [("entry", "Buy when 20 day average crosses above 100 day", 95), ("exit", "Sell when it drops below", 140)]),
    ("demo-risky-rita", "Risky Rita", "red", "The Nervous Scalper", "Just the Market", -0.005,
     "Breakout scalping made me rich", "Fast talking, jittery, checks the chart mid sentence.",
     [("entry", "Buy the 10 day high breakout", 61), ("exit", "Sell 3 days later", 88), ("claim", "Made me rich in 3 months", 12)]),
]


def main():
    for k, (nid, name, color, arch, verdict, edge, title, pers, tl) in enumerate(NPCS):
        tf, res = fake_trades_file(k + 3, edge)
        save_npc({"npc_id": nid, "name": name, "color": color, "archetype": arch, "personality": pers,
                  "portrait_path": f"frontend/art/{nid[5:]}.jpg", "strategy_id": nid, "verdict": verdict, "results": res, "demo": True,
                  "market": {"stated": "BTC", "tested_on": "BTC-USD"},
                  "source_videos": [{"url": f"https://www.youtube.com/watch?v=DEMO{k}", "title": title, "duration_s": 760}],
                  "rules_timeline": [{"kind": a, "rule": b, "timestamp_s": c} for a, b, c in tl]}, tf)
    save_npc({"npc_id": "demo-vague-vinny", "name": "Vague Vinny", "color": "violet", "archetype": "Talks in Vibes",
              "personality": "Dreamy, speaks in metaphors.", "portrait_path": "frontend/art/vague-vinny.jpg", "strategy_id": "vinny",
              "verdict": "Untestable", "results": None, "trades_path": "", "demo": True,
              "untestable_reason": "No rule can be written as code: entries depend on 'feeling the energy'.",
              "source_videos": [{"url": "https://www.youtube.com/watch?v=DEMO9", "title": "Trust the energy of the market", "duration_s": 610}],
              "rules_timeline": [{"kind": "claim", "rule": "You just feel when it's time", "timestamp_s": 140}]})
    print("4 demo NPCs written to data/npcs/")


if __name__ == "__main__":
    main()
