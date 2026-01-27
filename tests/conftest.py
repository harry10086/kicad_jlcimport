"""Shared test fixtures for JLCImport tests."""

import os
import sys

# Add the src directory so we can import the package as 'kicad_jlcimport'
_repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_src_dir = os.path.join(_repo_dir, "src")
sys.path.insert(0, _src_dir)
