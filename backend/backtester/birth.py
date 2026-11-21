"""Person 2's half of an NPC birth: backtest_and_judge(rules, on_step) -> (npc_record, trades).

Called by backend.pipeline.birth_npc after the Matcher. Steps reported to the birth screen:
  backtest  Neon writes the strategy code; the sandbox runs every reading of the rules with costs
  randoms   1,000 random traders race each reading; market and momentum are regressed out
  judge     Carbon reviews the code, checks the claims, gives the verdict and the personality

The NPC's headline numbers come from the median reading (not the best one), so a lucky setting
can't flatter it. birth_npc fills in the rule fields, draws the portrait and saves both files.
"""

import os
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

import numpy as np
import pandas as pd

from backend.backtester.codegen import code_and_positions
from backend.backtester.engine import (COST, START_CASH, build_readings, chart_index, load_prices,
                                       run_backtest)
from backend.randoms.randoms import N_TRADERS, percentile_beaten, race
from backend.skeptic.factors import factor_check
from backend.skeptic import audit as auditor
from backend.skeptic.skeptic import COLORS, RANK, evidence_verdict, judge

MAX_CHART_TRADES = 600
MIN_MAIN_TRADES = 5  # a reading needs this many trades to speak for the NPC, when any reading has them


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "npc"


def _fmt_date(ts: pd.Timestamp, timeframe: str) -> str:
    return ts.strftime("%Y-%m-%d") if timeframe == "1d" else ts.strftime("%Y-%m-%d %H:%M")


def _years(df: pd.DataFrame) -> float:
    return (df.index[-1] - df.index[0]).days / 365.25


def _trade_rule(rules: dict, kind: str, won: bool | None = None) -> tuple[str, float]:
    """Which rule a chart marker cites. Winning exits cite the exit rule, losing ones the stop."""
    order = ["entry"] if kind == "entry" else (["exit", "stop_loss"] if won else ["stop_loss", "exit"])
    for key in order:
        if rules.get(key):
            return rules[key][0]["rule"], rules[key][0]["timestamp_s"]
    return "", 0


def trades_file(df: pd.DataFrame, timeframe: str, result: dict, band: dict, checkpoints: np.ndarray,
                rules: dict) -> dict:
    """The Simulate replay file, shaped like schemas/trades.json."""
    close = df["close"].to_numpy()
    dates = [_fmt_date(df.index[i], timeframe) for i in checkpoints]
    to_chart = lambda bar: int(min(len(checkpoints) - 1, np.searchsorted(checkpoints, bar)))
    events = []
    for t in result["trades"]:
        entry_rule, entry_ts = _trade_rule(rules, "entry")
        events.append({"side": "buy" if t["side"] > 0 else "sell", "i": to_chart(t["a"]),
                       "date": _fmt_date(df.index[t["a"]], timeframe), "price": round(float(close[t["a"]]), 2),
                       "rule": entry_rule, "timestamp_s": entry_ts})
        if not t.get("open"):
            exit_rule, exit_ts = _trade_rule(rules, "exit", t["pnl"] > 0)
            events.append({"side": "sell" if t["side"] > 0 else "buy", "i": to_chart(t["b"]),
                           "date": _fmt_date(df.index[t["b"]], timeframe), "price": round(float(close[t["b"]]), 2),
                           "rule": exit_rule, "timestamp_s": exit_ts, "pnl_pct": round(100 * t["pnl"], 1)})
    if len(events) > MAX_CHART_TRADES:  # keep the replay readable: evenly spaced trades
        keep = np.unique(np.linspace(0, len(events) - 1, MAX_CHART_TRADES).astype(int))
        events = [events[k] for k in keep]

    closed = [t for t in result["trades"] if not t.get("open") and t["b"] <= result["trough"]]
    streak = best = 0
    for t in closed:
        streak = streak + 1 if t["pnl"] <= 0 else 0
        best = max(best, streak)
    trough = result["trough"]
    return {
        "market": rules["market"]["tested_on"], "interval": timeframe, "start_cash": START_CASH,
        "dates": dates,
        "price": [round(float(close[i]), 2) for i in checkpoints],
        "equity": [round(float(result["equity"][i]), 2) for i in checkpoints],
        "hold": [round(float(START_CASH * close[i] / close[0]), 2) for i in checkpoints],
        "random_band": {q: [round(float(v), 2) for v in band[q]] for q in ["p10", "p50", "p90"]},
        "trades": events,
        "pain_moment": {"i": to_chart(trough), "date": _fmt_date(df.index[trough], timeframe),
                        "drawdown_pct": round(result["max_drawdown"], 1), "losing_streak": best},
    }


