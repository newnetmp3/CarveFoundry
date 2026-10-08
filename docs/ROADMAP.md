# CarveFoundry implementation roadmap

This file separates **working, integrated features** from proposals. A roadmap
entry is not a claim that a control or algorithm is available. Update this file
in the same pull request whenever a roadmap capability is actually delivered.

## Recently completed roadmap milestones

- **Persistent object-aware machining operations — PR #59 / PR #60:** Native
  projects retain machining intent separately from generated motion. The
  Inspector exposes ordered operations with stable IDs, source-object links,
  cutter/settings, READY / RECALCULATE / DISABLED state, edit, reorder,
  duplicate, delete, enable/disable and selective background recalculation.
  Preview/export remain blocked while any enabled stage is stale or missing
  generated motion.
- **Analytic native vector foundation — PR #61:** Retained editable
  paths support line, circular-arc and cubic Bezier segments, deterministic
  curve tessellation, exact segment splitting, CF3D persistence, Direct
  Selection segment editing and node/midpoint/arc-center/intersection snapping.
  Planar retained vectors feed Profile, Pocket, Engrave and V-Carving directly
  at the 2D CAM boundary instead of first reconstructing their contours from
  triangles.
- **Vector topology editing — PR #62 (upon merge):** Direct Selection can
  close an open contour, open a closed contour at a chosen node, split an open
  path at an interior node, and join two selected open vector paths within the
  configured snap tolerance. Arc and cubic-Bezier segments remain analytic.
  Split/join update persistent CAM source-object IDs and participate in normal
  Undo/Redo and stale-operation invalidation.

## Workshop-safe output — implemented in PR #16 (upon merge)

- Project-owned rectangular fixture keep-outs with editable XY extents, top Z,
  clearance, visible viewport outlines, native CF3D persistence, and Undo/Redo.
- Cutter-radius-aware segment/fixture preflight, stock depth, configured machine
  travel and parking movement checks. Normal, resume and tiled exports are
  blocked when preflight detects an error. Preflight is also available as a
  separate report-only command.
- Dedicated G-code file per consecutive cutter stage rather than silently
  switching cutters inside one GRBL file. Manual cutter change and Z re-probe
  between files are required.
- Project-window open/save moved to workers; Save-before-New/Open/Close defers
  the requested action until the save succeeds.

Preflight is deliberately conservative and offline. It cannot know the actual
work offset, controller travel origin, hold-downs omitted from the project,
cutter holder envelope, spindle state, or where the machine is currently parked.
It must not be described as a guarantee of physical safety.

## Rust-native UI replacement — new priority

The product direction is now a native Rust desktop interface using egui/eframe,
**not a cosmetic PySide6 makeover**. The first isolated implementation lives in
`rust-ui/` and provides real vector shapes, direct selection, rectangle arrays,
polygon-aware first-fit stock placement, editable Rust layout JSON and SVG
interchange. It is intentionally an **experimental companion**, not a completed
UI replacement, and the legacy CNC workspace remains the sole validated
CF3D/CAM/preflight/export path until a cross-language engine bridge is proven.

Priorities based on gaps in production CNC tooling are sheet layout/nesting,
reusable toolpath templates, inlay plug/pocket workflows, merged/arrayed
operations, vector texturing, extension/gadget APIs and safe batch production.
See [Rust UI capability and acceptance plan](RUST_UI_GAP_PLAN.md).
No source workspace from this native Rust layout may be mistaken for G-code.
PR #84 merged the first Rust-native layout window after Cargo geometry
tests, Linux release compilation and strict Clippy CI passed. PR #85 merged
a read-only CF3D vector-outline and stock snapshot adapter after both Python
CI lanes passed. PR #86 merged the **Import vectors (read-only)** Rust UI workflow and a
separate KDE launcher, with passing native Rust geometry/Clippy/release tests,
shell syntax checks and Python 3.12/3.14 CI. This is explicitly **not** a
read/write CF3D engine bridge; it does not retain CAM or fixture metadata
inside the Rust layout, generate NC programs or replace full CNC preflight.
The original PySide6 application stays available as the CNC authority.
The current in-progress Rust Studio milestone adds bounded **multi-sheet
polygon-first-fit nesting**: asynchronous planning, per-sheet read-only preview,
optional 90° rotation lock, fixed stock margins/cutter gap, versioned plan
JSON and independent sheet SVG files. This is not a stock-optimized algorithm
nor a full CNC job: physical fixtures, grain orientation metadata and actual
toolpath safety remain the verified Python CAM application's responsibility.
Mark complete only after Cargo tests, Clippy, Linux build and Python CI pass.

