"""Fail-closed GRBL G-code decoder and post-export offline motion verification.

This parses the actual NC text rather than accepting the CAM planner's move list
as proof of what was exported. Supported modal dialect: linear G0/G1, G17,
G20/G21, G90/G91, G94, F, optional N words, M2/M30. Unsupported axes, arcs,
cycles, offsets and machine-coordinate commands are refused, not guessed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import pairwise
from math import isfinite

from carvefoundry.cam.gcode import GrblPostSettings
from carvefoundry.cam.preflight import Finding, PreflightResult, check_preflight
from carvefoundry.cam.toolpath import MoveKind, Toolpath, ToolpathMove
from carvefoundry.core.fixtures import Fixture
from carvefoundry.core.machine_profiles import MachineProfile
from carvefoundry.core.project import Stock

_WORD = re.compile(
    r"([A-Za-z])\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)"
)
_COMMENT = re.compile(r"\([^()]*\)")


@dataclass(frozen=True, slots=True)
class DecodedProgram:
    """Machine-space moves, in millimetres, with their original NC line numbers."""

    moves: tuple[ToolpathMove, ...]
    lines: tuple[int, ...]
    initial_safe_z_mm: float


@dataclass(frozen=True, slots=True)
class ExportVerification:
    preflight: PreflightResult
    decoded: DecodedProgram

    @property
    def safe_to_export(self) -> bool:
        return self.preflight.safe_to_export

    def format_report(self) -> str:
        return "Decoded exported G-code (not planner geometry)\n" + (
            self.preflight.format_report()
        )


def decode_grbl(program: str, *, x_offset_mm: float = 0, y_offset_mm: float = 0) -> DecodedProgram:
    """Interpret actual posted motion including modal coordinates and feed.

    The initial machine XY is unknowable offline. An initial Z-only G0 sets
    clearance but is not represented as a zero-length XY path. The first XY
    motion must be a noncutting rapid at/above the stock top.
    """
    if not all(isfinite(v) for v in (x_offset_mm, y_offset_mm)):
        raise ValueError("Non-finite coordinate offset")
    absolute: bool | None = None
    scale: float | None = None
    motion: MoveKind | None = None
    feed_mm_min: float | None = None
    x: float | None = None
    y: float | None = None
    z: float | None = None
    initial_z: float | None = None
    ended = False
    moves: list[ToolpathMove] = []
    lines: list[int] = []

    for number, raw in enumerate(program.splitlines(), start=1):
        if ended:
            if _COMMENT.sub("", raw.split(";", 1)[0]).strip():
                raise ValueError(f"NC line {number}: commands after program end")
            continue
        line = _COMMENT.sub("", raw.split(";", 1)[0]).strip()
        if not line or line == "%":
            continue
        words: dict[str, float] = {}
        g_words: list[int] = []
        end_program = False
        previous_end = 0
        for match in _WORD.finditer(line):
            if line[previous_end:match.start()].strip():
                raise ValueError(f"NC line {number}: unrecognized text")
            previous_end = match.end()
            letter = match.group(1).upper()
            value = float(match.group(2))
            if not isfinite(value):
                raise ValueError(f"NC line {number}: non-finite word")
            if letter == "G":
                if not value.is_integer():
                    raise ValueError(f"NC line {number}: unsupported fractional G code")
                g_words.append(int(value))
            elif letter == "M":
                if not value.is_integer() or int(value) not in (2, 30):
                    raise ValueError(f"NC line {number}: unsupported M code")
                end_program = True
            elif letter == "N":
                if "N" in words or not value.is_integer() or value < 0:
                    raise ValueError(f"NC line {number}: invalid line number")
                words["N"] = value
            elif letter in ("X", "Y", "Z", "F"):
                if letter in words:
                    raise ValueError(f"NC line {number}: duplicate {letter} word")
                words[letter] = value
            else:
                raise ValueError(f"NC line {number}: unsupported {letter} word")
        if line[previous_end:].strip():
            raise ValueError(f"NC line {number}: unrecognized text")
        if end_program:
            if g_words or any(k in words for k in ("X", "Y", "Z", "F")):
                raise ValueError(f"NC line {number}: end command mixed with motion")
            ended = True
            continue

        motion_codes = [g for g in g_words if g in (0, 1)]
        if len(motion_codes) > 1:
            raise ValueError(f"NC line {number}: conflicting motion commands")
        for g in g_words:
            if g in (0, 1):
                motion = MoveKind.RAPID if g == 0 else MoveKind.CUT
            elif g == 90:
                absolute = True
            elif g == 91:
                absolute = False
            elif g == 21:
                scale = 1.0
            elif g == 20:
                scale = 25.4
            elif g in (17, 94):
                pass
            else:
                raise ValueError(f"NC line {number}: unsupported G{g} (no arc/cycle/offset simulation)")
        if scale is None and any(k in words for k in ("X", "Y", "Z", "F")):
            raise ValueError(f"NC line {number}: units must be explicitly set")
        if absolute is None and any(k in words for k in ("X", "Y", "Z")):
            raise ValueError(f"NC line {number}: distance mode must be explicitly set")
        if "F" in words:
            feed_mm_min = words["F"] * scale  # type: ignore[operator]
            if feed_mm_min <= 0:
                raise ValueError(f"NC line {number}: feed must be positive")
        if not any(k in words for k in ("X", "Y", "Z")):
            continue
        if motion is None:
            raise ValueError(f"NC line {number}: motion mode not established")
        coordinates = {"X": x, "Y": y, "Z": z}
        for axis in ("X", "Y", "Z"):
            if axis in words:
                prev = coordinates[axis]
                if not absolute and prev is None:
                    raise ValueError(f"NC line {number}: unknown initial incremental {axis}")
                coordinates[axis] = (
                    (0.0 if absolute else float(prev))
                    + words[axis] * scale  # type: ignore[operator]
                )
        x, y, z = coordinates["X"], coordinates["Y"], coordinates["Z"]
        if x is None or y is None:
            if motion is not MoveKind.RAPID or z is None or z < 0:
                raise ValueError(f"NC line {number}: unsafe motion before XY is established")
            initial_z = z
            continue
        if z is None:
            raise ValueError(f"NC line {number}: initial Z is unknown")
        if not moves and (motion is not MoveKind.RAPID or z < 0):
            raise ValueError(f"NC line {number}: first XY must be a safe rapid")
        if motion is not MoveKind.RAPID and feed_mm_min is None:
            raise ValueError(f"NC line {number}: first cutting move has no feed")
        moves.append(ToolpathMove(
            x - x_offset_mm,
            y - y_offset_mm,
            z,
            motion,
            None if motion is MoveKind.RAPID else feed_mm_min,
        ))
        lines.append(number)

    if not ended:
        raise ValueError("NC program has no M2/M30 end command")
    if not moves:
        raise ValueError("NC program has no XY motion")
    if not any(move.kind is not MoveKind.RAPID for move in moves):
        raise ValueError("NC program has no cutting moves")
    return DecodedProgram(tuple(moves), tuple(lines), (
        initial_z if initial_z is not None else moves[0].z_mm
    ))


def verify_grbl_export(
    program: str,
    stage: list[Toolpath] | tuple[Toolpath, ...],
    stock: Stock,
    profile: MachineProfile,
    fixtures: tuple[Fixture, ...] = (),
    settings: GrblPostSettings | None = None,
    *,
    local_shift_mm: tuple[float, float] = (0.0, 0.0),
) -> ExportVerification:
    """Compare cutting words to planned cuts, then preflight *all* decoded motions.

    local_shift_mm translates global stock positions into a tile's local
    machine envelope; decoded coordinates always remove post offsets first.
    No initial XY/work-offset, tool holder or real machine state is inferred.
    """
    if not stage or any(path.cutter != stage[0].cutter for path in stage):
        raise ValueError("Verification requires one nonempty cutter stage")
    options = settings or GrblPostSettings()
    decoded = decode_grbl(
        program, x_offset_mm=options.x_offset_mm, y_offset_mm=options.y_offset_mm,
    )
    planned = [
        move for path in stage for move in path.moves
        if move.kind is not MoveKind.RAPID
    ]
    posted = [
        (i, move) for i, move in enumerate(decoded.moves)
        if move.kind is not MoveKind.RAPID
    ]
    if len(planned) != len(posted):
        raise ValueError(
            f"NC cutting move count differs from plan: {len(posted):,} "
            f"posted versus {len(planned):,} planned"
        )
    rounding = 0.5 * 10 ** (-options.decimals) + 1e-7
    for source, (index, actual) in zip(planned, posted, strict=True):
        if any(abs(a - b) > rounding for a, b in zip(source.xyz, actual.xyz, strict=True)):
            raise ValueError(
                f"NC line {decoded.lines[index]}: posted cut does not match planned XYZ"
            )
        if (source.feed_mm_min is None or actual.feed_mm_min is None or
                abs(source.feed_mm_min - actual.feed_mm_min) > rounding):
            raise ValueError(
                f"NC line {decoded.lines[index]}: posted feed does not match planned cut"
            )

    sx, sy = local_shift_mm
    if not all(isfinite(v) for v in (sx, sy)):
        raise ValueError("Invalid local verification offset")
    shifted = [
        ToolpathMove(
            move.x_mm + sx, move.y_mm + sy, move.z_mm,
            move.kind, move.feed_mm_min,
        )
        for move in decoded.moves
    ]
    actual_path = Toolpath(
        "Posted NC", stage[0].operation, stage[0].cutter,
        decoded.initial_safe_z_mm, shifted,
    )
    checked = check_preflight([actual_path], stock, profile, fixtures)
    findings = list(checked.findings)
    if decoded.initial_safe_z_mm < 0:
        findings.append(Finding(
            "ERROR", "INITIAL_RETRACT",
            "Posted initial retract is below stock top.",
            "Posted NC", decoded.lines[0],
        ))
    # Refuse rapid sweeps inside untouched stock. This is conservative: the
    # path may traverse already-cleared pockets, but must not be certified.
    for index, (before, after) in enumerate(pairwise(shifted), start=1):
        if (after.kind is MoveKind.RAPID and min(before.z_mm, after.z_mm) < -0.001
                and (abs(before.x_mm - after.x_mm) > 1e-6
                     or abs(before.y_mm - after.y_mm) > 1e-6)):
            r = stage[0].cutter.radius_mm
            if (
                max(before.x_mm, after.x_mm) + r >= 0
                and min(before.x_mm, after.x_mm) - r <= stock.width_mm
                and max(before.y_mm, after.y_mm) + r >= 0
                and min(before.y_mm, after.y_mm) - r <= stock.height_mm
            ):
                findings.append(Finding(
                    "ERROR", "RAPID_IN_STOCK",
                    f"NC line {decoded.lines[index]}: rapid may cross stock below Z0.",
                    "Posted NC", index,
                ))
                break
    return ExportVerification(
        PreflightResult(tuple(findings), checked.checked_moves), decoded,
    )
