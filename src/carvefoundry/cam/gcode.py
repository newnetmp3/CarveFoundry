from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from unicodedata import normalize

from .toolpath import MoveKind, Toolpath

GCODE_SUFFIXES = frozenset({".nc", ".gcode", ".tap", ".cnc"})


@dataclass(frozen=True, slots=True)
class GrblPostSettings:
    """Minimal, conservative GRBL-family output settings."""

    decimals: int = 3
    include_comments: bool = True
    x_offset_mm: float = 0.0
    y_offset_mm: float = 0.0
    park_enabled: bool = False
    park_x_mm: float = 0.0
    park_y_mm: float = 0.0
    park_z_mm: float = 10.0

    def __post_init__(self) -> None:
        if not 0 <= self.decimals <= 6:
            raise ValueError("decimals must be between zero and six.")
        values = (
            self.x_offset_mm,
            self.y_offset_mm,
            self.park_x_mm,
            self.park_y_mm,
            self.park_z_mm,
        )
        if not all(isfinite(value) for value in values):
            raise ValueError("G-code coordinate settings must be finite.")
        if self.park_z_mm < 0:
            raise ValueError("Parking Z must be at or above work Z0.")


def _number(value: float, decimals: int) -> str:
    text = f"{value:.{decimals}f}"
    if decimals:
        text = text.rstrip("0").rstrip(".")
    if text in {"", "-0"}:
        return "0"
    return text


def _comment(text: str) -> str:
    """Keep human-readable operation names in safe ASCII GRBL comments."""

    sanitized = (
        text.replace("(", "[")
        .replace(")", "]")
        .replace("\n", " ")
        .replace("·", "-")
        .replace("°", " deg")
        .replace("×", "x")
        .replace("–", "-")
        .replace("—", "-")
    )
    return normalize("NFKD", sanitized).encode(
        "ascii", errors="replace"
    ).decode("ascii")


def _xy(
    x_mm: float,
    y_mm: float,
    settings: GrblPostSettings,
) -> tuple[str, str]:
    return (
        _number(x_mm + settings.x_offset_mm, settings.decimals),
        _number(y_mm + settings.y_offset_mm, settings.decimals),
    )


def _append_parking(
    lines: list[str],
    settings: GrblPostSettings,
    *,
    safe_z_mm: float,
) -> None:
    if not settings.park_enabled:
        return
    clearance = max(float(safe_z_mm), settings.park_z_mm)
    if settings.include_comments:
        lines.append("(Park)")
    lines.append(f"G0 Z{_number(clearance, settings.decimals)}")
    lines.append(
        "G0 X"
        + _number(settings.park_x_mm, settings.decimals)
        + " Y"
        + _number(settings.park_y_mm, settings.decimals)
    )


def render_grbl(
    toolpath: Toolpath,
    settings: GrblPostSettings | None = None,
    *,
    progress: Callable[[float], None] | None = None,
) -> str:
    """Render a metric absolute-coordinate program suitable for GRBL/Onefinity workflows."""

    options = settings or GrblPostSettings()
    if not toolpath.moves:
        raise ValueError("Cannot emit G-code for an empty toolpath.")

    lines: list[str] = []
    if options.include_comments:
        lines.extend(
            (
                "(CarveFoundry)",
                f"(Operation: {_comment(toolpath.name)})",
                f"(Cutter: {_comment(toolpath.cutter.name)})",
            )
        )
    lines.extend(("G90", "G21", "G17", "G94"))
    safe_z = _number(toolpath.safe_z_mm, options.decimals)
    lines.append(f"G0 Z{safe_z}")

    last_feed: float | None = None
    move_count = len(toolpath.moves)
    for index, move in enumerate(toolpath.moves):
        if progress is not None and index % 8192 == 0:
            progress(index / move_count)
        x, y = _xy(move.x_mm, move.y_mm, options)
        z = _number(move.z_mm, options.decimals)
        if move.kind is MoveKind.RAPID:
            lines.append(f"G0 X{x} Y{y} Z{z}")
            continue
        assert move.feed_mm_min is not None
        command = f"G1 X{x} Y{y} Z{z}"
        if last_feed != move.feed_mm_min:
            command += f" F{_number(move.feed_mm_min, options.decimals)}"
            last_feed = move.feed_mm_min
        lines.append(command)

    if progress is not None:
        progress(1.0)
    lines.append(f"G0 Z{safe_z}")
    _append_parking(lines, options, safe_z_mm=toolpath.safe_z_mm)
    lines.append("M2")
    return "\n".join(lines) + "\n"


