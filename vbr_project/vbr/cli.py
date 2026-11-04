"""Terminal interface."""
import argparse
import sys
from datetime import date as _date

from . import bets
from .constants import BET_TYPES, VENUES
from .db import connect
from .importers import import_file
from .settle import GameError
from .ui_text import t
from .watcher import FolderWatcher


def ask(prompt):
    try:
        return input(prompt).strip()
    except EOFError:
        raise SystemExit(0)


def period_for(race_date):
    """(year, half) of the racer-period file that applies to a race date."""
    d = _date.fromisoformat(race_date)
    if 5 <= d.month <= 10:
        return d.year, 2
    return (d.year + 1 if d.month >= 11 else d.year), 1


def choose(label, options):
    """options: list of (value, text).  Returns value or None."""
    for i, (_, text) in enumerate(options, 1):
        print(f"  {i}) {text}")
    s = ask(f"{label}> ")
    if s.isdigit() and 1 <= int(s) <= len(options):
        return options[int(s) - 1][0]
    print(t("bad_input"))
    return None


def pick_race(conn, sid):
    dates = [r[0] for r in conn.execute("SELECT DISTINCT race_date FROM races ORDER BY 1")]
    if not dates:
        print(t("no_races"))
        return None
    print(t("pick_date"))
    d = choose(t("pick_date"), [(x, x) for x in dates])
    if d is None:
        return None
    venues = conn.execute("SELECT DISTINCT venue_code FROM races WHERE race_date=? ORDER BY 1",
                          (d,)).fetchall()
    print(t("pick_venue"))
    v = choose(t("pick_venue"), [(r[0], f"{r[0]:02d} {VENUES.get(r[0], '?')}") for r in venues])
    if v is None:
        return None
    rows = conn.execute("SELECT race_no, title, deadline FROM races WHERE race_date=? AND "
                        "venue_code=? ORDER BY race_no", (d, v)).fetchall()
    opts = []
    for r in rows:
        mark = t("revealed_mark") if bets.is_revealed(conn, sid, (d, v, r["race_no"])) else ""
        opts.append((r["race_no"], f"{r['race_no']:>2}R {r['title'] or ''} "
                                   f"closes {r['deadline'] or '--:--'} {mark}"))
    print(t("pick_race"))
    n = choose(t("pick_race"), opts)
    return None if n is None else (d, v, n)


def show_card(conn, key):
    race = conn.execute("SELECT * FROM races WHERE race_date=? AND venue_code=? AND race_no=?",
                        key).fetchone()
    print(f"\n{key[0]} {VENUES.get(key[1])} {key[2]}R  {race['title'] or ''}  "
          f"{race['distance'] or ''}m  closes {race['deadline'] or '--:--'}")
    if race["weather"]:
        print(f"Weather: {race['weather']}  wind {race['wind_dir']} {race['wind_speed']}m  "
              f"wave {race['wave_cm']}cm")
    year, half = period_for(key[0])
    rows = conn.execute(
        "SELECT e.boat, e.name, e.class, e.nat_win_rate, e.loc_win_rate, e.motor_place2, "
        "e.boat_place2, r.exhibition, c.place_rate AS own_course, c.entries AS own_n "
        "FROM entries e LEFT JOIN results r USING(race_date,venue_code,race_no,boat) "
        "LEFT JOIN racer_course_stats c ON c.reg_no=e.reg_no AND c.year=? AND c.half=? "
        "AND c.course=e.boat WHERE e.race_date=? AND e.venue_code=? AND e.race_no=? "
        "ORDER BY e.boat", (year, half, *key)).fetchall()
    if not rows:
        print("  (no race card imported for this race)")
        return
    print(f"{'#':>2} {'Name':<10} {'Cls':<3} {'NatWin':>6} {'LocWin':>6} {'Motor2':>6} "
          f"{'Boat2':>6} {'Exh':>5} {'OwnCourse2':>10}")
    for r in rows:
        own = f"{r['own_course']:.1f}%({r['own_n']})" if r["own_course"] is not None else "-"
        exh = f"{r['exhibition']:.2f}" if r["exhibition"] else "-"
        print(f"{r['boat']:>2} {r['name']:<10} {r['class']:<3} {r['nat_win_rate']:>6.2f} "
              f"{r['loc_win_rate']:>6.2f} {r['motor_place2']:>6.1f} {r['boat_place2']:>6.1f} "
              f"{exh:>5} {own:>10}")
    print("(OwnCourse2 = racer's top-2 rate when starting from the same course number, "
          f"period {year}/{half})")


