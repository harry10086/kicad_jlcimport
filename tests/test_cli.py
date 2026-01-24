from types import SimpleNamespace


def test_cli_import_project_writes_kicad_library(tmp_path, monkeypatch, capsys):
    import kicad_jlcimport.cli as cli

    fake_comp = {
        "title": "TestPart",
        "prefix": "U",
        "description": "desc",
        "datasheet": "https://example.invalid/ds",
        "manufacturer": "ACME",
        "manufacturer_part": "MPN",
        "footprint_data": {"dataStr": {"shape": ""}},
        "fp_origin_x": 0,
        "fp_origin_y": 0,
        "symbol_data_list": [{"dataStr": {"shape": ""}}],
        "sym_origin_x": 0,
        "sym_origin_y": 0,
    }

    class _Pad:
        layer = "1"

    class _Footprint:
        pads = [_Pad()]
        tracks = []
        model = None

    class _Symbol:
        pins = [object(), object()]
        rectangles = []

    monkeypatch.setattr(cli, "fetch_full_component", lambda _lcsc: fake_comp)
    monkeypatch.setattr(cli, "parse_footprint_shapes", lambda *_a, **_k: _Footprint())
    monkeypatch.setattr(cli, "parse_symbol_shapes", lambda *_a, **_k: _Symbol())
    monkeypatch.setattr(cli, "write_footprint", lambda *_a, **_k: "fp\n")
    monkeypatch.setattr(cli, "write_symbol", lambda *_a, **_k: "sym\n")

    args = SimpleNamespace(
        part="C123",
        show=None,
        output=None,
        project=str(tmp_path),
        global_dest=False,
        overwrite=False,
        lib_name="MyLib",
    )
    cli.cmd_import(args)

    out = capsys.readouterr().out
    assert "Project library tables updated." in out
    assert (tmp_path / "MyLib.pretty" / "TestPart.kicad_mod").exists()
    assert (tmp_path / "MyLib.kicad_sym").exists()
    assert (tmp_path / "sym-lib-table").exists()
    assert (tmp_path / "fp-lib-table").exists()


def test_cli_import_global_does_not_require_project_dir(tmp_path, monkeypatch, capsys):
    import kicad_jlcimport.cli as cli

    fake_comp = {
        "title": "TestPart",
        "prefix": "U",
        "description": "",
        "datasheet": "",
        "manufacturer": "",
        "manufacturer_part": "",
        "footprint_data": {"dataStr": {"shape": ""}},
        "fp_origin_x": 0,
        "fp_origin_y": 0,
        "symbol_data_list": [],
        "sym_origin_x": 0,
        "sym_origin_y": 0,
    }

    class _Pad:
        layer = "1"

    class _Footprint:
        pads = [_Pad()]
        tracks = []
        model = None

    monkeypatch.setattr(cli, "fetch_full_component", lambda _lcsc: fake_comp)
    monkeypatch.setattr(cli, "parse_footprint_shapes", lambda *_a, **_k: _Footprint())
    monkeypatch.setattr(cli, "write_footprint", lambda *_a, **_k: "fp\n")
    monkeypatch.setattr(cli, "get_global_lib_dir", lambda: str(tmp_path))
    monkeypatch.setattr(cli, "update_global_lib_tables", lambda *_a, **_k: None)

    args = SimpleNamespace(
        part="C123",
        show=None,
        output=None,
        project=None,
        global_dest=True,
        overwrite=False,
        lib_name="MyLib",
    )
    cli.cmd_import(args)

    out = capsys.readouterr().out
    assert "Global library tables updated." in out
    assert (tmp_path / "MyLib.pretty" / "TestPart.kicad_mod").exists()

