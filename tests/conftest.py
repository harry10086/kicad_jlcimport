"""Shared test fixtures for JLCImport tests."""
import importlib
import os
import sys

# Add the parent directory so we can import the package
_pkg_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_parent_dir = os.path.dirname(_pkg_dir)
sys.path.insert(0, _parent_dir)

# The package directory is 'kicad_jlcimport' but code references 'JLCImport'
import kicad_jlcimport
sys.modules['JLCImport'] = kicad_jlcimport
