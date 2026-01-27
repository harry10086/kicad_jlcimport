"""Tests for model3d.py - VRML conversion and model transforms."""

import pytest

from kicad_jlcimport.easyeda.ee_types import EE3DModel
from kicad_jlcimport.kicad.model3d import compute_model_transform, convert_to_vrml, download_and_save_models


class TestComputeModelTransform:
    def test_zero_z(self):
        """X/Y offset is always 0 - only Z is used."""
        model = EE3DModel(uuid="test", origin_x=0, origin_y=0, z=0, rotation=(0, 0, 0))
        offset, rotation = compute_model_transform(model, 0, 0)
        assert offset == (0.0, 0.0, 0.0)
        assert rotation == (0, 0, 0)

    def test_z_offset(self):
        """Z offset is converted from 3D units (100/mm) to mm."""
        model = EE3DModel(uuid="test", origin_x=200, origin_y=300, z=50, rotation=(0, 0, 90))
        offset, rotation = compute_model_transform(model, 100, 100)
        # X/Y are always 0 - c_origin is just canvas position, not offset
        assert offset[0] == 0.0
        assert offset[1] == 0.0
        # z: 50/100 = 0.5 mm
        assert offset[2] == pytest.approx(0.5)
        assert rotation == (0, 0, 90)

    def test_rotation_preserved(self):
        """Rotation tuple is passed through unchanged."""
        model = EE3DModel(uuid="test", origin_x=50, origin_y=50, z=0, rotation=(10, 20, 30))
        offset, rotation = compute_model_transform(model, 100, 100)
        assert offset[0] == 0.0
        assert offset[1] == 0.0
        assert rotation == (10, 20, 30)


class TestConvertToVrml:
    def test_empty_source(self):
        assert convert_to_vrml("") is None

    def test_no_vertices(self):
        source = "newmtl red\nKd 1 0 0\nendmtl\nusemtl red\nf 1 2 3"
        assert convert_to_vrml(source) is None

    def test_no_faces(self):
        source = "v 1 0 0\nv 0 1 0\nv 0 0 1\n"
        assert convert_to_vrml(source) is None

    def test_basic_triangle(self):
        source = (
            "newmtl mat1\n"
            "Kd 0.8 0.2 0.1\n"
            "Ks 0.1 0.1 0.1\n"
            "d 0\n"
            "endmtl\n"
            "v 0 0 0\n"
            "v 2.54 0 0\n"
            "v 0 2.54 0\n"
            "usemtl mat1\n"
            "f 1 2 3\n"
        )
        result = convert_to_vrml(source)
        assert result is not None
        assert "#VRML V2.0 utf8" in result
        assert "Shape {" in result
        assert "IndexedFaceSet" in result
        assert "diffuseColor" in result
        assert "coordIndex" in result

    def test_unit_conversion(self):
        # Vertices should be divided by 2.54
        source = "newmtl m\nKd 0.5 0.5 0.5\nendmtl\nv 2.54 5.08 7.62\nv 0 0 0\nv 2.54 2.54 0\nusemtl m\nf 1 2 3\n"
        result = convert_to_vrml(source)
        # 2.54 / 2.54 = 1.0, 5.08 / 2.54 = 2.0, 7.62 / 2.54 = 3.0
        assert "1.000000 2.000000 3.000000" in result

    def test_multiple_materials(self):
        source = (
            "newmtl red\nKd 1 0 0\nendmtl\n"
            "newmtl blue\nKd 0 0 1\nendmtl\n"
            "v 0 0 0\nv 1 0 0\nv 0 1 0\n"
            "v 2 0 0\nv 3 0 0\nv 2 1 0\n"
            "usemtl red\nf 1 2 3\n"
            "usemtl blue\nf 4 5 6\n"
        )
        result = convert_to_vrml(source)
        assert result.count("Shape {") == 2
        assert "1.0000 0.0000 0.0000" in result  # red
        assert "0.0000 0.0000 1.0000" in result  # blue

    def test_face_with_normals(self):
        # f v1//n1 v2//n2 v3//n3 format
        source = "newmtl m\nKd 0.5 0.5 0.5\nendmtl\nv 0 0 0\nv 1 0 0\nv 0 1 0\nusemtl m\nf 1//1 2//2 3//3\n"
        result = convert_to_vrml(source)
        assert result is not None
        assert "coordIndex" in result

    def test_face_with_texture_coords(self):
        # f v1/t1 v2/t2 v3/t3 format
        source = "newmtl m\nKd 0.5 0.5 0.5\nendmtl\nv 0 0 0\nv 1 0 0\nv 0 1 0\nusemtl m\nf 1/1 2/2 3/3\n"
        result = convert_to_vrml(source)
        assert result is not None

    def test_transparency(self):
        source = "newmtl glass\nKd 0.9 0.9 0.9\nd 0.5\nendmtl\nv 0 0 0\nv 1 0 0\nv 0 1 0\nusemtl glass\nf 1 2 3\n"
        result = convert_to_vrml(source)
        assert "transparency 0.5000" in result

    def test_quad_face(self):
        source = "newmtl m\nKd 0.5 0.5 0.5\nendmtl\nv 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\nusemtl m\nf 1 2 3 4\n"
        result = convert_to_vrml(source)
        assert result is not None
        assert "-1" in result  # face terminator

    def test_vrml_header(self):
        source = "newmtl m\nKd 0.5 0.5 0.5\nendmtl\nv 0 0 0\nv 1 0 0\nv 0 1 0\nusemtl m\nf 1 2 3\n"
        result = convert_to_vrml(source)
        lines = result.strip().split("\n")
        assert lines[0] == "#VRML V2.0 utf8"


class TestDownloadAndSaveModels:
    def test_skips_existing_files_by_default(self, tmp_path, monkeypatch):
        import kicad_jlcimport.kicad.model3d as model3d

        step_path = tmp_path / "part.step"
        wrl_path = tmp_path / "part.wrl"
        step_path.write_bytes(b"old-step")
        wrl_path.write_text("old-wrl", encoding="utf-8")

        def _should_not_download(*_a, **_k):
            raise AssertionError("download should be skipped for existing files")

        monkeypatch.setattr(model3d, "download_step", _should_not_download)
        monkeypatch.setattr(model3d, "download_wrl_source", _should_not_download)

        step_out, wrl_out = download_and_save_models("uuid", str(tmp_path), "part")
        assert step_out == str(step_path)
        assert wrl_out == str(wrl_path)
        assert step_path.read_bytes() == b"old-step"
        assert wrl_path.read_text(encoding="utf-8") == "old-wrl"

    def test_overwrite_true_rewrites_files(self, tmp_path, monkeypatch):
        import kicad_jlcimport.kicad.model3d as model3d

        step_path = tmp_path / "part.step"
        wrl_path = tmp_path / "part.wrl"
        step_path.write_bytes(b"old-step")
        wrl_path.write_text("old-wrl", encoding="utf-8")

        monkeypatch.setattr(model3d, "download_step", lambda *_a, **_k: b"new-step")
        monkeypatch.setattr(model3d, "download_wrl_source", lambda *_a, **_k: "src")
        monkeypatch.setattr(model3d, "convert_to_vrml", lambda *_a, **_k: "new-wrl")

        step_out, wrl_out = download_and_save_models("uuid", str(tmp_path), "part", overwrite=True)
        assert step_out == str(step_path)
        assert wrl_out == str(wrl_path)
        assert step_path.read_bytes() == b"new-step"
        assert wrl_path.read_text(encoding="utf-8") == "new-wrl"
