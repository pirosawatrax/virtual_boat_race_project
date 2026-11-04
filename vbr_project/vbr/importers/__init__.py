from pathlib import Path

from .bfile import import_b
from .fan import RECORD_LEN, import_fan
from .kfile import import_k


def detect_kind(path):
    """Detect file kind from its content (not its name)."""
    raw = Path(path).read_bytes()
    head = raw[:16].decode("ascii", errors="ignore")
    if head.startswith("STARTK"):
        return "K"
    if head.startswith("STARTB"):
        return "B"
    lines = [l for l in raw.replace(b"\r\n", b"\n").split(b"\n") if l.strip()]
    if lines and all(len(l) == RECORD_LEN for l in lines[:20]):
        return "fan"
    return None


def import_file(conn, path):
    kind = detect_kind(path)
    if kind == "K":
        return import_k(conn, path)
    if kind == "B":
        return import_b(conn, path)
    if kind == "fan":
        return import_fan(conn, path)
    raise ValueError(f"unrecognised file type: {path}")
