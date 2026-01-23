"""TUI (Text User Interface) for JLCImport using Textual."""
from __future__ import annotations

import argparse
import os


def main():
    from .app import JLCImportTUI

    parser = argparse.ArgumentParser(
        description="JLCImport TUI - interactive terminal interface for JLCPCB component import"
    )
    parser.add_argument(
        "-p", "--project",
        help="KiCad project directory (where .kicad_pro file is)",
        default="",
    )
    args = parser.parse_args()

    project_dir = args.project
    if project_dir:
        project_dir = os.path.abspath(project_dir)

    app = JLCImportTUI(project_dir=project_dir)
    app.run()
