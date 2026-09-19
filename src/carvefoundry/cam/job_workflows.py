from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from math import ceil, isfinite

from .toolpath import MoveKind, Toolpath, ToolpathMove

_EPS = 1.0e-9


@dataclass(frozen=True, slots=True)
class Tile:
    """One rectangular section of a larger workpiece."""

    row: int
    column: int
    x0_mm: float
    y0_mm: float
    x1_mm: float
    y1_mm: float

    @property
    def width_mm(self) -> float:
        return self.x1_mm - self.x0_mm

    @property
    def height_mm(self) -> float:
        return self.y1_mm - self.y0_mm


@dataclass(frozen=True, slots=True)
class TilingSettings:
    tile_width_mm: float
    tile_height_mm: float
    overlap_mm: float = 0.0
    rebase_each_tile: bool = True

    def validate(self) -> None:
        values = (self.tile_width_mm, self.tile_height_mm, self.overlap_mm)
        if not all(isfinite(value) for value in values):
            raise ValueError("Tiling dimensions must be finite.")
        if self.tile_width_mm <= 0 or self.tile_height_mm <= 0:
            raise ValueError("Tile width and height must be greater than zero.")
        if self.overlap_mm < 0:
            raise ValueError("Tile overlap cannot be negative.")
        if self.overlap_mm >= min(self.tile_width_mm, self.tile_height_mm):
            raise ValueError("Tile overlap must be smaller than both tile dimensions.")


def plan_tiles(
    stock_width_mm: float,
    stock_height_mm: float,
    settings: TilingSettings,
) -> list[Tile]:
    """Return a row-major tile plan that fully covers the stock."""

    settings.validate()
    if stock_width_mm <= 0 or stock_height_mm <= 0:
        raise ValueError("Stock dimensions must be greater than zero.")

    step_x = settings.tile_width_mm - settings.overlap_mm
    step_y = settings.tile_height_mm - settings.overlap_mm
    columns = max(
        1,
        ceil(max(0.0, stock_width_mm - settings.overlap_mm) / step_x),
    )
    rows = max(
        1,
        ceil(max(0.0, stock_height_mm - settings.overlap_mm) / step_y),
    )

    result: list[Tile] = []
    for row in range(rows):
        y0 = row * step_y
        y1 = min(y0 + settings.tile_height_mm, stock_height_mm)
        for column in range(columns):
            x0 = column * step_x
            x1 = min(x0 + settings.tile_width_mm, stock_width_mm)
            if x0 < stock_width_mm - _EPS and y0 < stock_height_mm - _EPS:
                result.append(Tile(row, column, x0, y0, x1, y1))
    return result


def _copy_path(
    toolpath: Toolpath,
    moves: list[ToolpathMove],
    *,
    name: str,
) -> Toolpath:
    return Toolpath(
        name=name,
        operation=toolpath.operation,
        cutter=toolpath.cutter,
        safe_z_mm=toolpath.safe_z_mm,
        moves=moves,
        source_item_id=toolpath.source_item_id,
        source_item_name=toolpath.source_item_name,
    )


def offset_toolpath_xy(
    toolpath: Toolpath,
    dx_mm: float,
    dy_mm: float,
    *,
    name: str | None = None,
) -> Toolpath:
    """Return a translated copy without altering Z, feeds, or move kinds."""

    return _copy_path(
        toolpath,
        [
            ToolpathMove(
                move.x_mm + dx_mm,
                move.y_mm + dy_mm,
                move.z_mm,
                move.kind,
                move.feed_mm_min,
            )
            for move in toolpath.moves
        ],
        name=name or toolpath.name,
    )


def _plunge_feed(toolpath: Toolpath) -> float:
    for move in toolpath.moves:
        if move.kind is MoveKind.PLUNGE and move.feed_mm_min is not None:
            return move.feed_mm_min
    for move in toolpath.moves:
        if move.kind is not MoveKind.RAPID and move.feed_mm_min is not None:
            return move.feed_mm_min
    raise ValueError("Toolpath has no cutting feed available for safe re-entry.")


def find_safe_resume_index(toolpath: Toolpath, requested_index: int) -> int:
    """Rewind a requested point to the beginning of its current cutting section."""

    if not toolpath.moves:
        raise ValueError("Cannot resume an empty toolpath.")
    if not 0 <= requested_index < len(toolpath.moves):
        raise IndexError("Resume move index is outside the toolpath.")

    index = requested_index
    while index > 0 and toolpath.moves[index].kind is not MoveKind.RAPID:
        index -= 1
    while index < len(toolpath.moves) and toolpath.moves[index].kind is MoveKind.RAPID:
        index += 1
    if index >= len(toolpath.moves):
        raise ValueError("No cutting moves remain after the selected resume point.")
    return index


def resume_toolpath(
    toolpath: Toolpath,
    start_move_index: int,
    *,
    safe_rewind: bool = True,
    name: str | None = None,
) -> Toolpath:
    """Build a continuation path with an explicit Safe-Z re-entry.

    By default the requested point is rewound to the start of the current
    uninterrupted cutting section. This may repeat some already-cut geometry,
    but avoids vertically plunging into the middle of an arbitrary 3D pass.
    """

    first_index = (
        find_safe_resume_index(toolpath, start_move_index)
        if safe_rewind
        else start_move_index
    )
    if not 0 <= first_index < len(toolpath.moves):
        raise IndexError("Resume move index is outside the toolpath.")

    while (
        first_index < len(toolpath.moves)
        and toolpath.moves[first_index].kind is MoveKind.RAPID
    ):
        first_index += 1
    if first_index >= len(toolpath.moves):
        raise ValueError("No cutting moves remain after the selected resume point.")

    first = toolpath.moves[first_index]
    plunge_feed = _plunge_feed(toolpath)
    moves = [
        ToolpathMove(first.x_mm, first.y_mm, toolpath.safe_z_mm, MoveKind.RAPID),
        ToolpathMove(
            first.x_mm,
            first.y_mm,
            first.z_mm,
            MoveKind.PLUNGE,
            plunge_feed,
        ),
    ]
    moves.extend(toolpath.moves[first_index + 1 :])

    if moves[-1].z_mm < toolpath.safe_z_mm - _EPS:
        last = moves[-1]
        moves.append(
            ToolpathMove(last.x_mm, last.y_mm, toolpath.safe_z_mm, MoveKind.RAPID)
        )

    return _copy_path(
        toolpath,
        moves,
        name=name or f"{toolpath.name} (Resume)",
    )


