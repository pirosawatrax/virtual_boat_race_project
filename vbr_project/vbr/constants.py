"""Static tables shared by importers and game logic."""

# Official venue codes (01-24).  Importers cross-check the venue name found in
# the data files against this table and report mismatches instead of guessing.
VENUES = {
    1: "桐生", 2: "戸田", 3: "江戸川", 4: "平和島", 5: "多摩川", 6: "浜名湖",
    7: "蒲郡", 8: "常滑", 9: "津", 10: "三国", 11: "びわこ", 12: "住之江",
    13: "尼崎", 14: "鳴門", 15: "丸亀", 16: "児島", 17: "宮島", 18: "徳山",
    19: "下関", 20: "若松", 21: "芦屋", 22: "福岡", 23: "唐津", 24: "大村",
}

# bet type -> (number of boats in the selection, order matters)
BET_TYPES = {
    "win": (1, False),
    "place": (1, False),
    "exacta": (2, True),
    "quinella": (2, False),
    "wide": (2, False),
    "trifecta": (3, True),
    "trio": (3, False),
}

# Names used in the K file ("競走成績") after NFKC normalisation.
K_BET_NAMES = {
    "単勝": "win", "複勝": "place", "2連単": "exacta", "2連複": "quinella",
    "拡連複": "wide", "3連単": "trifecta", "3連複": "trio",
}

# ASSUMPTION - NOT confirmed by any data or layout we have.  The K file has no
# refund lines at all (verified on 2026-10-01: 12 races contain F/K/S codes and
# all of them still list normal payouts).  Following the usual boat-race rule
# as we understand it, tickets that include a boat with one of these finish
# codes (flying, late start, absent) are refunded.  Disqualification (S0-S2) is
# treated as an ordinary loss.  Change this set if the real rule differs.
REFUND_FINISH_CODES = {"F", "L0", "L1", "K0", "K1"}

INITIAL_POINTS = 100_000
STAKE_UNIT = 100
