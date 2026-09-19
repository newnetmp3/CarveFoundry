"""Isolated CPU-heavy CarveFoundry jobs.

Never import PySide6 in this module. Only serializable snapshots cross the
process boundary and no subprocess can mutate the live Qt project.
"""
from __future__ import annotations

import json
import pickle
import sys
import time
import traceback
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np

from carvefoundry.cam.basic_ops import BasicCamSettings, ReliefStyle, finish_3d, waterline_3d
from carvefoundry.cam.gcode import (
    GrblPostSettings,
    render_grbl_program,
    write_grbl,
    write_grbl_program,
)
from carvefoundry.cam.job_workflows import TilingSettings, plan_tiles, resume_toolpath, tile_program, offset_toolpath_xy
from carvefoundry.cam.render_geometry import build_render_geometry
from carvefoundry.cam.preflight import check_preflight
from carvefoundry.cam.vector_ops import (
    geometry_center_drill,
    geometry_drill,
    geometry_engrave,
    geometry_face,
    geometry_pocket,
    geometry_profile,
    geometry_silhouette,
    geometry_vcarve,
)
from carvefoundry.core.project import ProjectItem, Stock
from carvefoundry.core.machine_profiles import MachineProfile
from carvefoundry.core.fixtures import Fixture
from carvefoundry.core.tools import Cutter

_LAST_UPDATE = 0.0


def report(fraction: float, message: str, *, force: bool = False) -> None:
    global _LAST_UPDATE
    now = time.monotonic()
    fraction = max(0.0, min(1.0, float(fraction)))
    if not force and fraction < 1 and now - _LAST_UPDATE < 0.08:
        return
    _LAST_UPDATE = now
    print(
        json.dumps({"type": "progress", "fraction": fraction, "message": message}),
        flush=True,
    )


@dataclass(slots=True)
class CamRequest:
    operation: str
    cutter: Cutter
    cut_type: str
    thickness_mm: float
    stock_width_mm: float
    stock_height_mm: float
    settings_by_item: list[tuple[ProjectItem, BasicCamSettings]]
    stock_settings: BasicCamSettings | None = None
    silhouette_settings: BasicCamSettings | None = None


@dataclass(slots=True)
class GcodeRequest:
    toolpaths: list[Any]
    path: str
    settings: GrblPostSettings
    mode: str = "export"
    resume_path_index: int = 0
    resume_move_index: int = 0
    resume_rewind: bool = True
    tile_settings: TilingSettings | None = None
    stock_width_mm: float = 0.0
    stock_height_mm: float = 0.0
    xy_zero: str = "bottom_left"
    stock: Stock | None = None
    machine_profile: MachineProfile | None = None
    fixtures: tuple[Fixture, ...] = ()


def _require_preflight(request: GcodeRequest, paths: list[Any]) -> str:
    if request.stock is None or request.machine_profile is None:
        raise ValueError("Preflight needs stock dimensions and a machine profile.")
    outcome = check_preflight(
        paths, request.stock, request.machine_profile,
        request.fixtures, request.settings,
    )
    report(0.12, "Preflight checked", force=True)
    if not outcome.safe_to_export:
        raise ValueError(outcome.format_report())
    return outcome.format_report()


def _local_fixture(fixture: Fixture, dx: float, dy: float) -> Fixture:
    return replace(
        fixture,
        x_min_mm=fixture.x_min_mm + dx,
        x_max_mm=fixture.x_max_mm + dx,
        y_min_mm=fixture.y_min_mm + dy,
        y_max_mm=fixture.y_max_mm + dy,
    )


