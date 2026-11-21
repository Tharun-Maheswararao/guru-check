"""Library card numbers: compound average yearly return."""

import unittest

from backend.api.server import _card, annual_return_pct


def npc(final, start="2015-01-01", end="2025-01-01"):
    return {"npc_id": "x", "name": "X", "results": {"final_balance": final}, "tested": {"start": start, "end": end}}


class CardTests(unittest.TestCase):
    def test_doubling_in_ten_years_is_about_7_percent_a_year(self):
        self.assertAlmostEqual(annual_return_pct(npc(20000)), 7.2, places=1)

    def test_losses_and_wipeouts(self):
        self.assertAlmostEqual(annual_return_pct(npc(5000)), -6.7, places=1)
        self.assertEqual(annual_return_pct(npc(0)), -100.0)

    def test_untestable_has_no_return(self):
        card = _card({"npc_id": "u", "name": "U", "results": None})
        self.assertIsNone(card["annual_return_pct"])
        self.assertIsNone(card["return_pct"])

    def test_card_keeps_total_and_years(self):
        card = _card(npc(54352.96, "2015-07-20", "2026-11-21"))
        self.assertEqual(card["return_pct"], 443.5)
        self.assertEqual(card["annual_return_pct"], 16.1)
        self.assertEqual(card["years"], 11.3)


if __name__ == "__main__":
    unittest.main()
