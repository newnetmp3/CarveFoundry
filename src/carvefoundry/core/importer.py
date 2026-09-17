from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

import ezdxf

from .mesh import MeshAsset, MeshImportError, load_stl


class ImportFileError(ValueError):
    """Raised when a source file cannot be accepted by CarveFoundry."""


@dataclass(frozen=True, slots=True)
class ImportFileInfo:
    path: Path
    kind: str
    mesh: MeshAsset | None = None

    @property
    def is_renderable(self) -> bool:
        return self.mesh is not None


_EXTENSION_KIND = {
    ".stl": "stl",
    ".svg": "svg",
    ".dxf": "dxf",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".bmp": "image",
    ".webp": "image",
    ".nc": "g-code",
    ".gcode": "g-code",
    ".tap": "g-code",
    ".cnc": "g-code",
}

_KIND_EXTENSIONS = {
    "STL": {".stl"},
    "SVG": {".svg"},
    "DXF": {".dxf"},
    "IMAGE": {".png", ".jpg", ".jpeg", ".bmp", ".webp"},
    "G-CODE": {".nc", ".gcode", ".tap", ".cnc"},
}


def supported_extensions() -> tuple[str, ...]:
    return tuple(sorted(_EXTENSION_KIND))


def _validate_common(path: Path) -> None:
    if not path.is_file():
        raise ImportFileError(f"File does not exist: {path}")
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ImportFileError(f"Could not inspect {path.name}: {exc}") from exc
    if size <= 0:
        raise ImportFileError(f"{path.name} is empty.")


def _validate_expected_kind(path: Path, expected_kind: str | None) -> None:
    if expected_kind is None:
        return
    expected = expected_kind.strip().upper()
    extensions = _KIND_EXTENSIONS.get(expected)
    if extensions is None:
        raise ImportFileError(f"Unsupported import type: {expected_kind}")
    if path.suffix.lower() not in extensions:
        allowed = ", ".join(sorted(extensions))
        raise ImportFileError(
            f"{path.name} is not a {expected_kind} file (expected {allowed})."
        )


def _validate_svg(path: Path) -> None:
    try:
        root = ElementTree.parse(path).getroot()
    except (OSError, ElementTree.ParseError) as exc:
        raise ImportFileError(f"Invalid SVG {path.name}: {exc}") from exc
    tag = root.tag.rsplit("}", 1)[-1].lower()
    if tag != "svg":
        raise ImportFileError(f"{path.name} does not contain an SVG root element.")


def _validate_dxf(path: Path) -> None:
    try:
        ezdxf.readfile(path)
    except (OSError, ezdxf.DXFError) as exc:
        raise ImportFileError(f"Invalid DXF {path.name}: {exc}") from exc


def _validate_image(path: Path) -> None:
    try:
        header = path.read_bytes()[:32]
    except OSError as exc:
        raise ImportFileError(f"Could not read image {path.name}: {exc}") from exc

    suffix = path.suffix.lower()
    valid = False
    if suffix == ".png":
        valid = header.startswith(b"\x89PNG\r\n\x1a\n")
    elif suffix in {".jpg", ".jpeg"}:
        valid = header.startswith(b"\xff\xd8\xff")
    elif suffix == ".bmp":
        valid = header.startswith(b"BM")
    elif suffix == ".webp":
        valid = (
            len(header) >= 12
            and header.startswith(b"RIFF")
            and header[8:12] == b"WEBP"
        )
    if not valid:
        raise ImportFileError(f"{path.name} does not appear to be a valid {suffix} image.")


def _validate_gcode(path: Path) -> None:
    try:
        sample = path.read_bytes()[:262144]
    except OSError as exc:
        raise ImportFileError(f"Could not read G-code {path.name}: {exc}") from exc

    if b"\x00" in sample:
        raise ImportFileError(f"{path.name} appears to be a binary file, not G-code.")
    try:
        text = sample.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        try:
            text = sample.decode("ascii", errors="strict")
        except UnicodeDecodeError as exc:
            raise ImportFileError(f"{path.name} is not readable text G-code.") from exc

    meaningful = [
        line.strip().upper()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith(("#", ";", "("))
    ]
    if not meaningful:
        raise ImportFileError(f"{path.name} does not contain any G-code commands.")
    if not any(
        any(token.startswith(("G", "M", "T", "X", "Y", "Z", "F", "S")) for token in line.split())
        for line in meaningful[:500]
    ):
        raise ImportFileError(f"{path.name} does not appear to contain recognizable G-code.")


def inspect_import_file(
    path: str | Path,
    *,
    expected_kind: str | None = None,
) -> ImportFileInfo:
    """Validate an import source and return normalized import information."""

    source = Path(path).expanduser()
    _validate_common(source)
    _validate_expected_kind(source, expected_kind)

    suffix = source.suffix.lower()
    kind = _EXTENSION_KIND.get(suffix)
    if kind is None:
        raise ImportFileError(
            f"Unsupported file type {suffix or '(no extension)'} for {source.name}."
        )

    mesh: MeshAsset | None = None
    if kind == "stl":
        try:
            mesh = load_stl(source)
        except MeshImportError as exc:
            raise ImportFileError(str(exc)) from exc
    elif kind == "svg":
        _validate_svg(source)
    elif kind == "dxf":
        _validate_dxf(source)
    elif kind == "image":
        _validate_image(source)
    elif kind == "g-code":
        _validate_gcode(source)

    return ImportFileInfo(
        path=source.resolve(),
        kind=kind,
        mesh=mesh,
    )