def _generate_item(
    item: ProjectItem,
    settings: BasicCamSettings,
    job: CamRequest,
    progress,
) -> list[Any]:
    mesh = item.transformed_mesh()
    if mesh is None:
        return []
    operation = job.operation
    cutter = job.cutter
    cut_type = job.cut_type
    needs_cutout = (
        operation == "finish" and settings.relief_style is ReliefStyle.FULL_DEPTH
    )
    end = 0.85 if needs_cutout else 0.95

    def on_cam_progress(value: float, status: str) -> None:
        progress(0.05 + (end - 0.05) * value, status)

    progress(0.03, "Preparing geometry")
    if operation == "vcarve":
        path = geometry_vcarve(mesh, cutter, settings)
    elif operation == "drill":
        path = geometry_drill(mesh, cutter, settings)
    elif operation == "center_drill":
        path = geometry_center_drill(mesh, cutter, settings)
    elif cut_type == "Pocket" and operation in {"profile", "pocket", "engrave"}:
        path = geometry_pocket(mesh, cutter, settings)
    elif cut_type in {"On Path", "Outside", "Inside"} and operation in {
        "profile", "pocket", "engrave"
    }:
        if operation == "engrave" and cut_type == "On Path":
            path = geometry_engrave(mesh, cutter, settings)
        else:
            offset = {"On Path": "on", "Outside": "outside", "Inside": "inside"}[
                cut_type
            ]
            path = geometry_profile(mesh, cutter, settings, offset_mode=offset)
            if operation == "engrave":
                path.name = "Engrave"
                path.operation = "engrave"
    elif operation == "profile":
        path = geometry_profile(mesh, cutter, settings)
    elif operation == "pocket":
        path = geometry_pocket(mesh, cutter, settings)
    elif operation == "engrave":
        path = geometry_engrave(mesh, cutter, settings)
    elif operation in {"rough", "finish", "rest"}:
        path = finish_3d(
            mesh, cutter, settings, strategy=operation, progress=on_cam_progress
        )
    elif operation == "height_map":
        path = finish_3d(
            mesh, cutter, settings, strategy="finish", progress=on_cam_progress
        )
        path.name = "Height Map"
        path.operation = "height_map"
    elif operation == "waterline":
        path = waterline_3d(mesh, cutter, settings, progress=on_cam_progress)
    else:
        raise ValueError(f"Unsupported CAM operation: {operation}")

    paths = [path]
    if needs_cutout:
        progress(0.88, "Generating full-depth cutout")
        cutout_settings = replace(
            settings,
            overall_depth_mm=job.thickness_mm,
            relief_style=ReliefStyle.FULL_DEPTH,
        )
        paths.append(
            geometry_profile(
                mesh,
                cutter,
                cutout_settings,
                name="Full Depth Cutout",
                offset_mode="outside",
            )
        )
    for generated in paths:
        generated.source_item_id = item.item_id
        generated.source_item_name = item.name
    progress(1.0, "Object ready")
    return paths


def run_cam(job: CamRequest) -> dict[str, Any]:
    report(0.04, "Preparing CAM", force=True)
    generated: list[Any] = []
    if job.operation == "surface":
        settings = job.stock_settings
        if settings is None:
            raise ValueError("Surface settings were not provided.")
        path = geometry_face(
            job.stock_width_mm,
            job.stock_height_mm,
            job.cutter,
            settings,
            name="Surface",
        )
        path.source_item_id = "stock"
        path.source_item_name = "Stock"
        generated = [path]
    elif job.operation == "silhouette":
        meshes = []
        for index, (item, _) in enumerate(job.settings_by_item):
            mesh = item.transformed_mesh()
            if mesh is not None:
                meshes.append(mesh)
            report(0.05 + 0.3 * (index + 1) / max(1, len(job.settings_by_item)),
                   f"Preparing silhouette: {item.name}")
        if not meshes or job.silhouette_settings is None:
            raise ValueError("No geometry is available for the silhouette.")
        path = geometry_silhouette(meshes, job.cutter, job.silhouette_settings)
        path.source_item_id = "project-silhouette"
        path.source_item_name = "All design objects"
        generated = [path]
    else:
        groups: list[list[Any]] = []
        count = max(1, len(job.settings_by_item))
        for index, (item, settings) in enumerate(job.settings_by_item):
            start = 0.05 + 0.85 * index / count
            span = 0.85 / count
            def on_item(
                value: float, message: str, *,
                item_start: float = start,
                item_span: float = span,
                item_name: str = item.name,
            ) -> None:
                report(
                    item_start + item_span * max(0.0, min(1.0, value)),
                    f"{item_name}: {message}",
                )
            group = _generate_item(item, settings, job, on_item)
            if group:
                groups.append(group)

        report(0.92, "Optimizing multi-object order", force=True)
        current_xy = np.array((0.0, 0.0), dtype=float)
        while groups:
            best = min(
                range(len(groups)),
                key=lambda idx: (
                    float(
                        np.linalg.norm(
                            np.array(
                                (groups[idx][0].moves[0].x_mm,
                                 groups[idx][0].moves[0].y_mm)
                            ) - current_xy
                        )
                    ) if groups[idx] and groups[idx][0].moves else float("inf")
                ),
            )
            group = groups.pop(best)
            generated.extend(group)
            for path in reversed(group):
                if path.moves:
                    last = path.moves[-1]
                    current_xy = np.array((last.x_mm, last.y_mm), dtype=float)
                    break
    if not generated:
        raise ValueError("The geometry produced no toolpaths.")
    report(0.94, "Estimating runtime", force=True)
    render_geometry = build_render_geometry(generated)
    report(0.96, "Preview geometry ready", force=True)
    return {
        "render_geometry": render_geometry,
        "toolpaths": generated,
        "moves": sum(len(path.moves) for path in generated),
        "cut_mm": sum(path.cutting_distance_mm for path in generated),
        "rapid_mm": sum(path.rapid_distance_mm for path in generated),
        "minutes": sum(path.estimated_cutting_minutes for path in generated),
        "object_count": len({
            path.source_item_id for path in generated
            if path.source_item_id not in {None, "stock", "project-silhouette"}
        }) if job.operation not in {"surface", "silhouette"} else (
            0 if job.operation == "surface" else len(job.settings_by_item)
        ),
        "summary": " + ".join(sorted({path.name for path in generated})),
    }