## Parallel architecture track — gradual Rust migration (planned)

PR #81 merged the expanded native raster parity benchmark with sloped,
sparse and overlapping triangle scenes. Both Python CI lanes passed and
full-array numerical equivalence checks are available. These results do
not establish speed improvements on the developer's machine, and cutter
contact/stock-sweep performance and parity remain separate future steps.
PR #83 merged an opt-in Python/Rust cutter-contact benchmark for smooth,
missing-data and ridge height fields with flat and ball-like radial footprints.
Python 3.12/3.14 CI passed; native parity tests run when the PyO3 extension is
available. It changes no production CAM code and does not establish real
hardware speedups or memory savings.

**Keep shipping the native 2D CAD / snapping / CAM roadmap above and below.**
The Rust migration is a parallel, opportunistic modernization track, **not**
a prerequisite for the next CAD feature and not a reason to halt current PRs.

**Existing foundation:** `rust/` already builds a PyO3/maturin extension with
Rayon and NumPy interoperability. Its implemented kernels currently accelerate
specific raster/contact calculations. The UI and most application logic remain
Python/PySide6. Do not describe the percentages below as measured repository
language composition.

**Target direction:** Prefer Rust for reliable geometry, motion planning,
validation and long-running numerical work while incrementally replacing the presentation layer with a Rust-native
Wayland interface, and retaining the established Python CNC runtime until
CF3D, CAM safety, and controller workflow parity are independently verified. An eventual approximately 80–85% Rust
architecture is an aspirational design choice, **not** a delivery milestone,
guaranteed speedup, or a commitment to rewrite the entire GUI. Keep Python
AI/PyTorch inference initially.

### Incremental migration order

1. **Benchmark and define compatibility contracts — in progress:**
   The initial raster kernel benchmark is available in
   `scripts/benchmark_native_kernels.py`: deterministic triangles, grid sizes,
   Python-reference/native parity checking, repeated warmup/median wall-time
   samples, and JSON output. Results must be measured on target hardware; CI
   asserts behavior, not speed. Expand to CAD edit, V-Carving, pocketing, 3D
   finishing, rest machining, simulation and export workloads, including peak
   memory and Python/Rust transfer overhead. Capture numerical tolerances and
   representative correct outputs before each conversion.
2. **Native vector geometry — planned:** Migrate analytic line/arc/cubic
   evaluation, subdivision, contour topology, geometric snapping and
   trim/extend/fillet primitives behind the existing Python-facing model/API.
   Keep UI, project serialization, and machining source UUID semantics stable.
3. **2D/2.5D CAM and path optimization — planned:** Move independently tested
   profile, pocket, engraving, V-Carving and rest/ordering kernels one strategy
   at a time, preserving cutter-aware input and output semantics.
4. **Simulation and verified NC safety — planned:** Port cutter-profile sweeps,
   sampled stock removal and collision/preflight calculations with independent
   Python-versus-Rust parity and fail-closed posted-G-code verification.
   No simulation replacement may silently weaken safety checks.
5. **Mesh, project and import cores — planned:** Benchmark and selectively
   migrate mesh processing, project serialization/history, and vector/import
   parsing while preserving compatibility with existing `.cf3d` projects
   and Undo/Redo.
6. **Optional application-level Rust expansion — evaluate later:** Consider
   background scheduling, plugin ABI and native UI only after core migration
   proves useful and KDE Plasma/Wayland behavior remains stable. Do not
   displace the functional Qt interface solely to maximize Rust percentage.

### Acceptance gates for *each* conversion

- Keep Python-facing interfaces and native CF3D file compatibility stable,
  including project roundtrips and Undo/Redo.
- Test golden geometry, numerical tolerances, toolpath ordering, cutter stages,
  operation stale/ready state and emitted/decoded G-code. Retain a trusted
  Python reference or reproducible golden cases until parity is demonstrated.
