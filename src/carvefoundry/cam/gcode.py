from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .toolpath import MoveKind, Toolpath

GCODE_SUFFIXES = frozenset({".nc", ".gcode", ".tap", ".cnc"})


@dataclass(frozen=True, slots=True)
class GrblPostSettings:
    """Minimal, conservative GRBL-family output settings."""

    decimals: int = 3
    include_comments: bool = True

    def __post_init__(self) -> None:
        if not 0 <= self.decimals <= 6:
            raise ValueError("decimals must be between zero and six.")


def _number(value: float, decimals: int) -> str:
    text = f"{value:.{decimals}f}".rstrip("0").rstrip(".")
    if text in {"", "-0"}:
        return "0"
    return text


def _comment(text: str) -> str:
    return text.replace("(", "[").replace(")", "]").replace("\n", " ")


def render_grbl(toolpath: Toolpath, settings: GrblPostSettings | None = None) -> str:
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
    for move in toolpath.moves:
        x = _number(move.x_mm, options.decimals)
        y = _number(move.y_mm, options.decimals)
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

    lines.append(f"G0 Z{safe_z}")
    lines.append("M2")
    return "\n".join(lines) + "\n"


def render_grbl_program(
    toolpaths: list[Toolpath] | tuple[Toolpath, ...],
    settings: GrblPostSettings | None = None,
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
        for move in toolpath.moves:
            x = _number(move.x_mm, options.decimals)
            y = _number(move.y_mm, options.decimals)
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
) -> Path:
    """Write a multi-operation GRBL program."""

    output_path = normalize_gcode_path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    try:
        temporary.write_text(
            render_grbl_program(toolpaths, settings),
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
) -> Path:
    """Write GRBL G-code atomically enough for normal desktop export."""

    output_path = normalize_gcode_path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    try:
        temporary.write_text(render_grbl(toolpath, settings), encoding="ascii")
        temporary.replace(output_path)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise
    return output_path