def do_bet(conn, sid, key):
    print(t("bet_types"))
    bt = ask(t("bet_type_prompt")).lower()
    if bt not in BET_TYPES:
        return print(t("bad_input"))
    raw = ask(t("boats_prompt")).replace(",", "-").replace(" ", "-")
    stake = ask(t("stake_prompt"))
    try:
        boats = [int(x) for x in raw.split("-") if x]
        bid = bets.place_bet(conn, sid, key, bt, boats, int(stake))
        sel = conn.execute("SELECT selection FROM bets WHERE id=?", (bid,)).fetchone()[0]
        print(t("bet_placed", id=bid, bet_type=bt, sel=sel, stake=int(stake)))
    except (ValueError, GameError) as e:
        print(f"! {e}")


def do_settle(conn, sid, key):
    try:
        outcomes = bets.settle_race(conn, sid, key)
    except GameError as e:
        return print(f"! {e}")
    print(t("revealed"))
    rows = conn.execute(
        "SELECT r.finish, r.boat, COALESCE(e.name, x.name, '') AS name, r.start_timing, "
        "r.start_flag, r.race_time, r.course FROM results r "
        "LEFT JOIN entries e USING(race_date,venue_code,race_no,boat) "
        "LEFT JOIN racers x ON x.reg_no=r.reg_no WHERE r.race_date=? AND r.venue_code=? "
        "AND r.race_no=? ORDER BY r.finish", key).fetchall()
    tech = conn.execute("SELECT technique FROM races WHERE race_date=? AND venue_code=? AND "
                        "race_no=?", key).fetchone()[0]
    for r in rows:
        st = f"{r['start_flag'] or ''}{r['start_timing']:.2f}" if r["start_timing"] is not None else "-"
        tm = f"{int(r['race_time'] // 60)}'{r['race_time'] % 60:04.1f}" if r["race_time"] else "-"
        print(f"  {r['finish']:>3}  boat {r['boat']}  {r['name']:<10} ST {st:>6}  {tm}")
    if tech:
        print(f"  Winning technique: {tech}")
    for p in conn.execute("SELECT bet_type, combo, amount FROM payouts WHERE race_date=? AND "
                          "venue_code=? AND race_no=? ORDER BY bet_type, combo", key):
        print(f"  payout {p['bet_type']:<9} {p['combo']:<6} {p['amount']:>8,} / 100")
    if not outcomes:
        print(t("no_bets_here"))
    for o in outcomes:
        print(t("outcome", **o))
    if any(o["status"] == "refunded" for o in outcomes):
        print(t("refund_note"))


def show_ledger(conn, sid):
    print(t("balance", bal=bets.balance(conn, sid), sid=sid))
    for r in conn.execute("SELECT ts, kind, amount, bet_id FROM ledger WHERE season_id=? "
                          "ORDER BY id DESC LIMIT 15", (sid,)):
        print(f"  {r['ts']}  {r['kind']:<8} {r['amount']:>+9,}  {('bet #' + str(r['bet_id'])) if r['bet_id'] else ''}")