- Run Rust unit/property tests, `cargo fmt`, strict Clippy, Python 3.12/3.14
  CI and integration/regression tests. Benchmark speed **and memory**, including
  PyO3 transfer costs; do not claim performance improvements without evidence.
- Preserve stock XY0/Z0 conventions, fixture/rapid clearance, offline
  preflight, manual tool-change and Z re-probing, and fail-closed export.
- Migrate modules in small, reversible PRs, preferably alongside the relevant
  CAD/CAM feature. Keep explicit Python fallback where practical during
  validation; remove it only with adequate independent coverage.
- Update **this roadmap** and `docs/HANDOVER.md` in each PR, distinguishing
  implemented, validated, and planned Rust functionality.

## Further development — do not treat proposals as implemented

1. **Live, managed CNC sender:** GRBL planner/serial response tracking, real
   machine position, feed overrides, pause, stop, recovery and alarm handling;
   design for interrupted transfers and controller disconnection.
2. **Exact volumetric simulation beyond the sampled, verified-NC stock preview:**
   The top-down 2.5D viewer now decodes and preflights exported GRBL motion,
   models actual cutter radial profiles, approximate removed volume and
   top-surface deviation. It does not validate arbitrary unsupported NC.
   Accurate undercuts, continuous CSG, holder collision and live machining
   verification remain unimplemented.
3. **Robust job recovery:** immutable job manifests, machine state/work-zero
   and tool identification, verified safe entry and machine-aware resumption.
4. **Persistent multi-tool planning and dependencies — substantially
   implemented:** Native CF3D retains both calculated toolpaths and ordered
   persistent machining-operation definitions. Operations store stable IDs,
   source-object links, cutter/settings, enabled state and recalculation state.
   The Inspector can edit, reorder, duplicate, delete, disable and selectively
   recalculate operations; geometry/settings changes invalidate the earliest
   affected stage and dependent downstream stages while retaining earlier valid
   motion. Preview/export fail closed while any enabled operation is stale or
   missing motion. Remaining work is richer dependency graphs beyond ordered
   downstream invalidation, exact stock-state dependency reasoning, reusable
   operation/toolpath templates and automatic global multi-tool optimization.
5. **V-carving inlays:** matched plug/pocket geometry, taper, gap, insertion depth,
   and fit/tolerance validation.
6. **Beyond sampled stock-aware rest:** 3D Rest now simulates all previously
   generated cutter stages and retains only selected-cutter cleanup passes at
   sample centres with residual material above an operator-set threshold.
   It appends to the existing ordered job, refuses no-op rest, and requires
   actual preceding operations for each model. Exact volumetric stock-aware
   clearing, variable cutter-engagement feeds and collision/holder simulation
   remain future work.
