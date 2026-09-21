# CarveFoundry

CarveFoundry is a native Linux CNC design and CAM application with a compact Photopea-style menu and tool rail. It is being built for Linux/Wayland first, with strong support for common CNC workflows including Onefinity-style GRBL machines.

## Install on Linux (KDE Plasma / Wayland)

CarveFoundry has a **user-local native desktop installer**. After installation
you can launch it from the KDE application menu or by typing `carvefoundry`
from a terminal; you do **not** need to activate a Python virtual environment.
No `sudo pip`, system Python modifications, or global PyTorch installs.

On Arch Linux, install the source-build prerequisites once:

```bash
sudo pacman -S --needed git python python-pip rust
git clone https://github.com/newnetmp3/CarveFoundry.git
cd CarveFoundry
bash scripts/install-linux.sh
```

This compiles the existing Rust CAM extension inside a private virtual
environment, installs the application as an editable Python package, and
registers a `CarveFoundry` KDE/GNOME menu entry with its icon. The first build
needs internet access and takes longer. This is a **native source-checkout
installer**, not a prebuilt Flatpak or a self-contained binary: keep the cloned
directory in place after installing. The application automatically reuses
`./.venv` if present, preserving installed PyTorch and model dependencies.
Otherwise it creates a private venv under
`${XDG_DATA_HOME:-~/.local/share}/carvefoundry/venv`.

**Already have a working CarveFoundry venv?** Register the app without touching
any Python/Rust packages:

```bash
cd /mnt/moar/Downloads/git/CarveFoundry
bash scripts/install-linux.sh --desktop-only
```

This uses the checkout's existing `.venv`. If yours is elsewhere, add
`--venv /absolute/path/to/venv`. This is the safest option when you already
have matching CPU/CUDA/ROCm AI packages installed.

