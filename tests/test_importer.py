from pathlib import Path

import ezdxf
import pytest
import trimesh

from carvefoundry.core.importer import ImportFileError, inspect_import_file


def test_stl_import_is_loaded_as_mesh(tmp_path: Path) -> None:
    path = tmp_path / "part.stl"
    trimesh.creation.box(extents=(10.0, 20.0, 5.0)).export(path)

    info = inspect_import_file(path)

    assert info.kind == "stl"
    assert info.mesh is not None
    assert info.path == path.resolve()


def test_svg_import_is_validated(tmp_path: Path) -> None:
    path = tmp_path / "shape.svg"
    path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0 L10 10"/></svg>',
        encoding="utf-8",
    )

    info = inspect_import_file(path)

    assert info.kind == "svg"
    assert info.mesh is None


def test_invalid_svg_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "broken.svg"
    path.write_text("<svg><path>", encoding="utf-8")

    with pytest.raises(ImportFileError, match="Invalid SVG"):
        inspect_import_file(path)


def test_dxf_import_is_validated(tmp_path: Path) -> None:
    path = tmp_path / "drawing.dxf"
    document = ezdxf.new()
    document.modelspace().add_line((0, 0), (10, 10))
    document.saveas(path)

    info = inspect_import_file(path)

    assert info.kind == "dxf"
    assert info.mesh is None


@pytest.mark.parametrize(
    ("suffix", "payload"),
    [
        (".png", b"\x89PNG\r\n\x1a\n" + b"0" * 32),
        (".jpg", b"\xff\xd8\xff" + b"0" * 32),
        (".bmp", b"BM" + b"0" * 32),
        (".webp", b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"0" * 20),
    ],
)
def test_supported_image_signatures_are_accepted(
    tmp_path: Path,
    suffix: str,
    payload: bytes,
) -> None:
    path = tmp_path / f"image{suffix}"
    path.write_bytes(payload)

    info = inspect_import_file(path)

    assert info.kind == "image"


def test_gcode_import_is_validated(tmp_path: Path) -> None:
    path = tmp_path / "job.nc"
    path.write_text("G90\nG0 X0 Y0\nG1 Z-1.0 F100\nM30\n", encoding="utf-8")

    info = inspect_import_file(path)

    assert info.kind == "g-code"


def test_empty_file_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "empty.svg"
    path.write_bytes(b"")

    with pytest.raises(ImportFileError, match="empty"):
        inspect_import_file(path)


def test_unknown_extension_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "unknown.xyz"
    path.write_text("not a design", encoding="utf-8")

    with pytest.raises(ImportFileError, match="Unsupported file type"):
        inspect_import_file(path)


def test_expected_kind_rejects_mismatched_extension(tmp_path: Path) -> None:
    path = tmp_path / "part.svg"
    path.write_text("<svg/>", encoding="utf-8")

    with pytest.raises(ImportFileError, match="not a STL file"):
        inspect_import_file(path, expected_kind="STL")
