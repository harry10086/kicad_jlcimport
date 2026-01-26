"""KiCad ActionPlugin subclass for JLCImport."""

import pcbnew

from .dialog import JLCImportDialog
from .kicad_version import detect_kicad_version_from_pcbnew


class JLCImportPlugin(pcbnew.ActionPlugin):
    def defaults(self):
        self.name = "JLCImport"
        self.category = "Import"
        self.description = "Import symbols, footprints, and 3D models from LCSC/EasyEDA"
        self.show_toolbar_button = True
        self.icon_file_name = ""

    def Run(self):
        board = pcbnew.GetBoard()
        kicad_version = detect_kicad_version_from_pcbnew()
        dlg = JLCImportDialog(None, board, kicad_version=kicad_version)
        dlg.ShowModal()
        dlg.Destroy()
