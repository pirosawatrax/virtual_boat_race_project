"""Integration tests against real sample files (not bundled with the project).

Set VBR_SAMPLE_DIR to a folder containing K261001.TXT, B261001.TXT, fan2604.txt.
"""
import os
import unittest
from pathlib import Path

from vbr.db import connect
from vbr.importers import detect_kind, import_file

DIR = Path(os.environ.get("VBR_SAMPLE_DIR", "/mnt/user-data/uploads"))
FILES = ["fan2604.txt", "B261001.TXT", "K261001.TXT"]


@unittest.skipUnless(all((DIR / f).exists() for f in FILES), "sample files not found")
class ImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = connect(":memory:")
        cls.reports = [import_file(cls.c, DIR / f) for f in FILES]

    def q(self, sql):
        return [tuple(r) for r in self.c.execute(sql)]

    def test_detect_and_no_anomalies(self):
        self.assertEqual([detect_kind(DIR / f) for f in FILES], ["fan", "B", "K"])
        for r in self.reports:
            self.assertEqual(r["anomalies"], [])

    def test_counts(self):
        self.assertEqual(self.q("SELECT COUNT(*) FROM races"), [(168,)])
        self.assertEqual(self.q("SELECT COUNT(*) FROM entries"), [(1008,)])
        self.assertEqual(self.q("SELECT COUNT(*) FROM results"), [(1008,)])
        self.assertEqual(self.q("SELECT COUNT(*) FROM racer_course_stats"), [(1643 * 6,)])

    def test_b_and_k_agree(self):
        self.assertEqual(self.q(
            "SELECT COUNT(*) FROM entries e JOIN results r USING(race_date,venue_code,race_no,boat)"
            " WHERE e.reg_no<>r.reg_no OR e.motor_no<>r.motor_no OR e.boat_no<>r.boat_no"), [(0,)])
        self.assertEqual(self.q("SELECT COUNT(*) FROM entries e LEFT JOIN racers x USING(reg_no) "
                                "WHERE x.reg_no IS NULL"), [(0,)])

    def test_payouts_match_finish_order(self):
        for key in self.q("SELECT race_date,venue_code,race_no FROM races"):
            order = [str(r[0]) for r in self.c.execute(
                "SELECT boat FROM results WHERE race_date=? AND venue_code=? AND race_no=? "
                "AND finish_pos IS NOT NULL ORDER BY finish_pos", key)]
            pay = {}
            for t, combo in self.c.execute("SELECT bet_type, combo FROM payouts WHERE "
                                           "race_date=? AND venue_code=? AND race_no=?", key):
                pay.setdefault(t, []).append(combo)
            self.assertEqual(pay["win"], [order[0]], key)
            self.assertEqual(pay["trifecta"], ["-".join(order[:3])], key)
            self.assertEqual(pay["trio"], ["-".join(sorted(order[:3]))], key)

    def test_reimport_is_idempotent(self):
        before = self.q("SELECT COUNT(*) FROM payouts")
        import_file(self.c, DIR / "K261001.TXT")
        self.assertEqual(self.q("SELECT COUNT(*) FROM payouts"), before)

    def test_fan_spot_check(self):
        row = self.q("SELECT name, branch, class, win_rate FROM racers JOIN racer_periods "
                     "USING(reg_no) WHERE reg_no=2538")
        self.assertEqual(row, [("高橋二朗", "東京", "B1", 3.51)])


if __name__ == "__main__":
    unittest.main()
