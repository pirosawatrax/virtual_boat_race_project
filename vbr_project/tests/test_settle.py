import unittest

from vbr import bets
from vbr.db import connect
from vbr.settle import GameError, canonical_selection, settle_bet


class SettleTests(unittest.TestCase):
    def test_canonical(self):
        self.assertEqual(canonical_selection("trifecta", [3, 1, 2]), "3-1-2")
        self.assertEqual(canonical_selection("trio", [3, 1, 2]), "1-2-3")
        self.assertEqual(canonical_selection("quinella", [6, 2]), "2-6")
        self.assertEqual(canonical_selection("exacta", [6, 2]), "6-2")
        for bad in ([1, 1], [0, 2], [1, 7], [1]):
            with self.assertRaises(GameError):
                canonical_selection("exacta", bad)

    def test_settle_bet(self):
        pay = {("trifecta", "6-2-5"): 205630, ("win", "6"): 840}
        self.assertEqual(settle_bet("trifecta", "6-2-5", 300, pay), ("won", 3 * 205630))
        self.assertEqual(settle_bet("trifecta", "6-5-2", 100, pay), ("lost", 0))
        self.assertEqual(settle_bet("win", "6", 1000, pay), ("won", 8400))
        self.assertEqual(settle_bet("win", "3", 100, pay, refund_boats={3}), ("refunded", 100))

    def test_dead_heat_two_winners(self):
        pay = {("win", "1"): 200, ("win", "2"): 200}
        self.assertEqual(settle_bet("win", "2", 100, pay)[0], "won")


class GameFlowTests(unittest.TestCase):
    def setUp(self):
        self.c = connect(":memory:")
        key = ("2026-10-01", 24, 1)
        self.key = key
        self.c.execute("INSERT INTO races(race_date,venue_code,race_no) VALUES(?,?,?)", key)
        for boat, fin in zip(range(1, 7), ["01", "02", "03", "04", "05", "F"]):
            self.c.execute("INSERT INTO results(race_date,venue_code,race_no,boat,finish) "
                           "VALUES(?,?,?,?,?)", (*key, boat, fin))
        for t, combo, amt in [("win", "1", 150), ("trifecta", "1-2-3", 700)]:
            self.c.execute("INSERT INTO payouts VALUES(?,?,?,?,?,?,NULL)", (*key, t, combo, amt))
        self.sid = bets.new_season(self.c)

    def test_win_lose_refund_and_ledger(self):
        c, sid, key = self.c, self.sid, self.key
        bets.place_bet(c, sid, key, "win", [1], 1000)          # wins 1000/100*150
        bets.place_bet(c, sid, key, "trifecta", [1, 3, 2], 500)  # loses
        bets.place_bet(c, sid, key, "win", [6], 200)            # boat 6 flew -> refund
        self.assertEqual(bets.balance(c, sid), 100000 - 1700)
        out = bets.settle_race(c, sid, key)
        self.assertEqual([o["status"] for o in out], ["won", "lost", "refunded"])
        self.assertEqual(bets.balance(c, sid), 100000 - 1700 + 1500 + 200)
        s = bets.stats(c, sid)
        self.assertEqual((s["stake"], s["payout"], s["profit"]), (1500, 1500, 0))
        self.assertAlmostEqual(s["recovery_rate"], 100.0)
        self.assertEqual(s["refunded_bets"], 1)

    def test_rules(self):
        c, sid, key = self.c, self.sid, self.key
        with self.assertRaises(GameError):
            bets.place_bet(c, sid, key, "win", [1], 150)         # not a multiple of 100
        with self.assertRaises(GameError):
            bets.place_bet(c, sid, key, "win", [1], 10_000_000)  # insufficient balance
        bets.settle_race(c, sid, key)
        with self.assertRaises(GameError):
            bets.place_bet(c, sid, key, "win", [1], 100)         # already revealed

    def test_missing_results_not_settled(self):
        key = ("2026-10-01", 24, 2)
        self.c.execute("INSERT INTO races(race_date,venue_code,race_no) VALUES(?,?,?)", key)
        with self.assertRaises(bets.SettlementError):
            bets.settle_race(self.c, self.sid, key)

    def test_new_season_resets_balance(self):
        bets.place_bet(self.c, self.sid, self.key, "win", [1], 1000)
        sid2 = bets.new_season(self.c)
        self.assertEqual(bets.balance(self.c, sid2), 100000)
        self.assertEqual(bets.current_season(self.c), sid2)


if __name__ == "__main__":
    unittest.main()
