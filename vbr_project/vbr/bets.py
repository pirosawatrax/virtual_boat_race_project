"""Game state: seasons, ledger, bets, settlement and statistics."""
from datetime import datetime

from .constants import INITIAL_POINTS, REFUND_FINISH_CODES
from .settle import GameError, canonical_selection, settle_bet, validate_stake


class SettlementError(GameError):
    pass


def _now():
    return datetime.now().isoformat(timespec="seconds")


def new_season(conn, initial=INITIAL_POINTS):
    cur = conn.execute("INSERT INTO seasons(started_at, initial_points) VALUES(?,?)",
                       (_now(), initial))
    sid = cur.lastrowid
    conn.execute("INSERT INTO ledger(season_id,ts,kind,amount,note) VALUES(?,?,?,?,?)",
                 (sid, _now(), "deposit", initial, "initial funds"))
    conn.commit()
    return sid


def current_season(conn):
    row = conn.execute("SELECT MAX(id) FROM seasons").fetchone()
    return row[0] if row[0] is not None else new_season(conn)


def balance(conn, season_id):
    return conn.execute("SELECT COALESCE(SUM(amount),0) FROM ledger WHERE season_id=?",
                        (season_id,)).fetchone()[0]


def is_revealed(conn, season_id, key):
    return conn.execute("SELECT 1 FROM reveals WHERE season_id=? AND race_date=? AND "
                        "venue_code=? AND race_no=?", (season_id, *key)).fetchone() is not None


def place_bet(conn, season_id, key, bet_type, boats, stake):
    validate_stake(stake)
    selection = canonical_selection(bet_type, boats)
    if not conn.execute("SELECT 1 FROM races WHERE race_date=? AND venue_code=? AND race_no=?",
                        key).fetchone():
        raise GameError("race not found")
    if is_revealed(conn, season_id, key):
        raise GameError("this race has already been revealed")
    if balance(conn, season_id) < stake:
        raise GameError("insufficient balance")
    cur = conn.execute(
        "INSERT INTO bets(season_id,race_date,venue_code,race_no,bet_type,selection,stake,placed_at)"
        " VALUES(?,?,?,?,?,?,?,?)", (season_id, *key, bet_type, selection, stake, _now()))
    conn.execute("INSERT INTO ledger(season_id,ts,kind,amount,bet_id) VALUES(?,?,?,?,?)",
                 (season_id, _now(), "bet", -stake, cur.lastrowid))
    conn.commit()
    return cur.lastrowid


def settle_race(conn, season_id, key):
    """Reveal a race and settle all open bets on it.  Returns the bet outcomes."""
    results = conn.execute("SELECT boat, finish FROM results WHERE race_date=? AND venue_code=? "
                           "AND race_no=?", key).fetchall()
    payouts = {(r["bet_type"], r["combo"]): r["amount"] for r in conn.execute(
        "SELECT bet_type, combo, amount FROM payouts WHERE race_date=? AND venue_code=? "
        "AND race_no=?", key)}
    if len(results) != 6 or not payouts:
        raise SettlementError("result data for this race is missing or incomplete; "
                              "import the matching results file (K) first")
    refund_boats = {r["boat"] for r in results if r["finish"] in REFUND_FINISH_CODES}
    outcomes = []
    for bet in conn.execute("SELECT * FROM bets WHERE season_id=? AND status='open' AND "
                            "race_date=? AND venue_code=? AND race_no=?", (season_id, *key)).fetchall():
        status, back = settle_bet(bet["bet_type"], bet["selection"], bet["stake"], payouts,
                                  refund_boats)
        conn.execute("UPDATE bets SET status=?, payout=?, settled_at=? WHERE id=?",
                     (status, back, _now(), bet["id"]))
        if back:
            conn.execute("INSERT INTO ledger(season_id,ts,kind,amount,bet_id) VALUES(?,?,?,?,?)",
                         (season_id, _now(), "payout" if status == "won" else "refund",
                          back, bet["id"]))
        outcomes.append({"bet_id": bet["id"], "bet_type": bet["bet_type"],
                         "selection": bet["selection"], "stake": bet["stake"],
                         "status": status, "payout": back})
    conn.execute("INSERT OR IGNORE INTO reveals VALUES(?,?,?,?)", (season_id, *key))
    conn.commit()
    return outcomes


def _group(conn, season_id, expr):
    rows = conn.execute(
        f"SELECT {expr} AS k, COUNT(*) AS n, SUM(status='won') AS wins, SUM(stake) AS stake, "
        "SUM(payout) AS payout FROM bets WHERE season_id=? AND status IN ('won','lost') "
        "GROUP BY k ORDER BY k", (season_id,)).fetchall()
    return [_summ(r["k"], r["n"], r["wins"], r["stake"], r["payout"]) for r in rows]


def _summ(k, n, wins, stake, payout):
    return {"key": k, "bets": n, "wins": wins or 0, "stake": stake or 0, "payout": payout or 0,
            "hit_rate": (wins or 0) / n * 100 if n else 0.0,
            "recovery_rate": (payout or 0) / stake * 100 if stake else 0.0}


def stats(conn, season_id):
    """Recovery rate = payouts / stakes x 100.  Refunded bets are excluded from
    both sides (the stake simply comes back)."""
    tot = conn.execute(
        "SELECT COUNT(*) n, SUM(status='won') w, SUM(stake) s, SUM(payout) p FROM bets "
        "WHERE season_id=? AND status IN ('won','lost')", (season_id,)).fetchone()
    summary = _summ("all", tot["n"], tot["w"], tot["s"], tot["p"])
    summary["profit"] = summary["payout"] - summary["stake"]
    summary["open_bets"] = conn.execute(
        "SELECT COUNT(*) FROM bets WHERE season_id=? AND status='open'", (season_id,)).fetchone()[0]
    summary["refunded_bets"] = conn.execute(
        "SELECT COUNT(*) FROM bets WHERE season_id=? AND status='refunded'", (season_id,)).fetchone()[0]
    summary["balance"] = balance(conn, season_id)
    summary["by_type"] = _group(conn, season_id, "bet_type")
    summary["by_venue"] = _group(conn, season_id, "venue_code")
    summary["by_month"] = _group(conn, season_id, "substr(race_date,1,7)")
    return summary
