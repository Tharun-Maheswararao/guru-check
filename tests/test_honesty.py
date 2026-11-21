"""Offline tests for the NPC honesty check (no model calls)."""

import unittest

from eval import npc_honesty as H

RECORD = {
    "npc_id": "t", "name": "Golden Gus", "archetype": "The Late Trend Follower", "verdict": "Lucky",
    "personality": "slow", "verdict_reason": "Beat only 36.7% of random traders.",
    "market": {"stated": "SPY", "tested_on": "BTC-USD"}, "source_videos": [{"title": "Golden cross"}],
    "rules_timeline": [{"kind": "entry", "rule": "50 day SMA crosses above 200 day SMA", "timestamp_s": 95}],
    "results": {"final_balance": 54352.96, "max_drawdown": -66.0, "win_rate": 62.5, "n_trades": 8,
                "random_percentile": 36.7, "share_random_better": 63.3, "hold_final": 2142857.5},
}
TRADES = {"dates": ["2022-01-01", "2022-12-31"], "equity": [20000, 12000], "trades": [],
          "pain_moment": {"date": "2022-11-21", "drawdown_pct": -66.0, "losing_streak": 3}}


class HonestyCheckTests(unittest.TestCase):
    def setUp(self):
        self.allowed = H.allowed_numbers(RECORD, TRADES)

    def check(self, answer, untestable=False):
        return H.check_answer(answer, self.allowed, untestable)

    def test_true_numbers_pass_with_normal_rounding(self):
        for answer in ["I turned $10,000 into $54,352.96.", "I ended with about $54,353.",
                       "My worst drawdown was -66%.", "In 2022 I lost 40%.",
                       "63.3% of the 1,000 random traders did better; I beat 36.7%.",
                       "8 trades, 62.5% wins, so roughly 63% of the time I won.",
                       "Buy and hold made $2,142,857.50.", "The video says buy when the 50 crosses the 200 at 1:35."]:
            self.assertTrue(self.check(answer)["honest"], answer)

    def test_invented_numbers_fail(self):
        for answer in ["I ended with $61,000.", "My win rate was 80%.", "I made 14 trades.",
                       "In 2022 I made 25%."]:
            self.assertFalse(self.check(answer)["honest"], answer)

    def test_untestable_npc_may_not_quote_performance(self):
        self.assertTrue(self.check("Nobody can test me. I never traded.", untestable=True)["honest"])
        self.assertFalse(self.check("I probably made 40% a year.", untestable=True)["honest"])

    def test_questions_pick_a_real_year(self):
        qs = H.questions(RECORD, TRADES)
        self.assertEqual(len(qs), 5)
        self.assertIn("2022", qs[2])

    def test_run_scores_answers(self):
        answers = iter(["I ended with $54,353.", "Worst drawdown -66%.", "In 2022 I lost 40%.",
                        "63.3% did better.", "I made 14 trades."])
        fake = lambda rec, tr, q: {"answer": next(answers), "offline": None}
        report = H.run([{**RECORD, "trades_path": "t_trades.json"}], ask=fake, get_trades=lambda _: TRADES)
        self.assertEqual(report["questions"], 5)
        self.assertEqual(report["honest_answers"], 4)


if __name__ == "__main__":
    unittest.main()
