import sqlite3

from .constants import VENUES

SCHEMA = """
CREATE TABLE IF NOT EXISTS venues(code INTEGER PRIMARY KEY, name TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS racers(
  reg_no INTEGER PRIMARY KEY, name TEXT, name_kana TEXT, branch TEXT,
  hometown TEXT, birth_date TEXT, gender INTEGER);

CREATE TABLE IF NOT EXISTS racer_periods(
  reg_no INTEGER, year INTEGER, half INTEGER, class TEXT, age INTEGER,
  height INTEGER, weight INTEGER, win_rate REAL, place_rate REAL,
  wins INTEGER, seconds INTEGER, starts INTEGER, finals INTEGER, titles INTEGER,
  avg_st REAL, prev_class TEXT, prev2_class TEXT, prev3_class TEXT,
  prev_ability REAL, ability REAL, period_from TEXT, period_to TEXT,
  training_term INTEGER,
  PRIMARY KEY(reg_no, year, half));

CREATE TABLE IF NOT EXISTS racer_course_stats(
  reg_no INTEGER, year INTEGER, half INTEGER, course INTEGER,
  entries INTEGER, place_rate REAL, avg_st REAL, avg_st_rank REAL,
  p1 INTEGER, p2 INTEGER, p3 INTEGER, p4 INTEGER, p5 INTEGER, p6 INTEGER,
  f_count INTEGER, l0 INTEGER, l1 INTEGER, k0 INTEGER, k1 INTEGER,
  s0 INTEGER, s1 INTEGER, s2 INTEGER,
  PRIMARY KEY(reg_no, year, half, course));

CREATE TABLE IF NOT EXISTS races(
  race_date TEXT, venue_code INTEGER, race_no INTEGER,
  title TEXT, distance INTEGER, deadline TEXT,
  weather TEXT, wind_dir TEXT, wind_speed INTEGER, wave_cm INTEGER,
  technique TEXT, notes TEXT,
  PRIMARY KEY(race_date, venue_code, race_no));

CREATE TABLE IF NOT EXISTS entries(
  race_date TEXT, venue_code INTEGER, race_no INTEGER, boat INTEGER,
  reg_no INTEGER, name TEXT, age INTEGER, branch TEXT, weight INTEGER,
  class TEXT, nat_win_rate REAL, nat_place2 REAL, loc_win_rate REAL,
  loc_place2 REAL, motor_no INTEGER, motor_place2 REAL, boat_no INTEGER,
  boat_place2 REAL, series_raw TEXT,
  PRIMARY KEY(race_date, venue_code, race_no, boat));

CREATE TABLE IF NOT EXISTS results(
  race_date TEXT, venue_code INTEGER, race_no INTEGER, boat INTEGER,
  finish TEXT, finish_pos INTEGER, reg_no INTEGER, motor_no INTEGER,
  boat_no INTEGER, exhibition REAL, course INTEGER, start_timing REAL,
  start_flag TEXT, race_time REAL,
  PRIMARY KEY(race_date, venue_code, race_no, boat));

CREATE TABLE IF NOT EXISTS payouts(
  race_date TEXT, venue_code INTEGER, race_no INTEGER,
  bet_type TEXT, combo TEXT, amount INTEGER, popularity INTEGER,
  PRIMARY KEY(race_date, venue_code, race_no, bet_type, combo));

CREATE TABLE IF NOT EXISTS seasons(
  id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT, initial_points INTEGER);

CREATE TABLE IF NOT EXISTS bets(
  id INTEGER PRIMARY KEY AUTOINCREMENT, season_id INTEGER NOT NULL,
  race_date TEXT, venue_code INTEGER, race_no INTEGER,
  bet_type TEXT, selection TEXT,
  stake INTEGER CHECK(stake > 0 AND stake % 100 = 0),
  placed_at TEXT,
  status TEXT DEFAULT 'open' CHECK(status IN ('open','won','lost','refunded')),
  payout INTEGER DEFAULT 0, settled_at TEXT);

CREATE TABLE IF NOT EXISTS ledger(
  id INTEGER PRIMARY KEY AUTOINCREMENT, season_id INTEGER NOT NULL, ts TEXT,
  kind TEXT CHECK(kind IN ('deposit','bet','payout','refund')),
  amount INTEGER NOT NULL, bet_id INTEGER, note TEXT);

CREATE TABLE IF NOT EXISTS reveals(
  season_id INTEGER, race_date TEXT, venue_code INTEGER, race_no INTEGER,
  PRIMARY KEY(season_id, race_date, venue_code, race_no));

CREATE TABLE IF NOT EXISTS imported_files(
  path TEXT PRIMARY KEY, size INTEGER NOT NULL, mtime_ns INTEGER NOT NULL,
  imported_at TEXT NOT NULL);
"""


def connect(path=":memory:"):
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    conn.executemany("INSERT OR IGNORE INTO venues(code, name) VALUES(?, ?)",
                     VENUES.items())
    conn.commit()
    return conn


def upsert_race(conn, race_date, venue_code, race_no, **fields):
    """Insert or update a race; None values never overwrite existing data."""
    cols = list(fields)
    sql = (f"INSERT INTO races(race_date, venue_code, race_no, {', '.join(cols)}) "
           f"VALUES(?, ?, ?, {', '.join('?' * len(cols))}) "
           "ON CONFLICT(race_date, venue_code, race_no) DO UPDATE SET "
           + ", ".join(f"{c}=COALESCE(excluded.{c}, races.{c})" for c in cols))
    conn.execute(sql, (race_date, venue_code, race_no, *fields.values()))
