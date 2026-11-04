"""Importer for the racer period-results file ("fan" file, 416 bytes/record).

Field offsets follow the official layout page (verified against fan2604.txt).
"""
from pathlib import Path

RECORD_LEN = 416
ERA_BASE = {"S": 1925, "H": 1988, "R": 2018}


def _s(b):
    return b.decode("cp932", errors="replace").strip()


def _i(b):
    s = _s(b)
    return int(s) if s.isdigit() else None


def _div(b, d):
    v = _i(b)
    return None if v is None else v / d


def _birth(era, yymmdd):
    if era in ERA_BASE and len(yymmdd) == 6 and yymmdd.isdigit():
        return f"{ERA_BASE[era] + int(yymmdd[:2]):04d}-{yymmdd[2:4]}-{yymmdd[4:]}"
    return None


def parse_record(rec):
    g = lambda o, n: rec[o:o + n]
    clean = lambda b: _s(b).replace("\u3000", "")
    d = {
        "reg_no": _i(g(0, 4)), "name": clean(g(4, 16)), "name_kana": _s(g(20, 15)),
        "branch": clean(g(35, 4)), "class": _s(g(39, 2)),
        "birth_date": _birth(_s(g(41, 1)), _s(g(42, 6))), "gender": _i(g(48, 1)),
        "age": _i(g(49, 2)), "height": _i(g(51, 3)), "weight": _i(g(54, 2)),
        "win_rate": _div(g(58, 4), 100), "place_rate": _div(g(62, 4), 10),
        "wins": _i(g(66, 3)), "seconds": _i(g(69, 3)), "starts": _i(g(72, 3)),
        "finals": _i(g(75, 2)), "titles": _i(g(77, 2)), "avg_st": _div(g(79, 3), 100),
        "prev_class": _s(g(160, 2)), "prev2_class": _s(g(162, 2)),
        "prev3_class": _s(g(164, 2)),
        "prev_ability": _div(g(166, 4), 100), "ability": _div(g(170, 4), 100),
        "year": _i(g(174, 4)), "half": _i(g(178, 1)),
        "period_from": _s(g(179, 8)), "period_to": _s(g(187, 8)),
        "training_term": _i(g(195, 3)), "hometown": clean(g(410, 6)),
    }
    courses = []
    for c in range(6):
        o1, o2 = 82 + 13 * c, 198 + 34 * c
        row = {
            "course": c + 1, "entries": _i(g(o1, 3)), "place_rate": _div(g(o1 + 3, 4), 10),
            "avg_st": _div(g(o1 + 7, 3), 100), "avg_st_rank": _div(g(o1 + 10, 3), 100),
        }
        for k in range(6):
            row[f"p{k + 1}"] = _i(g(o2 + 3 * k, 3))
        for k, name in enumerate(["f_count", "l0", "l1", "k0", "k1", "s0", "s1", "s2"]):
            row[name] = _i(g(o2 + 18 + 2 * k, 2))
        courses.append(row)
    d["courses"] = courses
    return d


def import_fan(conn, path):
    report = {"kind": "fan", "records": 0, "anomalies": []}
    raw = Path(path).read_bytes().replace(b"\r\n", b"\n").split(b"\n")
    for n, rec in enumerate(raw, 1):
        if not rec.strip():
            continue
        if len(rec) != RECORD_LEN:
            report["anomalies"].append(f"line {n}: length {len(rec)} != {RECORD_LEN}")
            continue
        d = parse_record(rec)
        if d["reg_no"] is None or d["year"] is None or d["half"] is None:
            report["anomalies"].append(f"line {n}: missing key fields")
            continue
        conn.execute(
            "INSERT INTO racers(reg_no,name,name_kana,branch,hometown,birth_date,gender) "
            "VALUES(?,?,?,?,?,?,?) ON CONFLICT(reg_no) DO UPDATE SET name=excluded.name,"
            "name_kana=excluded.name_kana,branch=excluded.branch,hometown=excluded.hometown,"
            "birth_date=excluded.birth_date,gender=excluded.gender",
            (d["reg_no"], d["name"], d["name_kana"], d["branch"], d["hometown"],
             d["birth_date"], d["gender"]))
        pcols = ["reg_no", "year", "half", "class", "age", "height", "weight", "win_rate",
                 "place_rate", "wins", "seconds", "starts", "finals", "titles", "avg_st",
                 "prev_class", "prev2_class", "prev3_class", "prev_ability", "ability",
                 "period_from", "period_to", "training_term"]
        conn.execute(
            f"INSERT OR REPLACE INTO racer_periods({','.join(pcols)}) "
            f"VALUES({','.join('?' * len(pcols))})", [d[c] for c in pcols])
        ccols = ["entries", "place_rate", "avg_st", "avg_st_rank", "p1", "p2", "p3", "p4",
                 "p5", "p6", "f_count", "l0", "l1", "k0", "k1", "s0", "s1", "s2"]
        for row in d["courses"]:
            conn.execute(
                f"INSERT OR REPLACE INTO racer_course_stats(reg_no,year,half,course,"
                f"{','.join(ccols)}) VALUES(?,?,?,?,{','.join('?' * len(ccols))})",
                [d["reg_no"], d["year"], d["half"], row["course"]] + [row[c] for c in ccols])
        report["records"] += 1
    conn.commit()
    return report
