from types import SimpleNamespace


def test_cli_import_project_writes_kicad_library(tmp_path, monkeypatch, capsys):
    import kicad_jlcimport.cli as cli
    import kicad_jlcimport.importer as importer

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

    monkeypatch.setattr(importer, "fetch_full_component", lambda _lcsc: fake_comp)
    monkeypatch.setattr(importer, "parse_footprint_shapes", lambda *_a, **_k: _Footprint())
    monkeypatch.setattr(importer, "parse_symbol_shapes", lambda *_a, **_k: _Symbol())
    monkeypatch.setattr(importer, "write_footprint", lambda *_a, **_k: "fp\n")
    monkeypatch.setattr(importer, "write_symbol", lambda *_a, **_k: "sym\n")

    args = SimpleNamespace(
        part="C123",
        show=None,
        output=None,
        project=str(tmp_path),
        global_dest=False,
        overwrite=False,
        lib_name="MyLib",
        kicad_version=9,
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
    import kicad_jlcimport.importer as importer

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

    monkeypatch.setattr(importer, "fetch_full_component", lambda _lcsc: fake_comp)
    monkeypatch.setattr(importer, "parse_footprint_shapes", lambda *_a, **_k: _Footprint())
    monkeypatch.setattr(importer, "write_footprint", lambda *_a, **_k: "fp\n")
    monkeypatch.setattr(cli, "get_global_lib_dir", lambda _v=9: str(tmp_path))
    monkeypatch.setattr(importer, "update_global_lib_tables", lambda *_a, **_k: None)

    args = SimpleNamespace(
        part="C123",
        show=None,
        output=None,
        project=None,
        global_dest=True,
        overwrite=False,
        lib_name="MyLib",
        kicad_version=9,
    )
    cli.cmd_import(args)

    out = capsys.readouterr().out
    assert "Global library tables updated." in out
    assert (tmp_path / "MyLib.pretty" / "TestPart.kicad_mod").exists()


def test_cli_import_project_skips_existing_3d_models_without_overwrite(tmp_path, monkeypatch, capsys):
    import kicad_jlcimport.cli as cli
    import kicad_jlcimport.importer as importer
    import kicad_jlcimport.model3d as model3d

    fake_comp = {
        "title": "TestPart",
        "prefix": "U",
        "description": "",
        "datasheet": "",
        "manufacturer": "",
        "manufacturer_part": "",
        "uuid_3d": "uuid",
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

    monkeypatch.setattr(importer, "fetch_full_component", lambda _lcsc: fake_comp)
    monkeypatch.setattr(importer, "parse_footprint_shapes", lambda *_a, **_k: _Footprint())
    monkeypatch.setattr(importer, "write_footprint", lambda *_a, **_k: "fp\n")

    calls = {"step": 0, "wrl": 0}

    def _download_step(*_a, **_k):
        calls["step"] += 1
        return b"step"

    def _download_wrl_source(*_a, **_k):
        calls["wrl"] += 1
        return "src"

    monkeypatch.setattr(model3d, "download_step", _download_step)
    monkeypatch.setattr(model3d, "download_wrl_source", _download_wrl_source)
    monkeypatch.setattr(model3d, "convert_to_vrml", lambda *_a, **_k: "wrl")

    args = SimpleNamespace(
        part="C123",
        show=None,
        output=None,
        project=str(tmp_path),
        global_dest=False,
        overwrite=False,
        lib_name="MyLib",
        kicad_version=9,
    )

    cli.cmd_import(args)
    capsys.readouterr()

    cli.cmd_import(args)
    out = capsys.readouterr().out

    assert calls == {"step": 1, "wrl": 1}
    assert "Skipped:" in out
    assert ".step" in out
    assert ".wrl" in out


def test_cli_import_with_kicad_v8(tmp_path, monkeypatch, capsys):
    """Test that --kicad-version 8 produces v8-format library files."""
    import kicad_jlcimport.cli as cli
    import kicad_jlcimport.importer as importer

    fake_comp = {
        "title": "TestPart",
        "prefix": "U",
        "description": "desc",
        "datasheet": "",
        "manufacturer": "",
        "manufacturer_part": "",
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
        pins = [object()]
        rectangles = []

    monkeypatch.setattr(importer, "fetch_full_component", lambda _lcsc: fake_comp)
    monkeypatch.setattr(importer, "parse_footprint_shapes", lambda *_a, **_k: _Footprint())
    monkeypatch.setattr(importer, "parse_symbol_shapes", lambda *_a, **_k: _Symbol())
    monkeypatch.setattr(importer, "write_footprint", lambda *_a, **_k: "fp\n")
    monkeypatch.setattr(importer, "write_symbol", lambda *_a, **_k: "sym\n")

    args = SimpleNamespace(
        part="C123",
        show=None,
        output=None,
        project=str(tmp_path),
        global_dest=False,
        overwrite=False,
        lib_name="MyLib",
        kicad_version=8,
    )
    cli.cmd_import(args)

    # Verify the symbol library was created with v8 format
    sym_path = tmp_path / "MyLib.kicad_sym"
    assert sym_path.exists()
    sym_text = sym_path.read_text()
    assert "(version 20231120)" in sym_text
    assert "generator_version" not in sym_text
