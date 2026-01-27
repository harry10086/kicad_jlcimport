"""TUI (Text User Interface) for JLCImport using Textual."""

from __future__ import annotations

import argparse
import os


def main():
    from .app import JLCImportTUI

    parser = argparse.ArgumentParser(
        prog="jlcimport-tui",
        description="JLCImport TUI - interactive terminal interface for JLCPCB component import",
    )
    parser.add_argument(
        "-p",
        "--project",
        help="KiCad project directory (where .kicad_pro file is)",
        default="",
    )
    parser.add_argument(
        "--kicad-version",
        type=int,
        choices=[8, 9],
        default=None,
        help="Target KiCad version (default: 9)",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Skip TLS certificate verification (use when behind an intercepting proxy)",
    )
    args = parser.parse_args()

    if args.insecure:
        from kicad_jlcimport.easyeda import api

        api.allow_unverified_ssl()

    project_dir = args.project
    if project_dir:
        project_dir = os.path.abspath(project_dir)

    app = JLCImportTUI(project_dir=project_dir, kicad_version=args.kicad_version)
    app.run()