To install optional local AI dependencies into the installer-managed venv for
a new installation, use `bash scripts/install-linux.sh --with-ai`. **Existing
GPU users:** this can replace matching PyTorch wheels; preserve your working
venv with `--desktop-only`, or use the
[official PyTorch installation selector](https://pytorch.org/get-started/locally/)
to choose matching CPU/CUDA/ROCm wheels. It does not package model weights;
those download on first use.

**Launch:**

```bash
~/.local/bin/carvefoundry
```

If `~/.local/bin` is already in your `PATH`, just run `carvefoundry`.
Or open the KDE application launcher and search for **CarveFoundry**.
For subsequent application updates:

```bash
cd /path/to/CarveFoundry
git pull --ff-only
bash scripts/install-linux.sh
```

Flatpak remains a future, separately tested distribution target, especially
for users on other Linux distributions. Its sandbox and GPU/AI dependency
handling need physical validation before replacing this native build.

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

## Locally generated AI bas-reliefs

Open **Model → Generate AI Bas-Relief…** (also in the Position tool flyout).
Choose **From image** for a local photograph/illustration, or **From text
prompt** to generate a reference image first. Choose relief width, height,
raised depth, backing thickness, grid detail (32–384 samples on the long
axis), foreground inversion, and smoothing. CarveFoundry saves a real,
watertight **STL in millimeters** at your selected path and automatically
imports it through the normal STL importer, ready to position, save in
`.cf3d`, and machine with cutter-aware CAM. Prompt generation also writes
`<STL stem>_source.png` beside the STL.

Install the optional, **locally executed** models on your Arch Linux Python
environment:

```bash
cd /mnt/moar/Downloads/git/CarveFoundry
git pull --ff-only
source .venv/bin/activate
python -m pip install -e '.[ai]'
python -c "import torch, torchvision; print('torch:', torch.__version__, 'torchvision:', torchvision.__version__)"
```

The AI extra installs **torchvision** as well as torch, Pillow, Transformers
and Diffusers. A missing Torchvision installation previously stopped
`AutoImageProcessor` before it could estimate depth. Install these in the
**same virtual environment** used to start CarveFoundry, then restart the app.
If the import check reports an error such as
`operator torchvision::nms does not exist`, torch and torchvision likely
have incompatible binary builds. Reinstall **matching** torch/torchvision
wheels for your CPU/CUDA/ROCm hardware, following the official PyTorch
installation selector at https://pytorch.org/get-started/locally/; do not
mix CPU, CUDA, ROCm, or system/pip builds. The optional dependency alone does
not guarantee GPU support.
**Depth Anything V2 Small** estimates relative image depth. For prompt mode,
**SD-Turbo** generates a reference image before depth estimation. Hugging Face
downloads their weights the first time you use each model, into your local
model cache. Later generation runs locally, and can run offline when the
weights are cached. No inference server, cloud generation account, or API key
is required. Image mode can run on CPU; prompt mode on CPU may be very slow
and needs substantially more memory. Consult SD-Turbo's current model license
for commercial-use terms.

The result is a **single-view, rectangular 2.5D heightfield relief** with
a flat back and solid edge walls, not a true multi-view 3D reconstruction.
Perspective, hidden surfaces, thin lettering, overlapping features and
background may require source-image cleanup or inversion. The ML predictions
are *relative*, not metric measurements; the selected millimeter depth
controls actual geometry. Check cutter reach, stock thickness, fixtures,
visual detail and preflight before cutting. The generated STL is placed with
its highest point at the current stock-top **Z0**, with stock-bottom-left XY
zero; change the object Z transform to recess its highest point if desired.
CarveFoundry keeps the UI responsive during generation and supports Cancel,
although model downloads and CPU jobs may consume substantial resources.

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

## Double-sided stock setup (front/back)

Choose **Project → Double-Sided Stock Setup…** (also in the Position flyout).
Assign the visible model objects for each face and choose the **physical**
turnover of the stock. Left/right turnover reverses X:
`X_back = stock_width - X_front`; top/bottom turnover reverses Y:
`Y_back = stock_height - Y_front`. Both resulting projects use the machine's
stock-bottom-left XY0 and **the exposed face's stock-top Z0**. The physical
stock thickness is unchanged in software. Geometry must fit the full stock
XY area and depth on each face; the wizard rejects an ambiguous/unsafe layout
rather than clipping it.

Select a parent directory and a **new** setup folder. CarveFoundry builds and
reload-validates `front.cf3d`, `back.cf3d`, and `SETUP_INSTRUCTIONS.txt`
in the background. The source project is not modified, and existing setup
folders are not overwritten. Back meshes have the reflection baked in;
edit the source project and repeat setup to change the back design. Fixture
rectangles remain in MACHINE coordinates (fixed fences are not mirrored).

**Operator steps:** Open each generated CF3D independently, generate that
face's toolpaths, preview, run fixture-aware CNC preflight and export. Machine
the front, stop and physically turn the wood against the registration stops,
secure it, confirm fence heights/clearances and work offsets, **re-probe the
newly exposed stock face as Z0**, then run the back setup. The wizard does not
control the machine, measure a physical turnover or guarantee alignment.

## Session multi-cutter machining job

In **Generate Toolpaths**, check **Append to existing machining job** when
adding rough, finish, detail or cutout passes. The CPU worker generates the
new operation, validates rough-before-finish and cutout-last dependencies,
and builds the complete combined preview. Failure leaves the previous job
untouched.

Use **Toolpaths → Machining Job Planner…** to inspect each actual operation,
its cutter, source part, estimated feed-only cutting time and move count;
reorder and remove operations. The existing GRBL export groups consecutive
same-cutter operations into separate numbered files when a cutter change
occurs. Re-probe Z after changing cutters. Mandatory preflight remains in
force for the entire exported plan.

**The generated paths/job order are session-owned; they are not yet persisted
inside .cf3d.** Regenerate toolpaths after reopening, and keep separate
front/back projects from two-sided setup.

## Batch production grid

Select a part or multiple component objects, then choose **Design → Arrange →
Batch Production Grid…** (also in the Position flyout). Specify copy count,
columns, gap and stock margin. The operation checks the full combined template
footprint against the stock and recorded clamp/fence rectangles using the
**currently selected cutter's radius**, then generates independently editable
stock-relative copies in a background worker. Originals are hidden, not
destroyed, and Undo/Redo restores them. Copies of multiple components are
grouped by finished part.

This is regular row/column layout, **not** irregular nesting or automatic
optimization of rotation/grain. The chosen cutter checks initial clearance;
use mandatory CNC preflight for every cutter in the finished multi-tool job.
X/Y Smart Value bindings must be removed from template objects so they cannot
overwrite calculated batch positions.

## Compact workspace and guided CAM form

The viewport's **Import / Fit / Inspector** shortcuts now move into the
always-visible **⋯** menu automatically when the canvas is narrow. The object
selector, CAM status and toolpath-generation command remain visible; no
feature is lost when you resize the window or expand the Inspector. The menu
also opens Layers and the Guided CNC Job.

The Inspector's **Position, Rotation, Size, Scale**, and Object/Gizmo
settings are compact expandable sections. Position and Size open by default;
Rotation, Scale, and advanced setup can remain collapsed. Your expand/collapse
choices persist across launches. Choosing **Model → Transform → Rotate/Size/
Scale/Position** reopens the correct section and takes the cursor to its
numerical field, so hidden controls do not interfere with menu workflows.

**Generate Toolpaths** has a side rail linking directly to Source, Cutter,
Strategy, Depth, Motion/Safety, Tabs, Stock-Aware Rest, and Readiness. Hide the
rail with **Hide steps** on smaller displays; the full form and all option
help remain available. A fixed context strip displays the chosen operation,
cutter, number of visible models and actual stock dimensions as you edit.
The existing live validation, cancellation, worker process and mandatory
export preflight are unchanged.

**Guided CNC Job** shows a progress indicator for *project readiness checks*
and a **Go to next action** shortcut. It avoids repainting unchanged checks
while open. Readiness is not physical proof of machine setup or confirmation
that the named steps were manually performed.

## Stock-aware rest machining

After generating a 3D Rough or Finish operation, reopen **Generate
Toolpaths → 3D Rest** (or **Guided CNC Job → Rest Cleanup**). This operation
**requires and appends to the existing machining job**. CarveFoundry simulates
stock after all prior cutter stages and generates cutter-contact-compensated
serpentine cleanup **only where the new cutter is predicted to remove residual
material above the selected threshold**. Typical workflow: rough with a
1/4-inch bit, then rest cleanup with a smaller ball nose; inspect the
completed path in Preview and rerun mandatory CNC preflight before export.
The existing job remains unchanged if the model has no sampled leftover.

Set **Minimum leftover height** (default 0.15 mm) to ignore negligible
material, and **Stock simulation spacing** (default 0.75 mm) to determine
the smallest leftover features the simulation can detect. This is sampled
**2.5D** rest machining—not a live measurement of the actual workpiece.
It cannot see cuts made outside CarveFoundry, real cutter deflection, the
holder or unrecorded hold-downs. Increase simulation resolution for small
features; the memory/sample caps reject overly fine setups instead of
silently guessing. Each design object needs a preceding operation, and
a detached part cannot be rest-machined after a full-depth cutout.
New cutter stages remain separate GRBL programs requiring manual cutter
change and stock-top Z re-probe; export still performs its own fixture-aware
preflight.

## Sampled material-removal simulation

Choose **Toolpaths → Simulate Material Removal…** after generating a machining
job. This is separate from the existing backplot/path animation. CarveFoundry
simulates each cutting/plunge move, in cutter-stage order, against a regular XY
grid of remaining stock using the selected flat, ball, V/cone, tapered ball or
custom radial cutter profile. G0 rapid moves are not treated as cuts. The
standalone viewer shows remaining stock height, approximate removed volume by
operation and (when a 3D model is present) deviation from the top model
surface: blue = remaining material above target, red = cut below target.
Choose XY sample spacing before calculation; the application rejects overly
large grids/sampling workloads instead of silently degrading resolution.
Long simulations support cancellation.

**Scope:** This is sampled **2.5D material removal**, not exact continuous
volumetric CSG. It cannot represent undercuts, physical holder contact,
runout, machine acceleration, the actual work offset or fixtures not recorded
in the project. Model comparison uses the *top surface* of visible 3D objects:
intentional 2D pocket/cutout operations can be below that surface. Simulated
volume is approximate. Always run mandatory CNC preflight before exporting.

## Automatic project recovery

CarveFoundry saves a **separate complete CF3D recovery checkpoint** after
approximately one minute without further editing. This does not replace your
manually saved file and does not clear the unsaved-change indicator. On the
next visible startup, existing checkpoints appear in a Restore/Discard dialog;
they remain available until successfully saved or deliberately discarded.
The File menu also offers **Recover Autosave…**, **Save Recovery Checkpoint**
and an **Automatic Recovery Checkpoints** toggle.

The recovery area lives in your normal Linux application-data directory, not
in the project folder. Checkpoints have atomic metadata, SHA-256 verification
before restore and bounded retention. Restoring loads a normal project as
**unsaved changes**. If the source file changed since the checkpoint, the
restore dialog warns you. Only an explicit normal **Save** can overwrite
the source project. A deliberate Discard of unsaved work removes that
session's recovery checkpoint. The checkpoint preserves the same design,
stock, fixture and mesh information as a normal CF3D Save; session-owned
generated toolpaths and machining-job order must be regenerated after restore.

## Direct Selection — real editable pen/line nodes

Newly drawn **Pen Strokes and Lines** now retain editable centerline XY knots
alongside the cutter-facing 3D mesh. Select ONE eligible object, then use the
new **Direct Selection** tool in the left rail or **Design → Draw/Vector →
Direct Selection**. Green knot crosses appear in the OpenGL viewport. Drag a
knot on the stock plane (Top view recommended); a modeless inspector also
allows exact XY coordinates, midpoint insertion and node deletion. All edits
rebuild actual mesh geometry, invalidate stale CAM paths, support Undo/Redo,
and persist the knot data inside normal CF3D files. Duplication, copy/paste
and the batch grid retain the independent vector metadata.

This feature does **not** pretend that arbitrary imported STL, raster traces
or baked silhouette/Boolean meshes contain editable vector control points.
Existing projects whose strokes were saved before this update lack retained
nodes; newly drawn Pen/Line objects have them. Paths with X/Y tilt must be
untilted before XY knot editing. Edited Line end caps become rounded like
other polyline strokes.

## Guided CNC workflow

Use the new **Guided CNC Job** button next to Save/Undo, or select
**Project → Guided CNC Workflow…**. The modeless eight-step guide follows:
stock and work zero, machine profile, physical fences/clamps, design objects,
CAM generation, job/preview review, **actual mandatory CNC preflight**, then
per-cutter G-code export. Every button launches the existing real command.
Its step statuses update from the current stock, fixture, machine and generated
toolpaths. Preflight completion is linked to the *exact current setup*;
changing stock, fixtures, machine settings or toolpaths invalidates the
guide's green preflight status. Export remains protected by the independent
fixture-aware preflight that already runs during export.

The guide is an aid for human setup, not automatic physical verification:
check the actual stock registration, Makita/Onefinity holder and fences,
re-probe stock-top Z0 after tool changes, and repeat the full guide separately
on each side of a double-sided project.

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

## Native Wayland hardware acceptance

Automated CI tests run offscreen and cannot prove physical KDE Plasma/Wayland
pointer delivery, input focus, real OpenGL rendering or GPU performance. The
hardware acceptance matrix and native-input recorder are in
[docs/WAYLAND_QA.md](docs/WAYLAND_QA.md). Run it locally after viewport,
gizmo, toolbar and Inspector changes; do not report those behaviors as
hardware-tested based on headless CI alone.

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
