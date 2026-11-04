"""Parser/importer for the race-program file ("B" file, 番組表).

Layout inferred from sample data; unmatched lines are reported, not guessed.
"""
import re

from ..constants import VENUES
from ..db import upsert_race
from ..textutil import clean_name, nfkc, read_lines

RE_BGN = re.compile(r"^(\d{2})BBGN\s*$")
RE_END = re.compile(r"^(\d{2})BEND\s*$")
RE_DATE = re.compile(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日")
RE_RACE = re.compile(r"^\s*(\d{1,2})R\s+(.+?)\s+H(\d+)m\s+電話投票締切予定\s*(\d{1,2}):(\d{2})")
RE_VENUE = re.compile(r"^ボートレース(.+?)\s{2,}")
# Fixed-width columns: values can touch each other (e.g. "40.00154" = motor
# place rate 40.00 + boat no 154), so separators are optional.
_W = r"([0-9]\.[0-9]{2})"          # win rate (< 10)
_P = r"([0-9]{1,3}\.[0-9]{2})"     # place rate (up to 100.00)
_I = r"([0-9]{1,3})"               # motor / boat number
RE_ROW = re.compile(
    r"^([1-6])\s([0-9]{4})([^0-9]+?)([0-9]{2})([^0-9\s]{2})([0-9]{2})([AB][12])\s+"
    + _W + r"\s*" + _P + r"\s*" + _W + r"\s*" + _P + r"\s*" + _I + r"\s*" + _P
    + r"\s*" + _I + r"\s*" + _P + r"\s*(.*)$")


def parse_b(lines):
    races, anomalies = [], []
    venue = date = race = None

    def flush():
        nonlocal race
        if race:
            races.append(race)
        race = None

    for n, line in enumerate(lines, 1):
        m = RE_BGN.match(line)
        if m:
            flush()
            venue, date = int(m.group(1)), None
            continue
        if RE_END.match(line):
            flush()
            venue = None
            continue
        if venue is None:
            continue
        norm = nfkc(line)
        if race is None:
            mv = RE_VENUE.match(line)
            if mv and VENUES.get(venue) != clean_name(mv.group(1)):
                anomalies.append(f"line {n}: venue {venue} named {clean_name(mv.group(1))!r}")
            md = RE_DATE.search(norm)
            if date is None and md:
                date = "%04d-%02d-%02d" % tuple(int(x) for x in md.groups())
        m = RE_RACE.match(norm)
        if m:
            flush()
            race = {"race_date": date, "venue_code": venue, "race_no": int(m.group(1)),
                    "title": clean_name(m.group(2)), "distance": int(m.group(3)),
                    "deadline": f"{int(m.group(4)):02d}:{m.group(5)}", "rows": [], "notes": []}
            continue
        if race is None or not line.strip():
            continue
        mr = RE_ROW.match(line)
        if mr:
            g = mr.groups()
            race["rows"].append({
                "boat": int(g[0]), "reg_no": int(g[1]), "name": clean_name(g[2]),
                "age": int(g[3]), "branch": g[4], "weight": int(g[5]), "class": g[6],
                "nat_win_rate": float(g[7]), "nat_place2": float(g[8]),
                "loc_win_rate": float(g[9]), "loc_place2": float(g[10]),
                "motor_no": int(g[11]), "motor_place2": float(g[12]),
                "boat_no": int(g[13]), "boat_place2": float(g[14]),
                "series_raw": g[15].strip() or None})
            continue
        # Column headers and rulers are expected noise; anything else is reported.
        if set(norm.strip()) <= {"-"} or norm.lstrip().startswith(("艇", "番", "N", "NO")):
            continue
        if "全国" in norm or "勝率" in norm or "選手" in norm:
            continue
        race["notes"].append(norm.strip())
    flush()
    return races, anomalies


def import_b(conn, path):
    races, anomalies = parse_b(read_lines(path))
    report = {"kind": "B", "races": 0, "entries": 0, "anomalies": anomalies}
    for r in races:
        key = (r["race_date"], r["venue_code"], r["race_no"])
        if r["race_date"] is None:
            anomalies.append(f"race {key}: no date")
            continue
        if r["notes"]:
            anomalies.append(f"race {key}: unrecognised lines: {r['notes']}")
        if len(r["rows"]) != 6:
            anomalies.append(f"race {key}: {len(r['rows'])} entries (expected 6)")
        upsert_race(conn, *key, title=r["title"], distance=r["distance"], deadline=r["deadline"])
        conn.execute("DELETE FROM entries WHERE race_date=? AND venue_code=? AND race_no=?", key)
        for e in r["rows"]:
            conn.execute(
                "INSERT INTO entries VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (*key, e["boat"], e["reg_no"], e["name"], e["age"], e["branch"], e["weight"],
                 e["class"], e["nat_win_rate"], e["nat_place2"], e["loc_win_rate"],
                 e["loc_place2"], e["motor_no"], e["motor_place2"], e["boat_no"],
                 e["boat_place2"], e["series_raw"]))
        report["races"] += 1
        report["entries"] += len(r["rows"])
    conn.commit()
    return report
