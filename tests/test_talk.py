"""Offline NPC talk: answers must follow the question, come from saved facts, and not repeat."""

import os
import unittest
from unittest import mock

from backend.api import talk

RECORD = {
    "name": "Test Tess", "archetype": "The Tester", "verdict": "Lucky", "personality": "calm",
    "verdict_reason": "Beats only 20% of random traders.", "market": {"stated": "BTC", "tested_on": "BTC-USD"},
    "source_videos": [{"title": "Test video"}],
    "rules_timeline": [{"kind": "entry", "rule": "buy the dip", "timestamp_s": 61}],
    "results": {"final_balance": 7774.43, "max_drawdown": -33.3, "win_rate": 30.0, "n_trades": 11,
                "random_percentile": 19.7, "share_random_better": 80.3, "hold_final": 2142857.5},
    "claim_checks": [{"claim": "never loses", "timestamp_s": 5, "status": "contradicted", "note": "It lost money."}],
}
TRADES = {"dates": ["2022-01-01", "2022-12-31"], "equity": [10000, 9000], "trades": [],
          "pain_moment": {"date": "2022-06-18", "drawdown_pct": -33.3, "losing_streak": 4}}


class OfflineTalkTests(unittest.TestCase):
    def ask(self, q, history=None):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            return talk.talk(RECORD, TRADES, q, history)

    def test_offline_is_reported(self):
        self.assertEqual(self.ask("hello")["offline"], "no_key")

    def test_answers_follow_the_question(self):
        self.assertIn("Test Tess", self.ask("hello")["answer"])
        self.assertIn("-10.0%", self.ask("how did you do in 2022?")["answer"])
        self.assertIn("2022-06-18", self.ask("what was your worst moment?")["answer"])
        self.assertIn("Lucky", self.ask("is your strategy real?")["answer"])
        self.assertIn("80.3%", self.ask("did you beat the random traders?")["answer"])
        self.assertIn("never loses", self.ask("what did the guru claim?")["answer"])
        self.assertIn("buy the dip", self.ask("what are your rules?")["answer"])
        self.assertIn("11 trades", self.ask("how many trades?")["answer"])

    def test_word_starts_only(self):
        self.assertNotIn("Test Tess, The Tester", self.ask("which year was best?")["answer"])  # not a greeting
        self.assertNotIn("worst moment", self.ask("do you close positions?")["answer"])  # "close" isn't "lose"

    def test_unplaced_questions_do_not_repeat(self):
        history, answers = [], []
        for _ in range(4):
            a = self.ask("what the hell are you talking about", history)["answer"]
            answers.append(a)
            history += [{"role": "user", "text": "q"}, {"role": "npc", "text": a}]
        self.assertEqual(len(set(answers)), 4)

    def test_gemini_failure_falls_back_and_says_so(self):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "x"}), \
             mock.patch.object(talk, "route_question", return_value=None), \
             mock.patch.object(talk, "answer", side_effect=RuntimeError("down")):
            out = talk.talk(RECORD, TRADES, "is your strategy real?")
        self.assertEqual(out["offline"], "gemini_error")
        self.assertIn("Lucky", out["answer"])


if __name__ == "__main__":
    unittest.main()
