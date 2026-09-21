"""G-code-driven virtual machining: verify the posted commands before cutting stock.

Postprocessing and NC parsing are separate paths. The NC interpreter supplies
all simulated motions, including the actual extra retract and park commands,
instead of trusting the CAM operation's in-memory move list. Uses the existing
bounded 2.5D cutter-profile stock solver; no holder/undercut/machine claim.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from carvefoundry.cam.gcode import GrblPostSettings, render_grbl_program
from carvefoundry.cam.gcode_verify import verify_grbl_export
from carvefoundry.cam.stock_simulation import StockRemovalResult, simulate_stock_removal
from carvefoundry.cam.toolpath import Toolpath
from carvefoundry.core.machine_profiles import MachineProfile
from carvefoundry.core.project import Project


def simulate_posted_stock_removal(
    project: Project,
    machine_profile: MachineProfile,
    settings: GrblPostSettings | None = None,
    *,
    spacing_mm: float = 0.75,
    progress: Callable[[float, str], None] | None = None,
    compare_model: bool = True,
) -> StockRemovalResult:
    """Simulate NC-rendered, decoded and preflighted cutter stages in order."""
    if not project.toolpaths:
        raise ValueError("Generate toolpaths before virtual machining.")
    options = settings or GrblPostSettings()
    stages: list[list[Toolpath]] = []
    for path in project.toolpaths:
        if not stages or path.cutter != stages[-1][-1].cutter:
            stages.append([path])
        else:
            stages[-1].append(path)
    decoded_paths: list[Toolpath] = []
    for index, stage in enumerate(stages):
        if progress:
            progress(0.2 * index / len(stages), f"Decoding posted NC: stage {index + 1}")
        program = render_grbl_program(stage, options)
        verification = verify_grbl_export(
            program, stage, project.stock, machine_profile,
            tuple(project.fixtures), options,
        )
        if not verification.safe_to_export:
            raise ValueError(
                f"Posted NC stage {index + 1} rejected:\n"
                + verification.format_report()
            )
        decoded_paths.append(Toolpath(
            name=f"NC stage {index + 1}: " + " + ".join(p.name for p in stage),
            operation=stage[0].operation,
            cutter=stage[0].cutter,
            safe_z_mm=verification.decoded.initial_safe_z_mm,
            moves=list(verification.decoded.moves),
        ))
    if progress:
        progress(0.2, "Simulating verified G-code cutter sweeps")
    virtual_project = replace(project, toolpaths=decoded_paths)
    result = simulate_stock_removal(
        virtual_project, spacing_mm=spacing_mm,
        progress=(
            (lambda fraction, status: progress(0.2 + 0.8 * fraction, status))
            if progress is not None else None
        ),
        compare_model=compare_model,
    )
    return result
