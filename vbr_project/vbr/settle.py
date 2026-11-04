"""Pure settlement logic (no database access)."""
from .constants import BET_TYPES, STAKE_UNIT


class GameError(Exception):
    """Invalid user action (bad stake, bad selection, race already revealed...)."""


def canonical_selection(bet_type, boats):
    """Return the canonical selection string, e.g. [3, 1, 2] -> '3-1-2' (trifecta)
    or '1-2-3' (trio).  Unordered types are sorted."""
    if bet_type not in BET_TYPES:
        raise GameError(f"unknown bet type: {bet_type}")
    n, ordered = BET_TYPES[bet_type]
    boats = [int(b) for b in boats]
    if len(boats) != n or len(set(boats)) != n or not all(1 <= b <= 6 for b in boats):
        raise GameError(f"{bet_type} needs {n} different boats numbered 1-6")
    if not ordered:
        boats.sort()
    return "-".join(map(str, boats))


def validate_stake(stake):
    if not isinstance(stake, int) or stake < STAKE_UNIT or stake % STAKE_UNIT:
        raise GameError(f"stake must be a multiple of {STAKE_UNIT}")


def settle_bet(bet_type, selection, stake, payouts, refund_boats=frozenset()):
    """Return (status, points_returned).

    payouts: {(bet_type, combo): amount_per_100_points}
    refund_boats: boats whose tickets are refunded (see constants.REFUND_FINISH_CODES)
    """
    boats = {int(b) for b in selection.split("-")}
    if boats & set(refund_boats):
        return "refunded", stake
    amount = payouts.get((bet_type, selection))
    if amount:
        return "won", stake // 100 * amount
    return "lost", 0