def run_gcode(request: GcodeRequest) -> dict[str, Any]:
    toolpaths = request.toolpaths
    settings = request.settings
    report(0.05, "Preparing G-code", force=True)
    if request.mode == "preview_code":
        program = render_grbl_program(
            toolpaths,
            settings,
            progress=lambda fraction: report(
                0.05 + 0.62 * fraction,
                "Rendering viewer G-code",
            ),
        )
        report(0.70, "Indexing move references", force=True)
        lines = program.rstrip("\n").splitlines()
        commands = [
            index for index, line in enumerate(lines)
            if line.lstrip().startswith(("G0 ", "G1 "))
        ]
        offsets: list[int] = []
        command_offset = 0
        for index, toolpath in enumerate(toolpaths):
            command_offset += 1
            matched = commands[
                command_offset:command_offset + len(toolpath.moves)
            ]
            if len(matched) == len(toolpath.moves):
                offsets.extend(matched)
            else:
                fallback = commands[0] if commands else 0
                offsets.extend([fallback] * len(toolpath.moves))
            command_offset += len(toolpath.moves) + 1
            report(
                0.70 + 0.25 * (index + 1) / len(toolpaths),
                "Preparing viewer references",
            )
        return {"code_lines": lines, "move_code_lines": offsets}
    if request.mode == "preflight":
        if request.stock is None or request.machine_profile is None:
            raise ValueError("Preflight needs stock and machine profile.")
        outcome = check_preflight(
            toolpaths, request.stock, request.machine_profile,
            request.fixtures, settings,
        )
        return {
            "report": outcome.format_report(),
            "safe_to_export": outcome.safe_to_export,
            "files": [],
        }
    if request.mode == "resume":
        toolpaths = [
            resume_toolpath(
                toolpaths[request.resume_path_index],
                request.resume_move_index,
                safe_rewind=request.resume_rewind,
            ),
            *toolpaths[request.resume_path_index + 1 :],
        ]
    if request.mode == "tiles":
        tile_settings = request.tile_settings
        if tile_settings is None:
            raise ValueError("Missing tile settings.")
        tiles = plan_tiles(
            request.stock_width_mm,
            request.stock_height_mm,
            tile_settings,
        )
        output = Path(request.path)
        suffix = output.suffix if output.suffix.lower() in {
            ".nc", ".gcode", ".tap", ".cnc"
        } else ".nc"
        jobs: list[tuple[Path, list[Any], GrblPostSettings]] = []
        tile_count = len(tiles)
        for index, tile in enumerate(tiles):
            report(
                0.05 + 0.35 * index / max(1, tile_count),
                f"Checking tile {index + 1} / {tile_count}",
                force=True,
            )
            clipped = tile_program(toolpaths, tile, rebase=tile_settings.rebase_each_tile)
            if not clipped:
                continue
            options = settings
            if tile_settings.rebase_each_tile:
                options = replace(
                    settings,
                    x_offset_mm=(
                        -tile.width_mm / 2 if request.xy_zero == "center" else 0
                    ),
                    y_offset_mm=(
                        -tile.height_mm / 2 if request.xy_zero == "center" else 0
                    ),
                )
            tiled_path = output.with_name(
                f"{output.stem}_r{tile.row + 1}_c{tile.column + 1}{suffix}"
            )
            if request.machine_profile is None:
                raise ValueError("Tiling requires a machine profile for preflight.")
            # Every tile is checked in its *local* work envelope even if the
            # exported G-code keeps absolute global coordinates.
            local_paths = (
                clipped if tile_settings.rebase_each_tile else [
                    offset_toolpath_xy(path, -tile.x0_mm, -tile.y0_mm)
                    for path in clipped
                ]
            )
            local_fixtures = tuple(
                _local_fixture(f, -tile.x0_mm, -tile.y0_mm)
                for f in request.fixtures
            )
            tile_stock = Stock(
                tile.width_mm, tile.height_mm,
                request.stock.thickness_mm if request.stock is not None else 19.0,
                request.xy_zero,
            )
            result = check_preflight(
                local_paths, tile_stock, request.machine_profile,
                local_fixtures, options,
            )
            if not result.safe_to_export:
                raise ValueError(
                    f"Tile row {tile.row + 1} column {tile.column + 1}:\\n"
                    + result.format_report()
                )
            jobs.append((tiled_path, clipped, options))
        if not jobs:
            raise ValueError("No cutting moves intersect these tiles.")
        # Validate ALL tiles before writing ANY output files.
        paths: list[str] = []
        for index, (tiled_path, clipped, options) in enumerate(jobs):
            paths.append(str(write_grbl_program(
                clipped, tiled_path, options,
                progress=lambda fraction, tile_index=index, count=len(jobs): report(
                    0.45 + 0.50 * (tile_index + fraction) / count,
                    f"Writing tile {tile_index + 1} / {count}",
                ),
            )))
        if not paths:
            raise ValueError("No cutting moves intersect these tiles.")
        return {
            "files": paths,
            "summary": " + ".join(path.name for path in toolpaths),
            "moves": sum(len(path.moves) for path in toolpaths),
            "minutes": sum(path.estimated_cutting_minutes for path in toolpaths),
        }
    _require_preflight(request, toolpaths)
    report(0.15, "Writing G-code", force=True)
    if len(toolpaths) == 1 and request.mode == "export":
        saved = write_grbl(
            toolpaths[0],
            request.path,
            settings,
            progress=lambda fraction: report(
                0.15 + 0.72 * fraction, "Writing G-code"
            ),
        )
    else:
        saved = write_grbl_program(
            toolpaths,
            request.path,
            settings,
            progress=lambda fraction: report(
                0.15 + 0.72 * fraction, "Writing G-code"
            ),
        )
    report(0.95, "G-code written", force=True)
    return {
        "files": [str(saved)],
        "summary": " + ".join(path.name for path in toolpaths),
        "moves": sum(len(path.moves) for path in toolpaths),
        "minutes": sum(path.estimated_cutting_minutes for path in toolpaths),
    }


def main() -> int:
    if len(sys.argv) != 3:
        print("Expected request and result paths.", file=sys.stderr)
        return 2
    try:
        with Path(sys.argv[1]).open("rb") as handle:
            request = pickle.load(handle)
        if isinstance(request, CamRequest):
            result = run_cam(request)
        elif isinstance(request, GcodeRequest):
            result = run_gcode(request)
        else:
            raise TypeError("Unknown job request type.")
        with Path(sys.argv[2]).open("wb") as handle:
            pickle.dump(result, handle, protocol=pickle.HIGHEST_PROTOCOL)
        report(0.97, "Worker complete", force=True)
        return 0
    except Exception as exc:  # noqa: BLE001 - subprocess boundary reports all errors
        print(json.dumps({"type": "error", "message": str(exc)}), flush=True)
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
