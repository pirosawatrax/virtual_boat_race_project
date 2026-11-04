"""All user-facing strings live here so another language can be added later."""

LANG = "en"

TEXT = {
    "en": {
        "title": "=== VIRTUAL BOAT RACE ===  (virtual points only, no real money)",
        "menu": ["Import data files", "Race card", "Place a bet",
                 "Reveal result & settle", "Balance & ledger", "Statistics",
                 "Bet history", "Start a new season (reset)"],
        "quit": "Quit",
        "choose": "Select> ",
        "balance": "Balance: {bal:,} pts (season {sid})",
        "no_races": "No races in the database. Import data files first.",
        "pick_date": "Date", "pick_venue": "Venue", "pick_race": "Race",
        "bad_input": "Invalid input.",
        "path_prompt": "File path(s), separated by spaces (blank to cancel)> ",
        "imported": "{kind}: {detail}",
        "anomaly": "  ! {msg}",
        "bet_types": "Bet types: win place exacta quinella wide trifecta trio",
        "bet_type_prompt": "Bet type> ",
        "boats_prompt": "Boats in order, e.g. 1-3-2> ",
        "stake_prompt": "Stake (multiples of 100)> ",
        "bet_placed": "Bet #{id} placed: {bet_type} {sel} x {stake:,} pts",
        "revealed": "--- Result ---",
        "outcome": "  #{bet_id} {bet_type} {selection} {stake:,} pts -> {status} (+{payout:,})",
        "no_bets_here": "  (no open bets on this race)",
        "refund_note": "Note: refunds for F/L/absent boats follow an assumed rule (see README).",
        "season_confirm": "Reset to a new season with 100,000 pts? (yes/no)> ",
        "season_started": "New season {sid} started.",
        "no_bets": "No bets yet.",
        "revealed_mark": "(revealed)",
        "stats_head": "Bets {bets} | Wins {wins} | Hit rate {hit:.1f}% | Staked {stake:,} | "
                      "Paid {payout:,} | Recovery {rec:.1f}% | Profit {profit:+,}",
        "stats_extra": "Open bets: {open_bets} | Refunded: {refunded_bets} | Balance: {balance:,}",
    }
}


def t(_key, **kw):
    v = TEXT[LANG][_key]
    return v.format(**kw) if isinstance(v, str) and kw else v
