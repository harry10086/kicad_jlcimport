"""Shared test fixtures for JLCImport tests."""

import os
import sys

# Add the src directory so we can import the package as 'kicad_jlcimport'
_repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_src_dir = os.path.join(_repo_dir, "src")
sys.path.insert(0, _src_dir)

import pytest

@pytest.fixture(autouse=True)
def mock_importer_kicad_libraries(monkeypatch):
    import kicad_jlcimport.importer as importer
    monkeypatch.setattr(importer, "_iter_footprint_libraries", lambda *a, **k: [])
    monkeypatch.setattr(importer, "search_components", lambda *a, **k: {"total": 0, "results": []})
    monkeypatch.setattr(importer, "search_components_cn", lambda *a, **k: {"total": 0, "results": []})