def _clip_segment_to_tile(
    start: ToolpathMove,
    end: ToolpathMove,
    tile: Tile,
) -> tuple[float, float] | None:
    """Liang-Barsky clip in XY, returning segment parameters t0/t1."""

    dx = end.x_mm - start.x_mm
    dy = end.y_mm - start.y_mm
    p = (-dx, dx, -dy, dy)
    q = (
        start.x_mm - tile.x0_mm,
        tile.x1_mm - start.x_mm,
        start.y_mm - tile.y0_mm,
        tile.y1_mm - start.y_mm,
    )
    t0 = 0.0
    t1 = 1.0
    for direction, distance in zip(p, q, strict=True):
        if abs(direction) <= _EPS:
            if distance < -_EPS:
                return None
            continue
        ratio = distance / direction
        if direction < 0:
            if ratio > t1:
                return None
            t0 = max(t0, ratio)
        else:
            if ratio < t0:
                return None
            t1 = min(t1, ratio)
    if t0 > t1 + _EPS:
        return None
    return max(0.0, t0), min(1.0, t1)


def _interpolate_move(
    start: ToolpathMove,
    end: ToolpathMove,
    t: float,
) -> tuple[float, float, float]:
    return (
        start.x_mm + (end.x_mm - start.x_mm) * t,
        start.y_mm + (end.y_mm - start.y_mm) * t,
        start.z_mm + (end.z_mm - start.z_mm) * t,
    )


def tile_toolpath(
    toolpath: Toolpath,
    tile: Tile,
    *,
    rebase: bool = True,
) -> Toolpath | None:
    """Clip cutting geometry to one tile and add conservative Safe-Z links."""

    if len(toolpath.moves) < 2:
        return None

    plunge_feed = _plunge_feed(toolpath)
    moves: list[ToolpathMove] = []
    continuation = False
    previous_endpoint: tuple[float, float, float] | None = None

    def translated(point: tuple[float, float, float]) -> tuple[float, float, float]:
        x, y, z = point
        if rebase:
            return x - tile.x0_mm, y - tile.y0_mm, z
        return point

    def retract_if_needed() -> None:
        if not moves:
            return
        last = moves[-1]
        if last.z_mm < toolpath.safe_z_mm - _EPS:
            moves.append(
                ToolpathMove(
                    last.x_mm,
                    last.y_mm,
                    toolpath.safe_z_mm,
                    MoveKind.RAPID,
                )
            )

    for start, end in pairwise(toolpath.moves):
        if end.kind is MoveKind.RAPID:
            continuation = False
            previous_endpoint = None
            continue

        clipped = _clip_segment_to_tile(start, end, tile)
        if clipped is None:
            continuation = False
            previous_endpoint = None
            continue

        t0, t1 = clipped
        entry_world = _interpolate_move(start, end, t0)
        exit_world = _interpolate_move(start, end, t1)
        entry = translated(entry_world)
        exit_point = translated(exit_world)

        can_continue = (
            continuation
            and previous_endpoint is not None
            and all(
                abs(a - b) <= 1.0e-7
                for a, b in zip(previous_endpoint, entry, strict=True)
            )
            and t0 <= _EPS
        )

        if not can_continue:
            retract_if_needed()
            moves.append(
                ToolpathMove(
                    entry[0],
                    entry[1],
                    toolpath.safe_z_mm,
                    MoveKind.RAPID,
                )
            )
            if abs(entry[2] - toolpath.safe_z_mm) > _EPS:
                moves.append(
                    ToolpathMove(
                        entry[0],
                        entry[1],
                        entry[2],
                        MoveKind.PLUNGE,
                        plunge_feed,
                    )
                )

        if any(abs(a - b) > _EPS for a, b in zip(entry, exit_point, strict=True)):
            kind = end.kind
            feed = end.feed_mm_min
            if kind is MoveKind.PLUNGE and (
                abs(exit_point[0] - entry[0]) > _EPS
                or abs(exit_point[1] - entry[1]) > _EPS
            ):
                kind = MoveKind.CUT
            moves.append(
                ToolpathMove(
                    exit_point[0],
                    exit_point[1],
                    exit_point[2],
                    kind,
                    feed,
                )
            )

        continuation = t1 >= 1.0 - _EPS
        previous_endpoint = exit_point if continuation else None

    retract_if_needed()
    if not any(move.kind is not MoveKind.RAPID for move in moves):
        return None

    return _copy_path(
        toolpath,
        moves,
        name=f"{toolpath.name} · Tile {tile.row + 1},{tile.column + 1}",
    )


def tile_program(
    toolpaths: list[Toolpath] | tuple[Toolpath, ...],
    tile: Tile,
    *,
    rebase: bool = True,
) -> list[Toolpath]:
    """Clip every operation to one tile, omitting operations with no cuts there."""

    result: list[Toolpath] = []
    for toolpath in toolpaths:
        tiled = tile_toolpath(toolpath, tile, rebase=rebase)
        if tiled is not None:
            result.append(tiled)
    return result
