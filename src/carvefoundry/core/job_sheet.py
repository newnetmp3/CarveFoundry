"""Self-contained printable operator setup sheet for a generated CNC job.

The sheet is a record of CONFIGURED inputs, not a machine-readiness certificate.
Physical setup checks remain unchecked for the operator to complete.
"""
from __future__ import annotations

from html import escape
from itertools import groupby

from carvefoundry.core.machine_profiles import MachineProfile
from carvefoundry.core.project import Project


def _h(value: object) -> str:
    return escape(str(value), quote=True)


def job_sheet_html(project: Project, machine: MachineProfile) -> str:
    """Create deterministic letter-sized print markup without running CAM."""
    stock = project.stock
    paths = project.toolpaths
    if not paths:
        raise ValueError("Generate toolpaths before making an operator setup sheet.")

    stages: list[tuple[str, int, float, float]] = []
    for cutter, group in groupby(paths, key=lambda path: path.cutter.name):
        selected = list(group)
        stages.append((
            cutter,
            len(selected),
            sum(path.estimated_cutting_minutes for path in selected),
            max(path.safe_z_mm for path in selected),
        ))

    rows = "".join(
        "<tr>"
        f"<td>{index}</td><td>{_h(cutter)}</td>"
        f"<td>{number}</td><td>{minutes:.1f} min</td>"
        f"<td>+{safe_z:g} mm</td>"
        "</tr>"
        for index, (cutter, number, minutes, safe_z) in enumerate(stages, 1)
    )
    fixtures = "".join(
        "<tr><td>" + _h(fixture.name) + "</td><td>"
        + f"X {fixture.x_min_mm:g}…{fixture.x_max_mm:g}; "
        + f"Y {fixture.y_min_mm:g}…{fixture.y_max_mm:g}; "
        + f"top Z {fixture.top_z_mm:g}; margin {fixture.clearance_mm:g} mm"
        + "</td></tr>"
        for fixture in project.fixtures
    ) or "<tr><td colspan='2'>None recorded — check all physical clamps/fences.</td></tr>"
    total = sum(path.estimated_cutting_minutes for path in paths)
    return f"""<!doctype html><html><head><meta charset="utf-8">
<style>
body {{ font-family: sans-serif; font-size: 10pt; color: #142333; }}
h1 {{ font-size: 19pt; margin-bottom: 2pt; }}
h2 {{ font-size: 12pt; margin-bottom: 4pt; border-bottom: 1px solid #999; }}
p {{ margin: 5pt 0; }}
table {{ border-collapse: collapse; width: 100%; margin: 5pt 0 12pt; }}
th,td {{ border: 1px solid #9aa; padding: 5pt; text-align: left; }}
th {{ background: #eaf0f1; }}
.note {{ border: 1px solid #789; padding: 6pt; }}
</style></head><body>
<h1>CarveFoundry · CNC Job Setup Sheet</h1>
<p><b>Project:</b> {_h(project.name)} &nbsp; <b>Machine profile:</b>
{_h(machine.name)}</p>
<h2>1 · Stock and coordinates</h2>
<p><b>Wood:</b> {stock.width_mm:g} × {stock.height_mm:g} ×
{stock.thickness_mm:g} mm (X × Y × thickness)</p>
<p><b>XY0:</b> bottom-left stock registration corner;
<b>Z0:</b> stock TOP. Machine home is NOT work zero.</p>
<p><b>Configured travel:</b> {machine.work_x_mm:g} ×
{machine.work_y_mm:g} × {machine.work_z_mm:g} mm</p>
<h2>2 · Cutter stages, in programmed order</h2>
<table><tr><th>Stage</th><th>Install cutter</th><th>Operations</th>
<th>Cut-only estimate</th><th>Safe Z</th></tr>{rows}</table>
<p>Estimated cutting: {total:.1f} minutes, excluding rapid moves, pauses,
setup, and tool changes. After EACH cutter change stop and re-probe
stock-top Z0. Execute only the corresponding exported NC program.</p>
<h2>3 · Recorded clamps / fences (not physically verified)</h2>
<table><tr><th>Keep-out</th><th>Recorded coordinates relative to stock</th></tr>
{fixtures}</table>
<h2>4 · Physical setup checklist — operator must confirm</h2>
<p>☐ Verify actual wood size and secure all clamps/fences.</p>
<p>☐ Verify the selected NC file, installed cutter, usable bit length and router speed.</p>
<p>☐ Verify machine home, the configured work offset, XY origin and actual Z0.</p>
<p>☐ Check holder, collet, clamps and fences clear ALL moves and first rapid.</p>
<p>☐ Run independent posted-code preflight; inspect full simulated carve.</p>
<p>☐ Confirm any cutout has adequate holding tabs or equivalent workholding.</p>
<p>☐ Confirm dust collection, protective equipment and stop access.</p>
<p>☐ After each stage: stop spindle, change cutter and re-probe Z0.</p>
<p class="note"><b>Important:</b> This setup sheet reflects the project
at the time of printing. It is not proof of safe machining and does not
validate the controller's live work offsets, stock registration, hold-downs,
spindle RPM, holder collisions or actual machine position. Regenerate the
sheet and re-run independent posted-code preflight whenever the job changes.</p>
</body></html>"""
