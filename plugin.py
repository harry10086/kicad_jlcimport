"""KiCad ActionPlugin subclass for JLCImport."""

import pcbnew

from .dialog import JLCImportDialog


class JLCImportPlugin(pcbnew.ActionPlugin):
    def defaults(self):
        self.name = "JLCImport"
        self.category = "Import"
        self.description = "Import symbols, footprints, and 3D models from LCSC/EasyEDA"
        self.show_toolbar_button = True
        self.icon_file_name = ""

    def Run(self):
        board = pcbnew.GetBoard()
        dlg = JLCImportDialog(None, board)
        dlg.ShowModal()
        dlg.Destroy()
