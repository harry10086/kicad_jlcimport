"""Shared test fixtures for JLCImport tests."""

import os
import sys

# Add the parent directory so we can import the package as 'JLCImport'
_pkg_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_parent_dir = os.path.dirname(_pkg_dir)
sys.path.insert(0, _parent_dir)
