# CarveFoundry

CarveFoundry is a native Linux CNC design and CAM application with a compact Photopea-style menu and tool rail. It is being built for Linux/Wayland first, with strong support for common CNC workflows including Onefinity-style GRBL machines.

## Project direction

CarveFoundry aims to cover the practical workflow people often use Easel for while giving more control over imported geometry, cutter definitions, 3D relief work, preview, optimization, and G-code export.

Planned and current areas include:

- 2D/2.5D design and CAM workflows
- SVG, DXF, image, STL, and G-code import paths
- first-class STL mesh import with retained geometry and mesh metadata
- stock and project setup
- cutter-aware CAM using the actual selected cutter profile
- roughing and finishing strategies for 3-axis CNC
- preview and simulation
- G-code export
- Linux/Wayland-native desktop behavior

## Cutter geometry

CarveFoundry is not designed around a ball-nose-only 3D finishing assumption. Cutter definitions model the actual cutter profile so flat end mills, ball noses, V-bits, engraving/conical tools, tapered ball noses, and future custom revolved profiles can be handled by the CAM engine.

## Compact left toolbar

The vertical rail prioritizes **interactive viewport tools**. Camera/Arcball
remains the default, followed by Select, Shapes, Line, Text, Pen, Measure XY,
and Draw Fixture. Move through the longer rail using the mouse wheel over
the icons; the top File/Edit/View menus retain the general commands.

The **Measure XY** tool measures a drag on the *stock-top Z0 plane*,
reporting length, signed ΔX, signed ΔY and the counterclockwise angle
from +X. The yellow measurement line remains until you click **Clear**
or open a different project. This is a **planar measurement**, not an
arbitrary 3D surface/mesh distance.

With **Draw Fixture**, set Top Z and extra cutter-clearance margin in the
contextual options bar, then drag an XY rectangle on the stock. The
result is a real project-owned preflight keep-out, visible in the viewport,
undoable and saved in .cf3d. The small arrow on its tool button opens
**Clamps and Fences** for editing, deleting or adding off-stock fence
regions that cannot be drawn within the stock rectangle.

Generate Toolpaths, Preview, CNC Preflight and G-code Export are
one-click buttons near the bottom of the scrollable rail. More advanced
CAM, cutter and machine controls remain in their flyout menus.

## Planar silhouette Union / Subtract / Intersect / Offset

Select two or more drawn planar shapes, then choose **Design → Vector → Union
Silhouettes**, **Subtract Silhouettes**, or **Intersect Silhouettes**. The
same commands are available from the small arrow on the Pen/Vector rail tool.
For Subtract, the first item in Layers order is kept and the other selected
items are removed from its XY outline. Select exactly one planar shape for
**Offset Silhouette**: a positive distance expands it and a negative distance
contracts it. Round, mitre and bevel corner styles are available.

The operation runs in a background worker and creates a new 2.5D shape, with
the selected depth below **stock-top Z0**. It preserves cutouts and separate
islands, hides the original objects without deleting them, and supports
Undo/Redo and .cf3d save/load. Recalculate toolpaths after making an edit.

**Scope:** these are XY-projected outline operations, not volumetric 3D
Booleans or editable vector control points. STL reliefs and objects tilted
out of the XY plane are not accepted. Source shapes that no longer overlap
may produce an empty Intersect/Subtract result; the existing design is
left untouched if a calculation fails.

## Workshop preflight and cutter stages

CarveFoundry stores clamps and fences as project fixture keep-out zones.
Open **Project → Clamps and Fences** to record the fixture XY footprint and
its top Z relative to the **stock top Z0**. For example, a 23 mm high left
fence measured from the *machine bed* alongside 19.4 mm thick stock has
top Z = 23 − 19.4 = **+3.6 mm**, not +23 mm. Fixture clearance is an extra
margin around the nominal cutter radius.

**Toolpaths → CNC Preflight** checks fixture collision, cutter travel, depth
and configured work-envelope limits. The same checks run automatically
before normal, resume and tiled G-code export; known errors block export.
Tiled programs are checked tile-by-tile in their own local work envelopes.

Multi-tool output is split into one G-code file per consecutive cutter stage.
Run these files in the numbered order, stop the machine between stages,
change the cutter and re-probe the new tool's Z before proceeding.

These are **offline checks**. CarveFoundry cannot determine actual
work-zero calibration, an unrecorded clamp, cutter holder collisions,
or where the machine is currently positioned. Always verify the program
and the physical setup before starting your CNC.

For proposed features that do **not** yet exist, see
[`docs/ROADMAP.md`](docs/ROADMAP.md). CarveFoundry does not expose fake
controls for those proposals.

## Native CAM core

The CPU-heavy mesh rasterization and cutter-contact calculations are implemented in Rust and exposed to the Python application through PyO3. The PySide6 UI, project model, cutter definitions, and orchestration remain Python.

The original readable Python implementations are intentionally kept as reference backends. This makes correctness problems much easier to isolate:

```bash
CARVEFOUNDRY_CAM_BACKEND=python carvefoundry
CARVEFOUNDRY_CAM_BACKEND=rust carvefoundry
```

The normal default is auto, which uses Rust when the compiled extension is available and otherwise falls back to Python. Packaged/development installs build the Rust extension automatically.

For module ownership and extension guidelines, see
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Development

Requires Python 3.12 or newer and a Rust toolchain new enough for PyO3 0.29 (Rust 1.83 or newer).

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e '.[dev]'
carvefoundry
```

Run the Python and Rust checks with:

```bash
ruff check src tests
pytest -q
cargo fmt --manifest-path rust/Cargo.toml --check
cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings
cargo test --manifest-path rust/Cargo.toml
```
