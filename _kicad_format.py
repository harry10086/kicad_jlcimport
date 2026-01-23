"""Shared formatting utilities for KiCad file output."""
import uuid as _uuid_mod


def gen_uuid() -> str:
    """Generate a random UUID string for KiCad elements."""
    return str(_uuid_mod.uuid4())


def fmt_float(v: float) -> str:
    """Format a float for KiCad S-expression output.

    Returns integers without decimals, otherwise up to 6 decimal places
    with trailing zeros stripped.
    """
    if v == int(v) and abs(v) < 1e10:
        return str(int(v))
    return f"{v:.6f}".rstrip("0").rstrip(".")


def escape_sexpr(s: str) -> str:
    """Escape special characters for S-expression string values."""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
