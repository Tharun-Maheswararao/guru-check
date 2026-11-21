"""Offline tests for the backtester, sandbox, random traders and Skeptic, with fake model calls.

    python -m unittest discover tests
"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd

from backend.backtester import birth, codegen
from backend.backtester.engine import START_CASH, build_readings, chart_index, run_backtest
from backend.randoms.randoms import percentile_beaten, race
from backend.skeptic import skeptic
from backend.skeptic.factors import factor_check
from backend.skeptic.skeptic import evidence_verdict


def setUpModule():
    codegen.MODE = "direct"  # tests never call the real managed agents unless they mock them
    os.environ["AUDIT_AGENT"] = "0"


def prices(n=900, seed=3, drift=0.0005, vol=0.03):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(drift, vol, n)))
    idx = pd.date_range("2020-01-01", periods=n, freq="D", tz="UTC")
    return pd.DataFrame({"open": close, "high": close * 1.01, "low": close * 0.99, "close": close,
                         "volume": 1.0}, index=idx)


HONEST = '''def generate_positions(df, reading):
    fast = df.close.rolling(int(reading.get("fast", "20"))).mean()
    slow = df.close.rolling(100).mean()
    return (fast > slow).astype(int).tolist()
'''
PEEK = '''def generate_positions(df, reading):
    return (df.close.shift(-1) > df.close).astype(int).tolist()
'''
FORBIDDEN = '''import os
def generate_positions(df, reading):
    return [0] * len(df)
'''

ONLY_30_TRADES = '''def generate_positions(df, reading):
    if reading["fast"] != "30":
        return [0] * len(df)
    return (df.close.rolling(30).mean() > df.close.rolling(100).mean()).astype(int).tolist()
'''

RULES = {
    "strategy_id": "a" * 40, "strategy_name": "MA cross", "market": {"stated": "BTC", "tested_on": "BTC-USD"},
    "timeframe": "1d", "entry": [{"rule": "fast MA above slow", "timestamp_s": 10}],
    "exit": [{"rule": "fast MA below slow", "timestamp_s": 20}], "stop_loss": [], "filters": [],
    "vague_terms": [{"term": "fast", "meanings": ["10", "20", "30"]}],
    "claims": [{"text": "never loses", "timestamp_s": 5}], "testable": True, "untestable_reason": None,
    "source_videos": [{"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}],
}


class EngineTests(unittest.TestCase):
    def test_hand_checked_long_and_short(self):
        df = pd.DataFrame({"close": [100, 100, 110, 121, 121, 100.0]})
        r = run_backtest(df, np.array([0, 1, 1, 0, -1, 0], np.int8))
        self.assertEqual([t["side"] for t in r["trades"]], [1, -1])
        self.assertAlmostEqual(r["trades"][0]["pnl"], 1.21 * (1 - 0.0015) ** 2 - 1, places=6)
        self.assertAlmostEqual(r["trades"][1]["pnl"], (1 + 21 / 121) * (1 - 0.0015) ** 2 - 1, places=6)
        self.assertEqual(r["n_trades"], 2)
        self.assertEqual(r["win_rate"], 100.0)

    def test_signal_trades_next_bar_not_same_bar(self):
        df = pd.DataFrame({"close": [100, 200.0]})
        r = run_backtest(df, np.array([1, 1], np.int8))  # buy at close of bar 0, so bar 1's +100% counts
        self.assertAlmostEqual(r["final_balance"], START_CASH * (1 - 0.0015) * 2, places=4)
        r = run_backtest(df, np.array([0, 1], np.int8))  # signal on the last bar earns nothing
        self.assertLess(r["final_balance"], START_CASH)

    def test_readings(self):
        self.assertEqual(build_readings([]), [{}])
        self.assertEqual(len(build_readings(RULES["vague_terms"])), 3)
        many = [{"term": t, "meanings": ["x", "y", "z"]} for t in "abcd"]
        r = build_readings(many, seed="s")
        self.assertEqual(len(r), 6)
        self.assertEqual(r[0], {t: "x" for t in "abcd"})
        self.assertEqual(len({tuple(x.values()) for x in r}), 6)


class SandboxTests(unittest.TestCase):
    def test_honest_code_runs_every_reading(self):
        df = prices(400)
        pos, rep = codegen.run_code(HONEST, df, [{"fast": "10"}, {"fast": "30"}])
        self.assertTrue(rep["lookahead_free"])
        self.assertIsNone(codegen.problem_with(pos, rep))
        self.assertFalse(np.array_equal(pos[0], pos[1]))

    def test_sandbox_sees_the_real_dates(self):
        idx = pd.date_range("2024-03-01", periods=600, freq="5min", tz="UTC")
        df = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}, index=idx)
        for unit in ["ns", "us", "s"]:  # however pandas stores the dates
            d = df.copy()
            d.index = d.index.as_unit(unit)
            code = "def generate_positions(df, reading):\n    return ((df.index.hour == 8) & (df.index.year == 2024)).astype(int).tolist()\n"
            pos, rep = codegen.run_code(code, d, [{}])
            expected = ((idx.hour == 8) & (idx.year == 2024)).astype(int)
            self.assertTrue(np.array_equal(pos[0], expected), unit)

    def test_peeking_and_forbidden_imports_are_caught(self):
        df = prices(400)
        pos, rep = codegen.run_code(PEEK, df, [{}])
        self.assertFalse(rep["lookahead_free"])
        self.assertIn("future data", codegen.problem_with(pos, rep))
        pos, rep = codegen.run_code(FORBIDDEN, df, [{}])
        self.assertIn("not allowed", rep["load_error"])

    def test_bad_code_gets_one_fix(self):
        answers = [PEEK, HONEST]
        with mock.patch.object(codegen, "write_code", side_effect=lambda *a, **k: answers.pop(0)) as w:
            out = codegen.code_and_positions(RULES, prices(400), "1d", [{"fast": "20"}],
                                              save_dir=tempfile.mkdtemp())
        self.assertEqual(w.call_count, 2)
        previous_code, problem = w.call_args_list[1].args[3]  # second try sees the first code and why it failed
        self.assertEqual(previous_code, PEEK)
        self.assertIn("future data", problem)
        self.assertIsNone(out["problem"])


class RandomsAndFactorsTests(unittest.TestCase):
    def test_random_timing_sits_in_the_crowd(self):
        df = prices(1500, seed=5)
        pos = np.random.default_rng(2).integers(0, 2, len(df)).astype(np.int8)
        r = run_backtest(df, pos)
        rc = race(df.close.to_numpy(), r["trades"], chart_index(len(df)))
        self.assertTrue(10 < percentile_beaten(r["final_balance"], rc["finals"]) < 90)
        self.assertEqual(len(rc["band"]["p50"]), len(chart_index(len(df))))
        self.assertTrue(np.all(rc["band"]["p10"] <= rc["band"]["p90"]))

    def test_no_trades_means_flat_randoms(self):
        df = prices(300)
        r = run_backtest(df, np.zeros(len(df), np.int8))
        rc = race(df.close.to_numpy(), r["trades"], chart_index(len(df)))
        self.assertTrue(np.all(rc["finals"] == START_CASH))

    def test_holding_the_market_is_all_beta(self):
        df = prices(1200)
        r = run_backtest(df, np.ones(len(df), np.int8))
        f = factor_check(df, r["bar_ret"])
        self.assertAlmostEqual(f["beta_market"], 1.0, places=1)
        self.assertLess(abs(f["alpha_annual_pct"]), 2)


class SkepticTests(unittest.TestCase):
    def reading(self, pct):
        return {"random_percentile": pct}

    def test_evidence_verdicts(self):
        main = {"trades_total": 10, "random_percentile": 95}
        good_alpha = {"alpha_t": 2.5, "alpha_annual_pct": 8}
        no_alpha = {"alpha_t": 0.4, "alpha_annual_pct": 3}
        three_good = [self.reading(95)] * 3
        self.assertEqual(evidence_verdict(True, main, three_good, good_alpha, True)[0], "Real Edge")
        self.assertEqual(evidence_verdict(True, main, three_good, no_alpha, True)[0], "Just the Market")
        self.assertEqual(evidence_verdict(True, main, [self.reading(95)] + [self.reading(20)] * 2, good_alpha, True)[0], "Lucky")
        self.assertEqual(evidence_verdict(True, {**main, "random_percentile": 40}, three_good, good_alpha, True)[0], "Lucky")
        self.assertEqual(evidence_verdict(True, main, three_good, good_alpha, False)[0], "Lucky")
        self.assertEqual(evidence_verdict(True, {**main, "trades_total": 0}, three_good, good_alpha, True)[0], "Untestable")
        self.assertEqual(evidence_verdict(False, None, [], None, None)[0], "Untestable")

    def carbon(self, verdict):
        return {"verdict": verdict, "verdict_reason": "Carbon says so", "name": "Test Tess",
                "archetype": "The Tester", "personality": "Calm.", "claim_checks": [],
                "code_review": {"lookahead_risk": "low", "matches_rules": True, "notes": ""}}

    def test_carbon_can_be_stricter_but_never_kinder(self):
        with mock.patch.object(skeptic.llm, "_retry", return_value=self.carbon("Real Edge")):
            j = skeptic.judge(RULES, {}, "", ("Lucky", "numbers say lucky"))
        self.assertEqual((j["verdict"], j["verdict_reason"], j["color"]), ("Lucky", "numbers say lucky", "gold"))
        with mock.patch.object(skeptic.llm, "_retry", return_value=self.carbon("Lucky")):
            j = skeptic.judge(RULES, {}, "", ("Real Edge", "numbers say edge"))
        self.assertEqual(j["verdict"], "Lucky")

    def test_carbon_failure_falls_back_to_the_numbers(self):
        with mock.patch.object(skeptic.llm, "_retry", side_effect=RuntimeError("down")):
            j = skeptic.judge(RULES, {}, "", ("Just the Market", "beta only"))
        self.assertEqual(j["verdict"], "Just the Market")
        self.assertEqual(j["name"], "Ma Cross")


class BacktestAndJudgeTests(unittest.TestCase):
    def test_full_backtest_with_fake_models(self):
        steps = []
        with mock.patch.object(birth, "load_prices", return_value=(prices(900), "1d")), \
             mock.patch.object(codegen, "DATA_DIR", Path(tempfile.mkdtemp())), \
             mock.patch.object(codegen, "write_code", return_value=HONEST), \
             mock.patch.object(skeptic.llm, "_retry", return_value=SkepticTests.carbon(None, "Lucky")):
            record, trades = birth.backtest_and_judge(RULES, lambda s, d="": steps.append(s))
        self.assertEqual(list(dict.fromkeys(steps)), ["backtest", "randoms", "judge"])
        self.assertEqual(record["npc_id"], "test-tess-aaaaaa")
        self.assertEqual(len(record["readings"]), 3)
        for key in ["final_balance", "max_drawdown", "win_rate", "random_percentile", "share_random_better",
                    "hold_final", "n_trades"]:
            self.assertIn(key, record["results"])
        self.assertTrue(record["lookahead_free"])
        with open("schemas/trades.json") as f:
            expected = set(json.load(f)) - {"_note"}
        self.assertEqual(set(trades), expected)
        n = len(trades["dates"])
        self.assertTrue(all(len(trades[k]) == n for k in ["price", "equity", "hold"]))
        self.assertTrue(all(0 <= t["i"] < n for t in trades["trades"]))

    def test_main_reading_skips_readings_that_never_trade(self):
        with mock.patch.object(birth, "load_prices", return_value=(prices(900), "1d")), \
             mock.patch.object(codegen, "DATA_DIR", Path(tempfile.mkdtemp())), \
             mock.patch.object(codegen, "write_code", return_value=ONLY_30_TRADES), \
             mock.patch.object(skeptic.llm, "_retry", return_value=SkepticTests.carbon(None, "Lucky")):
            record, _ = birth.backtest_and_judge({**RULES, "strategy_id": "b" * 40}, lambda s, d="": None)
        self.assertEqual(record["main_reading"], {"fast": "30"})
        self.assertGreater(record["results"]["n_trades"], 0)

    def test_main_reading_prefers_readings_with_enough_trades(self):
        def fake_results(trades_by_reading, finals):
            return {k: {"trades_total": t, "final_balance": f} for k, (t, f) in enumerate(zip(trades_by_reading, finals))}
        # Zoned Zack's real readings: the 11-trade $7,770 reading, not the 2-trade one.
        self.assertEqual(birth.choose_main(fake_results([20, 3, 11, 2, 15, 11], [8456, 9832, 7770, 8142, 5662, 11969])), 2)
        # London Liam's: nothing has 5 trades but one, so it speaks; zero-trade readings never do.
        self.assertEqual(birth.choose_main(fake_results([0, 0, 493, 0, 2, 0], [1e4, 1e4, 1798, 1e4, 10152, 1e4])), 2)
        self.assertEqual(birth.choose_main(fake_results([0, 2, 0], [1e4, 9000, 1e4])), 1)

    def test_managed_agent_code_is_verified_locally(self):
        from backend.backtester import managed
        with mock.patch.object(managed, "write_code", return_value=(HONEST, {"via": "managed"})), \
             mock.patch.object(codegen, "write_code", side_effect=AssertionError("direct path used")):
            out = codegen.code_and_positions(RULES, prices(400), "1d", [{"fast": "20"}],
                                             save_dir=tempfile.mkdtemp(), mode="managed")
        self.assertEqual(out["author"]["via"], "managed")
        self.assertTrue(out["author"]["passed_local_checks"])

    def test_managed_agent_failure_or_bad_code_falls_back_to_direct(self):
        from backend.backtester import managed
        for behaviour in [TimeoutError("too slow"), (PEEK, {"via": "managed"})]:
            kwargs = {"side_effect": behaviour} if isinstance(behaviour, Exception) else {"return_value": behaviour}
            with mock.patch.object(managed, "write_code", **kwargs), \
                 mock.patch.object(codegen, "write_code", return_value=HONEST) as direct:
                out = codegen.code_and_positions(RULES, prices(400), "1d", [{"fast": "20"}],
                                                 save_dir=tempfile.mkdtemp(), mode="managed")
            self.assertEqual(direct.call_count, 1)
            self.assertIsNone(out["problem"])
            self.assertTrue(out["author"]["via"].startswith("direct"))

    def test_sample_fits_an_inline_file(self):
        from backend.backtester import managed
        idx = pd.date_range("2020-01-01", periods=60000, freq="5min", tz="UTC")
        df = pd.DataFrame({"open": 65000.12, "high": 65010.5, "low": 64990.25, "close": 65001.75,
                           "volume": 12.345678}, index=idx)
        text = managed.sample_csv(df)
        self.assertLessEqual(len(text.encode()), managed.MAX_CSV_BYTES)
        self.assertTrue(text.rstrip().endswith(text.rstrip().splitlines()[-1]))
        last_ts = int(text.rstrip().splitlines()[-1].split(",")[0])
        self.assertEqual(last_ts, int(idx[-1].timestamp()))

    def test_saved_code_is_reused_without_asking_neon(self):
        folder = Path(tempfile.mkdtemp())
        (folder / f"{RULES['strategy_id']}.py").write_text(HONEST)
        with mock.patch.object(codegen, "write_code", side_effect=AssertionError("Neon called")):
            out = codegen.code_and_positions(RULES, prices(400), "1d", [{"fast": "20"}], save_dir=folder)
        self.assertTrue(out["reused"])

    def birth_with_audit(self, audit_behaviour):
        from backend.skeptic import audit as auditor
        edge = {**SkepticTests.carbon(None, "Real Edge"), "color": "green"}
        kwargs = {"side_effect": audit_behaviour} if isinstance(audit_behaviour, Exception) else {"return_value": audit_behaviour}
        with mock.patch.dict(os.environ, {"AUDIT_AGENT": "1"}), \
             mock.patch.object(birth, "load_prices", return_value=(prices(900), "1d")), \
             mock.patch.object(codegen, "DATA_DIR", Path(tempfile.mkdtemp())), \
             mock.patch.object(codegen, "write_code", return_value=HONEST), \
             mock.patch.object(birth, "judge", return_value=edge), \
             mock.patch.object(auditor, "audit", **kwargs) as audit_call:
            record, _ = birth.backtest_and_judge(RULES, lambda s, d="": None)
        return record, audit_call

    def test_passing_audit_keeps_the_verdict(self):
        record, call = self.birth_with_audit({"numbers_match": True, "lookahead_found": False, "notes": "ok"})
        self.assertEqual(call.call_count, 1)
        self.assertEqual(record["verdict"], "Real Edge")
        self.assertTrue(record["audit"]["numbers_match"])

    def test_failed_audit_caps_the_verdict(self):
        for finding in [{"numbers_match": True, "lookahead_found": True}, {"numbers_match": False, "lookahead_found": False}]:
            record, _ = self.birth_with_audit(finding)
            self.assertEqual((record["verdict"], record["color"]), ("Lucky", "gold"))
            self.assertIn("auditor", record["verdict_reason"])

    def test_audit_that_crashes_never_blocks_a_birth(self):
        record, _ = self.birth_with_audit(TimeoutError("too slow"))
        self.assertEqual(record["verdict"], "Real Edge")
        self.assertEqual(record["audit"]["status"], "unavailable")

    def test_expected_numbers_for_the_auditor(self):
        from backend.skeptic import audit as auditor
        df = prices(600)
        exp = auditor.expected_numbers(HONEST, df, {"fast": "20"})
        pos, _ = codegen.run_code(HONEST, df, [{"fast": "20"}])
        r = run_backtest(df, pos[0])
        self.assertEqual(exp, {"final_balance": round(r["final_balance"], 2), "closed_trades": r["n_trades"],
                               "max_drawdown_pct": round(r["max_drawdown"], 2)})

    def test_untestable_skips_the_backtest(self):
        rules = {**RULES, "testable": False, "untestable_reason": "Buy when it feels strong."}
        with mock.patch.object(skeptic.llm, "_retry", return_value=SkepticTests.carbon(None, "Lucky")):
            record, trades = birth.backtest_and_judge(rules, lambda s, d="": None)
        self.assertEqual(record["verdict"], "Untestable")
        self.assertIsNone(record["results"])
        self.assertIsNone(trades)


if __name__ == "__main__":
    unittest.main()
