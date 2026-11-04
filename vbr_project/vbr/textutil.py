import unicodedata
from pathlib import Path


def read_lines(path):
    """Read a Shift_JIS (cp932) text file into lines (CRLF safe)."""
    text = Path(path).read_bytes().decode("cp932", errors="replace")
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def nfkc(s):
    return unicodedata.normalize("NFKC", s)


def clean_name(s):
    """Remove ASCII/full-width padding spaces from a name or label."""
    return s.replace("\u3000", "").replace(" ", "").strip()