def render_grbl_program(
    toolpaths: list[Toolpath] | tuple[Toolpath, ...],
    settings: GrblPostSettings | None = None,
    *,
    progress: Callable[[float], None] | None = None,
) -> str:
    """Render multiple operations as one metric absolute GRBL program."""

    options = settings or GrblPostSettings()
    if not toolpaths:
        raise ValueError("Cannot emit G-code without toolpaths.")
    if any(not toolpath.moves for toolpath in toolpaths):
        raise ValueError("Cannot emit G-code for an empty toolpath.")

    lines: list[str] = []
    if options.include_comments:
        lines.append("(CarveFoundry)")
    lines.extend(("G90", "G21", "G17", "G94"))

    total_moves = sum(len(toolpath.moves) for toolpath in toolpaths)
    completed_moves = 0
    for operation_index, toolpath in enumerate(toolpaths, start=1):
        if options.include_comments:
            lines.extend(
                (
                    f"(Operation {operation_index}: {_comment(toolpath.name)})",
                    f"(Cutter: {_comment(toolpath.cutter.name)})",
                )
            )
        safe_z = _number(toolpath.safe_z_mm, options.decimals)
        lines.append(f"G0 Z{safe_z}")

        last_feed: float | None = None
        for index, move in enumerate(toolpath.moves):
            if progress is not None and (completed_moves + index) % 8192 == 0:
                progress((completed_moves + index) / total_moves)
            x, y = _xy(move.x_mm, move.y_mm, options)
            z = _number(move.z_mm, options.decimals)
            if move.kind is MoveKind.RAPID:
                lines.append(f"G0 X{x} Y{y} Z{z}")
                continue

            assert move.feed_mm_min is not None
            command = f"G1 X{x} Y{y} Z{z}"
            if last_feed != move.feed_mm_min:
                command += (
                    f" F{_number(move.feed_mm_min, options.decimals)}"
                )
                last_feed = move.feed_mm_min
            lines.append(command)

        lines.append(f"G0 Z{safe_z}")
        completed_moves += len(toolpath.moves)
        if progress is not None:
            progress(completed_moves / total_moves)

    _append_parking(
        lines,
        options,
        safe_z_mm=max(toolpath.safe_z_mm for toolpath in toolpaths),
    )
    lines.append("M2")
    return "\n".join(lines) + "\n"


def normalize_gcode_path(path: str | Path) -> Path:
    """Return a machine-file path, defaulting unsupported suffixes to .nc."""

    output_path = Path(path).expanduser()
    if output_path.suffix.lower() not in GCODE_SUFFIXES:
        output_path = output_path.with_suffix(".nc")
    return output_path


def write_grbl_program(
    toolpaths: list[Toolpath] | tuple[Toolpath, ...],
    path: str | Path,
    settings: GrblPostSettings | None = None,
    *,
    progress: Callable[[float], None] | None = None,
) -> Path:
    """Write a multi-operation GRBL program."""

    output_path = normalize_gcode_path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    try:
        temporary.write_text(
            render_grbl_program(toolpaths, settings, progress=progress),
            encoding="ascii",
        )
        temporary.replace(output_path)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise
    return output_path


def write_grbl(
    toolpath: Toolpath,
    path: str | Path,
    settings: GrblPostSettings | None = None,
    *,
    progress: Callable[[float], None] | None = None,
) -> Path:
    """Write GRBL G-code atomically enough for normal desktop export."""

    output_path = normalize_gcode_path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    try:
        temporary.write_text(
            render_grbl(toolpath, settings, progress=progress),
            encoding="ascii",
        )
        temporary.replace(output_path)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise
    return output_path
