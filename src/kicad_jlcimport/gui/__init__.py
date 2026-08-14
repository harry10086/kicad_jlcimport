"""Standalone GUI (wxPython) for JLCImport."""

from __future__ import annotations

try:
    from ..gui_entry import main
except (ImportError, ValueError):
    from gui_entry import main

__all__ = ["main"]
