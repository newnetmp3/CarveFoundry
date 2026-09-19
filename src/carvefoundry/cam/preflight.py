"""CNC preflight for stock limits, machine travel and physical fixture clearance.

Coordinates: cutter TIP in stock bottom-left XY and stock top Z0.
The checker is deliberately conservative: it treats the cutter as its entire
nominal radius at every Z and each fixture as a solid vertical column. It
cannot certify holders, machine home/work-offset setup or spindle condition.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from collections.abc import Sequence

from carvefoundry.cam.gcode import GrblPostSettings
from carvefoundry.cam.toolpath import MoveKind, Toolpath
from carvefoundry.core.fixtures import Fixture
from carvefoundry.core.machine_profiles import MachineProfile
from carvefoundry.core.project import Stock

_EPS = 0.001


@dataclass(frozen=True, slots=True)
class Finding:
    severity: str
    code: str
    message: str
    operation: str = ""
    move_index: int | None = None


@dataclass(frozen=True, slots=True)
class PreflightResult:
    findings: tuple[Finding, ...]
    checked_moves: int

    @property
    def safe_to_export(self) -> bool:
        return not any(f.severity == "ERROR" for f in self.findings)

    def format_report(self) -> str:
        status = "PASS" if self.safe_to_export else "BLOCKED"
        lines = [f"Preflight {status} — {self.checked_moves:,} moves"]
        for finding in self.findings:
            where = f" [{finding.operation}]" if finding.operation else ""
            move = (
                f" move {finding.move_index:,}" if finding.move_index is not None
                else ""
            )
            lines.append(
                f"{finding.severity}: {finding.message}{where}{move}"
            )
        if not self.findings:
            lines.append("No issues detected within the configured limits.")
        lines.append(
            "Check actual work offsets, clamps/holders, bit reach and current "
            "machine position before running. Offline checks cannot verify these."
        )
        return "\n".join(lines)


def _xy_overlap(
    a: tuple[float, float],
    b: tuple[float, float],
    rect: tuple[float, float, float, float],
) -> tuple[float, float] | None:
    """Liang-Barsky segment intersection, including a segment inside a box."""
    x0, y0 = a
    dx, dy = b[0] - x0, b[1] - y0
    xmin, ymin, xmax, ymax = rect
    enter, leave = 0.0, 1.0
    for p, q in (
        (-dx, x0 - xmin), (dx, xmax - x0),
        (-dy, y0 - ymin), (dy, ymax - y0),
    ):
        if abs(p) <= 1e-12:
            if q < -_EPS:
                return None
            continue
        t = q / p
        if p < 0:
            enter = max(enter, t)
        else:
            leave = min(leave, t)
        if enter > leave + 1e-12:
            return None
    return max(0.0, enter), min(1.0, leave)


def _fixture_collision(
    start: tuple[float, float, float],
    end: tuple[float, float, float],
    fixture: Fixture,
    cutter_radius: float,
) -> bool:
    margin = cutter_radius + fixture.clearance_mm
    overlap = _xy_overlap(
        (start[0], start[1]), (end[0], end[1]),
        (
            fixture.x_min_mm - margin,
            fixture.y_min_mm - margin,
            fixture.x_max_mm + margin,
            fixture.y_max_mm + margin,
        ),
    )
    if overlap is None:
        return False
    enter, leave = overlap
    z_at_enter = start[2] + (end[2] - start[2]) * enter
    z_at_leave = start[2] + (end[2] - start[2]) * leave
    return min(z_at_enter, z_at_leave) < fixture.top_z_mm + fixture.clearance_mm - _EPS


def check_preflight(
    paths: Sequence[Toolpath],
    stock: Stock,
    profile: MachineProfile,
    fixtures: Sequence[Fixture] = (),
    options: GrblPostSettings | None = None,
) -> PreflightResult:
    """Validate output program before writing, preserving current work offsets.

    Only relative travel extents can be checked offline. Travel clearance at the
    actual G54 work origin MUST be verified at the machine.
    """
    profile.validate()
    for fixture in fixtures:
        fixture.validate()
    settings = options or GrblPostSettings()
    findings: list[Finding] = []
    if not paths:
        return PreflightResult(
            (Finding("ERROR", "EMPTY", "No toolpaths to check."),), 0
        )
    if not fixtures:
        findings.append(
            Finding(
                "WARNING", "NO_FIXTURES",
                "No fixtures recorded; add clamps/fences to check their clearance.",
            )
        )
    if stock.width_mm > profile.work_x_mm + _EPS:
        findings.append(Finding(
            "ERROR", "STOCK_TRAVEL_X",
            f"Stock width {stock.width_mm:g} mm exceeds machine X travel "
            f"{profile.work_x_mm:g} mm.",
        ))
    if stock.height_mm > profile.work_y_mm + _EPS:
        findings.append(Finding(
            "ERROR", "STOCK_TRAVEL_Y",
            f"Stock height {stock.height_mm:g} mm exceeds machine Y travel "
            f"{profile.work_y_mm:g} mm.",
        ))
    count = 0
    min_xyz = [float("inf")] * 3
    max_xyz = [float("-inf")] * 3
    outside_stock_reported: set[str] = set()
    fixture_reported: set[tuple[str, str]] = set()
    overcut_reported: set[str] = set()
    for path in paths:
        if not path.moves:
            findings.append(Finding(
                "ERROR", "EMPTY_PATH", "Operation has no moves.", path.name
            ))
            continue
        if path.safe_z_mm < -_EPS:
            findings.append(Finding(
                "ERROR", "NEGATIVE_SAFE_Z",
                f"Safe Z is below the stock top ({path.safe_z_mm:g} mm).",
                path.name,
            ))
        r = path.cutter.radius_mm
        for idx, move in enumerate(path.moves):
            count += 1
            for axis, coordinate in enumerate(move.xyz):
                min_xyz[axis] = min(min_xyz[axis], coordinate)
                max_xyz[axis] = max(max_xyz[axis], coordinate)
            if move.kind is not MoveKind.RAPID:
                if move.z_mm < -stock.thickness_mm - _EPS and path.name not in overcut_reported:
                    findings.append(Finding(
                        "ERROR", "THROUGH_STOCK",
                        f"Cutter tip Z{move.z_mm:g} extends below stock bottom "
                        f"Z{-stock.thickness_mm:g}.",
                        path.name, idx,
                    ))
                    overcut_reported.add(path.name)
                if (
                    (move.x_mm - r < -_EPS or move.y_mm - r < -_EPS or
                     move.x_mm + r > stock.width_mm + _EPS or
                     move.y_mm + r > stock.height_mm + _EPS)
                    and path.name not in outside_stock_reported
                ):
                    findings.append(Finding(
                        "WARNING", "OUTSIDE_STOCK",
                        "Cutter footprint extends beyond stock XY; verify intentional "
                        "edge machining and available spoilboard clearance.",
                        path.name, idx,
                    ))
                    outside_stock_reported.add(path.name)
            if idx == 0:
                # Postprocessor lifts to safe Z before this first move. Its
                # starting XY is unknown offline and cannot be collision-checked.
                start = (move.x_mm, move.y_mm, path.safe_z_mm)
            else:
                start = path.moves[idx - 1].xyz
            for fixture in fixtures:
                key = (path.name, fixture.name)
                if key not in fixture_reported and _fixture_collision(
                    start, move.xyz, fixture, r
                ):
                    findings.append(Finding(
                        "ERROR", "FIXTURE_COLLISION",
                        f"Cutter intersects {fixture.name!r} keep-out/clearance "
                        f"(top Z{fixture.top_z_mm:g} mm, margin "
                        f"{fixture.clearance_mm:g} mm).",
                        path.name, idx,
                    ))
                    fixture_reported.add(key)
        # Postprocessor retracts vertically to safe Z after each operation.
        last = path.moves[-1]
        for fixture in fixtures:
            key = (path.name, fixture.name)
            if key not in fixture_reported and _fixture_collision(
                last.xyz,
                (last.x_mm, last.y_mm, path.safe_z_mm),
                fixture,
                path.cutter.radius_mm,
            ):
                findings.append(Finding(
                    "ERROR", "FIXTURE_RETRACT",
                    f"Final retract intersects {fixture.name!r}.", path.name,
                ))
                fixture_reported.add(key)
    if count and (
        max_xyz[0] - min_xyz[0] > profile.work_x_mm + _EPS
        or max_xyz[1] - min_xyz[1] > profile.work_y_mm + _EPS
    ):
        findings.append(Finding(
            "ERROR", "PROGRAM_TRAVEL_XY",
            "Program XY span exceeds the configured machine travel.",
        ))
    if count and max_xyz[2] - min_xyz[2] > profile.work_z_mm + _EPS:
        findings.append(Finding(
            "ERROR", "PROGRAM_TRAVEL_Z",
            "Program Z span exceeds the configured machine travel.",
        ))
    if settings.park_enabled and paths:
        last = paths[-1].moves[-1] if paths[-1].moves else None
        park_z = max(max(path.safe_z_mm for path in paths), settings.park_z_mm)
        if last is not None:
            for fixture in fixtures:
                if _fixture_collision(
                    (last.x_mm, last.y_mm, park_z),
                    (settings.park_x_mm, settings.park_y_mm, park_z),
                    fixture, paths[-1].cutter.radius_mm,
                ):
                    findings.append(Finding(
                        "ERROR", "PARK_COLLISION",
                        f"Parking XY transit does not clear {fixture.name!r}.",
                    ))
    findings.append(Finding(
        "WARNING", "WORK_OFFSET",
        "Machine work offset, holder diameter, and initial cutter position "
        "cannot be verified offline.",
    ))
    return PreflightResult(tuple(findings), count)