7. **Extended native vector editing, group cutouts and text-on-path —
   in progress:** Direct Selection edits retained Pen/Line anchors with viewport
   dragging, exact coordinates, insertion/deletion, Undo/Redo and CF3D
   persistence. PR #61 adds analytic line, circular-arc and cubic Bezier
   segments, exact curve splitting, numeric arc/Bezier segment editing, and
   snapping to vector nodes, segment midpoints, arc centers and intersections.
   Planar retained vectors feed the 2D Profile, Pocket, Engrave and V-Carving
   CAM boundary directly, with mesh projection retained as a fallback.
   PR #62 adds close/open-at-node, split-at-node and two-object endpoint join
   operations with CAM source retargeting.
   PR #63 adds validated immutable cubic control editing; PR #64 adds native
   viewport cubic handles, anchor guide lines, hit testing and drag-to-edit
   through the existing Undo/Redo and CAM invalidation workflow. Both Python
   CI lanes passed for PR #64; physical KDE/Wayland interaction testing is
   still outstanding. PR #65 adds optional stock-origin grid snapping;
   PR #68 applies geometry/grid snaps to cubic handles; PR #69 adds directional
   tangent/normal projection math; PRs #70-71 add Shift angle increments and
   in-viewport active constraint feedback.
   PR #73 aligns cubic handles with the adjoining segment's
   tangent via Ctrl or its perpendicular via Ctrl+Shift, with typed visual
   markers and retained Undo/CAM invalidation. This is limited to cubic
   handle editing where an adjacent segment provides a reference; it is NOT
   general all-tool tangent snapping or automatic curvature continuity.
   PR #73 CI passed both Python 3.12 and 3.14; physical KDE/Wayland
   modifier interactions still require real-device verification.
   Remaining native vector-CAD work includes wider draw-time snapping,
   geometric live snap indicators, intersection-aware trim/extend,
   fillet/chamfer, editable circle/ellipse/polygon primitives, retained
   SVG/DXF contours, group
   cutouts and text-on-path.
   PR #74 adds exact fractional *open endpoint trimming*
   to line, arc, and cubic paths with Direct Selection UI and Undo/CAM
   invalidation. This is not yet intersection-aware trim/extend, and it
   was merged after passing CI. The next in-progress milestone extends open
   straight-line endpoints by a specified distance without affecting their
   other segments, through Direct Selection and Undo/CAM invalidation. It
   does not extrapolate arcs or cubic curves. PR #75 is merged after CI.
   Finite straight-segment trim/extend intersection geometry is now in
   development, with explicit trim/extend direction and bounds validation.
   PR #76 merged the strict finite-line intersection geometry. The next
   in-progress Direct Selection workflow supports fitting against one chosen
   straight segment of a second selected vector, converting from its world
   coordinates to the source's local coordinate space. That UI remains
   unverified until tests and CI pass. General analytic curve intersections
   and direct mouse target picking remain future work. PR #77 merged the
   two-vector finite line trim/extend interface after passing CI.
   The next **in-progress**, unmerged step adds an equal-setback analytic
   chamfer for open path interior line/line corners, using Direct Selection
   and the retained-history/CAM invalidation lifecycle. PR #78 merged
   an equal-setback line/line chamfer for open-path interior corners and
   PR #79 merged an exact circular-radius line/line fillet with retained
   analytic arc geometry. Both are integrated with Direct Selection,
   Undo/Redo, CAM invalidation and Python 3.12/3.14 CI regression coverage.
   PR #80 merged closed-contour line/line corner chamfer and fillet,
   including seam-aware regression coverage, with both Python CI lanes green.
   PR #82 merged the Direct Selection inspector into five scrollable
   tabs (Geometry, Snapping, Topology, Corners, Endpoints), retaining the
   selected node and callbacks and persisting the active tab. Both Python
   CI lanes and the offscreen UI regressions passed.
   Curved junctions, general live snap indicators and physical KDE/Wayland
   pointer validation remain outstanding.
   Planar Union/Subtract/Intersect and signed Offset currently produce
   Z0-topped 2.5D watertight results rather than retained analytic contours or
   true volumetric 3D mesh Booleans.
8. **Multi-component 3D relief compositing and editable heightmap layers.**
9. **Machine-integrated double-sided workflow:** Stock-registered two-face
   setup now partitions visible front/back models, reflects the chosen physical
   flip axis, validates XY/Z containment, and writes two verified CF3D projects
   and a setup checklist in a new folder without touching source geometry.
   Each face must separately generate, preflight and export G-code. Live fixture
   detection, physical registration testing, machine-aware flip verification,
   and automatic multi-face G-code execution are NOT implemented.
10. **Optimized batch production/nesting:** Editable regular-grid duplication
    now supports selected multi-part templates, cutter-radius stock margins,
    recorded fixture clearance, hidden originals and Undo/Redo. Irregular
    silhouette nesting, optional grain rotation, serial text and automatic
    global multi-tool optimization remain future additions.
11. **Spoilboard mapping and probe-backed height compensation** with verified
    source/units and explicit controller dependencies.
12. **Material presets, first-run machine wizard and packaged Linux releases.**
13. **Extended recovery features:** Complete CF3D idle checkpoints,
    checksum verification, source modification warnings, restore/discard
    choice, user-controlled normal Save, and bounded retention now exist.
    Persistent Undo history, cross-device sync and cloud backups remain
    unimplemented.

For each item, do not add a button or a stub until calculation, UI,
persistence (where needed), export/sender behavior and regression tests can
be delivered together.