def choose_main(results: dict) -> int:
    """The reading the NPC speaks for: the median (the lower one when even) among readings with at
    least MIN_MAIN_TRADES trades, so one lucky setting can't speak for the strategy and a reading
    with a trade or two can't either. Falls back to any reading that trades, then to all of them."""
    trading = ([k for k in results if results[k]["trades_total"] >= MIN_MAIN_TRADES]
               or [k for k in results if results[k]["trades_total"] > 0] or list(results))
    ranked = sorted(trading, key=lambda k: results[k]["final_balance"])
    return ranked[(len(ranked) - 1) // 2]


def _untestable(rules: dict, reason: str, on_step: Callable, code: str = "") -> tuple[dict, None]:
    on_step("backtest", f"Nothing to backtest: {reason}")
    on_step("randoms", "Skipped: no trades to race")
    on_step("judge", "Carbon is judging the claims")
    j = judge(rules, {"testable": False, "reason": reason}, code, ("Untestable", reason))
    record = {"npc_id": f"{_slug(j['name'])}-{rules['strategy_id'][:6]}", "name": j["name"],
              "color": j["color"], "archetype": j["archetype"], "personality": j["personality"],
              "portrait_path": "", "verdict": "Untestable", "verdict_reason": j["verdict_reason"],
              "results": None, "trades_path": "", "claim_checks": j["claim_checks"],
              "code_review": j["code_review"]}
    return record, None


def backtest_and_judge(rules: dict, on_step: Callable) -> tuple[dict, dict | None]:
    if not rules["testable"]:
        return _untestable(rules, rules["untestable_reason"], on_step)

    market = rules["market"]["tested_on"]
    df, timeframe = load_prices(market, rules["timeframe"])
    readings = build_readings(rules.get("vague_terms", []), seed=rules["strategy_id"])
    on_step("backtest", f"Neon is coding {len(readings)} readings of the rules for {market} {timeframe}")
    coded = code_and_positions(rules, df, timeframe, readings, notify=lambda d: on_step("backtest", d))
    ok = [(k, p) for k, p in enumerate(coded["positions"]) if p is not None]
    if not ok:
        return _untestable(rules, "The rules couldn't be turned into working code.", on_step, coded["code"])

    on_step("backtest", f"Backtesting {len(ok)} readings on {_years(df):.1f} years of {market} with "
                        f"{100 * COST:.2f}% costs per trade")
    results = {k: run_backtest(df, p) for k, p in ok}

    on_step("randoms", f"Racing {N_TRADERS:,} random traders")
    close = df["close"].to_numpy()
    checkpoints = chart_index(len(df))
    races = {k: race(close, r["trades"], checkpoints) for k, r in results.items()}
    summary = []
    for k, r in results.items():
        r["random_percentile"] = percentile_beaten(r["final_balance"], races[k]["finals"])
        r["trades_total"] = len(r["trades"])
        summary.append({"reading": readings[k], "final_balance": round(r["final_balance"], 2),
                        "random_percentile": round(r["random_percentile"], 1), "n_trades": r["n_trades"],
                        "max_drawdown": round(r["max_drawdown"], 1)})
    main_k = choose_main(results)
    main = results[main_k]
    factors = factor_check(df, main["bar_ret"])

    # Second managed agent: the Carbon auditor rechecks the backtest in its own sandbox while the
    # Carbon judge reviews the code and claims. A failed or slow audit never blocks the birth.
    audit_pool = ThreadPoolExecutor(max_workers=1)
    audit_job = None
    if os.environ.get("AUDIT_AGENT", "1") != "0":
        audit_job = audit_pool.submit(auditor.audit, coded["code"], df, readings[main_k], market, timeframe)
        on_step("judge", "Carbon is judging the claims while the Carbon auditor agent rechecks the backtest in its sandbox")
    else:
        on_step("judge", "Carbon is reviewing the code and checking the claims")
    cap = evidence_verdict(True, main, summary, factors, coded["report"].get("lookahead_free"))
    evidence = {
        "tested_on": market, "timeframe": timeframe, "period": [str(df.index[0].date()), str(df.index[-1].date())],
        "start_cash": START_CASH, "costs_per_trade_pct": 100 * COST,
        "main_reading": readings[main_k],
        "main_results": {"final_balance": round(main["final_balance"], 2), "max_drawdown_pct": round(main["max_drawdown"], 1),
                         "win_rate_pct": round(main["win_rate"], 1), "closed_trades": main["n_trades"],
                         "time_in_market_pct": round(100 * main["exposure"], 1),
                         "beats_random_traders_pct": round(main["random_percentile"], 1),
                         "buy_and_hold_final": round(main["hold_final"], 2)},
        "all_readings": summary, "market_and_momentum_regression": factors,
        "automatic_lookahead_test_passed": coded["report"].get("lookahead_free"),
        "code_problem_after_retries": coded["problem"],
    }
    j = judge(rules, evidence, coded["code"], cap)
    audit_result = {"status": "off"}
    if audit_job is not None:
        try:
            audit_result = audit_job.result(timeout=auditor.TIMEOUT_S + 30)
        except Exception as e:
            audit_result = {"status": "unavailable", "error": f"{type(e).__name__}: {e}"[:300]}
    audit_pool.shutdown(wait=False)
    problem = auditor.failed_audit(audit_result)
    if problem and RANK.get(j["verdict"], 0) > RANK["Lucky"]:
        j["verdict"], j["color"] = "Lucky", COLORS["Lucky"]
        j["verdict_reason"] = f"{problem} {j['verdict_reason']}"

    if j["verdict"] == "Untestable":  # no reading ever traded: no numbers or replay to show
        return {"npc_id": f"{_slug(j['name'])}-{rules['strategy_id'][:6]}", "name": j["name"],
                "color": j["color"], "archetype": j["archetype"], "personality": j["personality"],
                "portrait_path": "", "verdict": "Untestable", "verdict_reason": j["verdict_reason"],
                "results": None, "trades_path": "", "readings": summary, "claim_checks": j["claim_checks"],
                "code_review": j["code_review"], "code_path": coded["code_path"]}, None
    trades = trades_file(df, timeframe, main, races[main_k]["band"], checkpoints, rules)
    record = {
        "npc_id": f"{_slug(j['name'])}-{rules['strategy_id'][:6]}", "name": j["name"], "color": j["color"],
        "archetype": j["archetype"], "personality": j["personality"], "portrait_path": "",
        "verdict": j["verdict"], "verdict_reason": j["verdict_reason"],
        "results": {"final_balance": round(main["final_balance"], 2), "max_drawdown": round(main["max_drawdown"], 1),
                    "win_rate": round(main["win_rate"], 1), "random_percentile": round(main["random_percentile"], 1),
                    "share_random_better": round(100 - main["random_percentile"], 1),
                    "hold_final": round(main["hold_final"], 2), "n_trades": main["n_trades"]},
        "readings": summary, "main_reading": readings[main_k], "factor_check": factors,
        "claim_checks": j["claim_checks"], "code_review": j["code_review"],
        "lookahead_free": coded["report"].get("lookahead_free"), "code_path": coded["code_path"],
        "code_author": coded.get("author"), "audit": audit_result,
        "tested": {"market": market, "timeframe": timeframe, "start": evidence["period"][0],
                   "end": evidence["period"][1], "bars": len(df), "costs_per_trade_pct": 100 * COST},
        "trades_path": "",
    }
    return record, trades
