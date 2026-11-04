"""Parser/importer for the race-results file ("K" file, 競走成績).

Layout was inferred from sample data (no official layout page available), so
anything that does not match a known pattern is recorded in `notes` / anomalies
instead of being guessed at.
"""
import re

from ..constants import K_BET_NAMES, VENUES
from ..db import upsert_race
from ..textutil import clean_name, nfkc, read_lines

RE_BGN = re.compile(r"^(\d{2})KBGN\s*$")
RE_END = re.compile(r"^(\d{2})KEND\s*$")
RE_DATE = re.compile(r"(\d{4})/\s*(\d{1,2})/\s*(\d{1,2})")
RE_RACE = re.compile(r"^\s+(\d{1,2})R\s+(.+?)\s+H(\d+)m\s*(.*)$")
RE_WEATHER = re.compile(r"^(\S+)\s+風\s+(\S*?)\s*(\d+)m\s+波\s+(\d+)cm")
RE_ROW = re.compile(r"^\s{2}(\S{1,2})\s+([1-6])\s+(\d{4})\s+(.+?)\s+(\d{1,2})\s+(\d{1,3})\s+(.*)$")
RE_BET = re.compile(r"^\s+(単勝|複勝|2連単|2連複|拡連複|3連単|3連複)\s+(.*)$")
RE_CONT = re.compile(r"^\s+(\d(?:-\d){0,2})\s+\d+")
RE_PAIR = re.compile(r"(\d(?:-\d){0,2})\s+(\d+)(?:\s+人気\s+(\d+))?")
RE_TIME = re.compile(r"^(\d)\.(\d{2})\.(\d)$")
RE_ST = re.compile(r"^([A-Z]?)(\d?\.\d+)$")


def _parse_row(m):
    finish, boat, reg, _name, motor, boat_no, rest = m.groups()
    t = rest.split()
    exhibition = course = st = flag = race_time = None
    if t and t[0] != "K":  # "K" rows (absent) carry no measurements
        if re.fullmatch(r"\d\.\d{2}", t[0]):
            exhibition = float(t[0])
        if len(t) > 1 and t[1].isdigit():
            course = int(t[1])
        ms = RE_ST.match(t[2]) if len(t) > 2 else None
        if ms:
            flag, st = ms.group(1) or None, float(ms.group(2))
        mt = RE_TIME.match(t[3]) if len(t) > 3 else None
        if mt:
            race_time = int(mt.group(1)) * 60 + int(mt.group(2)) + int(mt.group(3)) / 10
    return {
        "finish": finish, "finish_pos": int(finish) if finish.isdigit() else None,
        "boat": int(boat), "reg_no": int(reg), "motor_no": int(motor),
        "boat_no": int(boat_no), "exhibition": exhibition, "course": course,
        "start_timing": st, "start_flag": flag, "race_time": race_time,
    }


def parse_k(lines):
    """Return (races, anomalies).  Each race is a dict (see keys below)."""
    races, anomalies = [], []
    venue = date = race = None
    venue_name = None

    def flush():
        nonlocal race
        if race:
            races.append(race)
        race = None

    for n, line in enumerate(lines, 1):
        m = RE_BGN.match(line)
        if m:
            flush()
            venue, date, venue_name = int(m.group(1)), None, None
            continue
        if RE_END.match(line):
            flush()
            venue = None
            continue
        if venue is None:
            continue
        if race is None:
            if venue_name is None and "［成績］" in line:
                venue_name = clean_name(line.split("［成績］")[0])
                if VENUES.get(venue) != venue_name:
                    anomalies.append(f"line {n}: venue {venue} named {venue_name!r}, "
                                     f"expected {VENUES.get(venue)!r}")
            md = RE_DATE.search(line)
            if date is None and md:
                date = "%04d-%02d-%02d" % tuple(int(x) for x in md.groups())
        m = RE_RACE.match(line)
        if m:
            flush()
            race = {"race_date": date, "venue_code": venue, "race_no": int(m.group(1)),
                    "title": clean_name(m.group(2)), "distance": int(m.group(3)),
                    "weather": None, "wind_dir": None, "wind_speed": None,
                    "wave_cm": None, "technique": None, "rows": [], "payouts": [],
                    "notes": []}
            mw = RE_WEATHER.match(m.group(4).strip())
            if mw:
                race.update(weather=clean_name(mw.group(1)), wind_dir=clean_name(mw.group(2)),
                            wind_speed=int(mw.group(3)), wave_cm=int(mw.group(4)))
            else:
                race["notes"].append(f"weather unparsed: {m.group(4).strip()!r}")
            last_bet = None
            continue
        if race is None or not line.strip():
            continue
        if "ﾚｰｽﾀｲﾑ" in line:
            race["technique"] = clean_name(line.split("ﾚｰｽﾀｲﾑ", 1)[1]) or None
            continue
        if set(line.strip()) == {"-"}:
            continue
        mr = RE_ROW.match(line)
        if mr:
            race["rows"].append(_parse_row(mr))
            continue
        norm = nfkc(line)
        mb = RE_BET.match(norm)
        if mb:
            last_bet = K_BET_NAMES[mb.group(1)]
            body = mb.group(2)
        elif last_bet and RE_CONT.match(norm):
            body = norm.strip()
        else:
            race["notes"].append(norm.strip())
            continue
        for combo, amount, pop in RE_PAIR.findall(body):
            race["payouts"].append({"bet_type": last_bet, "combo": combo,
                                    "amount": int(amount), "popularity": int(pop) if pop else None})
    flush()
    return races, anomalies


def import_k(conn, path):
    races, anomalies = parse_k(read_lines(path))
    report = {"kind": "K", "races": 0, "results": 0, "payouts": 0, "anomalies": anomalies}
    for r in races:
        key = (r["race_date"], r["venue_code"], r["race_no"])
        if r["race_date"] is None:
            anomalies.append(f"race {key}: no date")
            continue
        notes = "\n".join(r["notes"]) or None
        if notes:
            anomalies.append(f"race {key}: unrecognised lines: {r['notes']}")
        if len(r["rows"]) != 6:
            anomalies.append(f"race {key}: {len(r['rows'])} result rows (expected 6)")
        upsert_race(conn, *key, title=r["title"], distance=r["distance"],
                    weather=r["weather"], wind_dir=r["wind_dir"], wind_speed=r["wind_speed"],
                    wave_cm=r["wave_cm"], technique=r["technique"], notes=notes)
        conn.execute("DELETE FROM results WHERE race_date=? AND venue_code=? AND race_no=?", key)
        conn.execute("DELETE FROM payouts WHERE race_date=? AND venue_code=? AND race_no=?", key)
        for row in r["rows"]:
            conn.execute(
                "INSERT INTO results(race_date,venue_code,race_no,boat,finish,finish_pos,reg_no,"
                "motor_no,boat_no,exhibition,course,start_timing,start_flag,race_time) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (*key, row["boat"], row["finish"], row["finish_pos"], row["reg_no"],
                 row["motor_no"], row["boat_no"], row["exhibition"], row["course"],
                 row["start_timing"], row["start_flag"], row["race_time"]))
        for p in r["payouts"]:
            conn.execute("INSERT OR REPLACE INTO payouts VALUES(?,?,?,?,?,?,?)",
                         (*key, p["bet_type"], p["combo"], p["amount"], p["popularity"]))
        report["races"] += 1
        report["results"] += len(r["rows"])
        report["payouts"] += len(r["payouts"])
    conn.commit()
    return report
