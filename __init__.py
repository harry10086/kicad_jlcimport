"""JLCImport - KiCad 9 LCSC Component Import Plugin."""

try:
    from .plugin import JLCImportPlugin

    JLCImportPlugin().register()
except ImportError:
    pass  # pcbnew not available (running outside KiCad)