def show_stats(conn, sid):
    s = bets.stats(conn, sid)
    print(t("stats_head", bets=s["bets"], wins=s["wins"], hit=s["hit_rate"], stake=s["stake"],
            payout=s["payout"], rec=s["recovery_rate"], profit=s["profit"]))
    print(t("stats_extra", **s))
    for title, rows in (("By bet type", s["by_type"]), ("By venue", s["by_venue"]),
                        ("By month", s["by_month"])):
        if rows:
            print(f"{title}:")
            for r in rows:
                name = VENUES.get(r["key"], r["key"]) if isinstance(r["key"], int) else r["key"]
                print(f"  {name:<10} bets {r['bets']:>3}  hit {r['hit_rate']:5.1f}%  "
                      f"recovery {r['recovery_rate']:6.1f}%")


def show_history(conn, sid):
    rows = conn.execute("SELECT * FROM bets WHERE season_id=? ORDER BY id DESC LIMIT 30",
                        (sid,)).fetchall()
    if not rows:
        return print(t("no_bets"))
    for b in rows:
        print(f"  #{b['id']:<4} {b['race_date']} {VENUES.get(b['venue_code'])} {b['race_no']}R "
              f"{b['bet_type']:<9} {b['selection']:<6} {b['stake']:>7,}  {b['status']:<8} "
              f"+{b['payout']:,}")


def do_import(conn, paths):
    for p in paths:
        try:
            r = import_file(conn, p)
        except (OSError, ValueError) as e:
            print(f"! {p}: {e}")
            continue
        detail = ", ".join(f"{k}={v}" for k, v in r.items() if k not in ("kind", "anomalies"))
        print(t("imported", kind=r["kind"], detail=f"{detail}  <- {p}"))
        for a in r["anomalies"][:10]:
            print(t("anomaly", msg=a[:200]))
        if len(r["anomalies"]) > 10:
            print(t("anomaly", msg=f"... {len(r['anomalies']) - 10} more"))


def play(conn, db_path="vbr.sqlite3", watch_dir="data"):
    sid = bets.current_season(conn)
    key = None
    watcher = FolderWatcher(db_path, watch_dir).start() if db_path != ":memory:" else None
    try:
        while True:
            print("\n" + t("title"))
            print(t("balance", bal=bets.balance(conn, sid), sid=sid))
            for i, name in enumerate(t("menu"), 1):
                print(f" {i}) {name}")
            print(f" 0) {t('quit')}")
            c = ask(t("choose"))
            if c == "0":
                return
            if c == "1":
                do_import(conn, ask(t("path_prompt")).split())
            elif c in ("2", "3", "4"):
                key = pick_race(conn, sid)
                if key:
                    {"2": show_card, "3": lambda *a: (show_card(conn, key), do_bet(conn, sid, key)),
                     "4": lambda *a: do_settle(conn, sid, key)}[c](conn, key)
            elif c == "5":
                show_ledger(conn, sid)
            elif c == "6":
                show_stats(conn, sid)
            elif c == "7":
                show_history(conn, sid)
            elif c == "8":
                if ask(t("season_confirm")).lower() == "yes":
                    sid = bets.new_season(conn)
                    print(t("season_started", sid=sid))
            else:
                print(t("bad_input"))

    finally:
        if watcher is not None:
            watcher.stop()

def main(argv=None):
    ap = argparse.ArgumentParser(prog="vbr", description="VIRTUAL BOAT RACE (replay mode)")
    ap.add_argument("--db", default="vbr.sqlite3")
    sub = ap.add_subparsers(dest="cmd")
    imp = sub.add_parser("import", help="import K / B / fan data files")
    imp.add_argument("files", nargs="+")
    play_parser = sub.add_parser("play", help="interactive game (default)")
    play_parser.add_argument("--watch-dir", default="data",
                             help="folder monitored for new race data files (default: data)")
    args = ap.parse_args(argv)
    conn = connect(args.db)
    if args.cmd == "import":
        do_import(conn, args.files)
    else:
        play(conn, args.db, getattr(args, "watch_dir", "data"))


if __name__ == "__main__":
    sys.exit(main())
