"""TUI (Text User Interface) for JLCImport using Textual."""

from __future__ import annotations

import argparse
import os
import sys

# Ensure the kicad_jlcimport package is importable when running as
# `python -m tui` from the project directory.
_parent_of_project = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _parent_of_project not in sys.path:
    sys.path.insert(0, _parent_of_project)


def main():
    from .app import JLCImportTUI

    parser = argparse.ArgumentParser(
        description="JLCImport TUI - interactive terminal interface for JLCPCB component import"
    )
    parser.add_argument(
        "-p",
        "--project",
        help="KiCad project directory (where .kicad_pro file is)",
        default="",
    )
    args = parser.parse_args()

    project_dir = args.project
    if project_dir:
        project_dir = os.path.abspath(project_dir)

    app = JLCImportTUI(project_dir=project_dir)
    app.run()
