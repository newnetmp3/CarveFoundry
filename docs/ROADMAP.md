# CarveFoundry — pure Rust reboot roadmap

**Direction:** entirely new Rust desktop, Rust-owned project schema, and
incrementally built Rust CAD/CAM. Do not port GUI functions one by one from the
old Python application. Reimplement useful workflows with tests and stable
interfaces, informed by the archived code, without depending on it at runtime.

## Milestone gates

| Phase | Deliverable | Acceptance | State |
|---|---|---|---|
| R0 | Pure Rust monorepo + working 2D canvas | Cargo workspace, geometry, stock/fixture model, versioned files, undo/redo, CI, native window | **Merged to main via PR #99; Rust CI passed; KDE/Onefinity QA pending** |
| R1 | Professional vector CAD | Retained line/arc/cubic paths, node/handle editing, snapping, Bézier preservation, real fonts/text, SVG/DXF, layers/grouping, trim/extend, fillet/chamfer | **R1a merged PR #101, Rust CI passed:** retained curves, stable nodes, typed Undo/Redo, UI direct editing; remaining text/import/trim/layers pending |
| R2 | 3D geometry workspace | Real mesh load/store, multi-part layers, camera/gizmos, material relief, procedural image-to-depth input, robust Wayland viewport QA | Planned |
| R3 | Native job definition and tool library | Physical cutter profiles and materials, ordered typed CAM operations, UUID-linked sources, per-stage invalidation/dependency graph | Planned |
| R4 | Rust 2D/2.5D CAM | Profile, pocket, engraving, V-carving, inlay, contour/texturing, clearance vs cutter geometry, operation arrays, performance parity | Planned |
| R5 | Rust 3D CAM and preview | Roughing, finishing, rest, native stock removal visualization, collision/contact checks and deterministic benchmarks | Planned |
| R6 | CNC-critical safeguards and export | Fixture/holder-aware posted NC preflight, stock/tool/machine bounds, Z clearance, cutter-specific NC stages, re-probe prompts, fail-closed output | Planned |
| R7 | Production reliability + physical QA | Atomic recovery, packaged Linux build, source/project migration tool, golden projects, independent NC validation, KDE/Wayland and Onefinity scrap tests | Planned |

## Immediate next milestones

1. **R0 QA and usability:** Rust unit tests, strict Clippy and release build passed in [run 37862945581](https://github.com/newnetmp3/CarveFoundry/actions/runs/37862945581). Next improve exact vector selection,
   fixture editing/removal and save/load error feedback; measure native UI
   behavior on KDE Plasma/Wayland before declaring R0 fully accepted.
2. **R1 analytic vector data core (merged PR #101, CI green):** persistent segment enum (line, circular
   arc, cubic Bézier), exact edge operations, stable node IDs and Undo, full
   schema roundtrip. Avoid sampling analytic curves as the canonical source.
3. **R1 editor UI (initial slice merged PR #101):** Direct Selection mode and separate whole-object mode,
   numeric coordinates, live snaps and keyboard modifiers, layers, SVG/DXF.
4. **R2 mesh project store + live 3D view**, after successful R1 milestones.
5. **R3/R4 typed CNC jobs**, no NC emitter until R6 passes independent tests.

## Critical constraints learned from earlier versions

- XY0 = stock bottom-left; Z0 = stock top. Store fixtures' top Z relative
  to stock top (bed fence height minus stock thickness where appropriate).
- A side fence can extend outside nominal stock XY. Keep-out validation
  must allow those negative coordinates.
- Each cutter stage must have distinct generated NC output. Manual tool
  changes need Z re-probing. Never silently switch physical cutters.
- Treat every relevant design, fixture, cutter or strategy change as
  stale-to-downstream CAM until regenerated. Post-processed NC needs
  validation **after** generation, not only internal toolpath checks.
- CAM safety needs holder/tool envelope, clamp clearances, machine travel
  and safe rapid positioning, not just positive Z values.
- Keep operations reproducible and granular. Do not claim cutting readiness
  on the basis of editor tests, Rust compilation or a preview.

The clean-slate Rust reboot was merged as [PR #99](https://github.com/newnetmp3/CarveFoundry/pull/99) into main at `909ae2a4eef989515cb93d66cf9de41f4709f0f3`. The 10 pure-core Rust tests passed; strict Clippy and native Linux release compilation passed on exact PR head `916cffe80dd8f1860aa7f4c3552f529eab3db310`. This does not establish tested physical KDE Wayland behavior or CNC safety.

The archived Python application is evidence/reference only; it is not linked
or executed by the clean Rust workspace. A future CF3D-to-CFD migration
must use an explicit, tested one-way tool with clear omissions, not rename
files or infer compatibility.

## R1a analytic paths — implementation checkpoint

PR #101 merged to main (`49a58bf3b0270af52ac526ec05f65e3e2ad50010`), after [Rust native CI `37867505729`](https://github.com/newnetmp3/CarveFoundry/actions/runs/37867505729) passed all 26 core tests, strict Clippy and native Linux release build on exact head `6511f900bf5b6aadfe67290c4fe059e601aaa9d1`. It introduces retained
open/closed `AnalyticPath` objects with persistent node/segment IDs and
first-class **Line / Circular Arc / Cubic Bézier** variants. Paths are stored
in a new optional `paths` field of the existing `.cfd` schema v1, with
older projects loading unchanged and no polygon geometry flattened to curves.
The new Rust Inspector supports node X/Y edits, cubic handle coordinates,
line-edge midpoint insertions, straight-line node deletion, closure and
lock/delete; the canvas exposes separate **Move objects** and **Edit nodes**
modes with undoable drag sessions. Preview polyline sampling never replaces
stored arcs/cubic controls, and is not used for CNC.

**Scope limits:** Only straight-segment insertion and line-only junction
removal are lossless today; arc endpoint edits fail closed until a constraint
solver exists. Fixed-tolerance visual tessellation is not toolpath geometry.
There is still no import of historic `.cf3d`, 3D, CAM, preflight or NC output.
Automated Rust CI passed; physical KDE Wayland and Onefinity machining tests remain outstanding.

### R1b next: stable analytic SVG + native feature snapping

Implement a dedicated 2D source-preserving SVG reader/writer with safe bounds,
roundtrip tests for line, arc and Bézier paths, and robust object/node/handle
snaps without changing source identities. SVG curve import must validate every
node and stop on unsupported commands; do not pretend lossless legacy CF3D
conversion. Add tangent-aware curve handles before general trim/chamfer.
Do not integrate CNC output until the R6 machine-safety gate passes.

## R1 usability remediation / day-to-day CAD tools

The first analytic vector release passed Rust CI but has serious usability
gaps. [PR #103](https://github.com/newnetmp3/CarveFoundry/pull/103), now merged to main as `e78c33470eb54a5e8034399b09d28fb103852197`, prioritizes **functional direct manipulation**
before adding more esoteric geometry features. Its acceptance includes:

1. Drag nodes/handles on **first gesture** using mouse-down press origin;
   exact coordinates cannot shift before pointer movement.
2. Snap the **movement delta** only, OFF by default; preserve true
   circular arc/Bézier data and reject invalid transforms atomically.
3. Native editable shape palette, Pen-click polygon/polyline, duplicate,
   rotate, flip, align, hide/show, undo/redo and keyboard workflows.
4. Pointer-centered wheel zoom, middle/right-drag pan, Fit View; no
   invisible camera adjustments when selecting geometry.
5. Automated hit-test, edit transaction, curve preservation and project
   format regression checks, strict Clippy and Linux release compilation.
6. Explicit **manual** KDE Plasma/Wayland UX smoke test before any
   claim of real-device usability. The machine/CAM preflight gate remains
   closed.

The 2D canvas should be assessed by ordinary tasks (draw polygon, select,
move node, undo, copy, mirror, save/reopen), **not** simply number of
buttons or Rust code size. Next major R1 scope remains SVG/DXF, real
font/text authoring, editable layers and advanced curve tool topology.

## Verified Rust editor usability recovery — merged PR #103

- [PR #103](https://github.com/newnetmp3/CarveFoundry/pull/103)
  merged as main commit **e78c33470eb54a5e8034399b09d28fb103852197**.
  Its exact feature head **4d8bf1833636b06d92851396f627323e1a855406**
  passed [Rust CI run 37869621001](https://github.com/newnetmp3/CarveFoundry/actions/runs/37869621001):
  **38 Rust tests, strict Clippy and Linux native release compilation**.
- Corrected node/handle dragging to pick the **original mouse press point**
  rather than the cursor after the drag threshold; nodes on unselected
  paths can be moved directly. Grid snaps relative displacement and is
  OFF by default. Undo/redo and failed drags are atomic.
- Native editable shapes now include Rectangle, Circle, Ellipse, Triangle,
  Pentagon, Hexagon, Octagon and Star. Circles/ellipses are four
  cubic-Bézier approximations. Pen clicks create open polylines or closed
  outlines. New editable objects have real analytic path nodes.
- Existing R0 polygon contours can be converted on demand to editable
  line paths, preserving identity, placement, visibility and Undo.
- True circular arcs allow endpoint motion with exact sweep-preserving
  circle refits. The editor includes Duplicate, Rotate ±90°, Mirror X/Y,
  Center on Stock X/Y, Hide/Show, Delete, keyboard shortcuts, mousewheel
  cursor-anchored zoom, middle/right pan and Fit View.
- Enabled serde_json float_roundtrip for precise f64 CAD persistence:
  exact saved path coordinates round-trip without parser rounding changes.
- [docs/UX_SMOKE.md](UX_SMOKE.md) specifies required real-world KDE Plasma
  Wayland interaction tests. **Those manual tests have NOT been run.**
- Still no real fonts/text, SVG/DXF, grouping/layers, broad curve topology,
  3D workspace, native CAM engine, machine-safety preflight or NC export.

**Next priority:** obtain actual KDE Plasma Wayland node-drag and zoom/pan
feedback, fix any remaining blockers, then continue with native 2D authoring,
SVG/DXF and typography. Do not treat automated tests as interactive QA.
Do not resume Python GUI conversion or unlock CNC export prematurely.


## R1 UI usability milestone — PR #105

Focus shifts from adding disconnected features to restoring a discoverable,
drawing-first desktop experience inspired by established CNC design workflows.
Merged as [PR #105](https://github.com/newnetmp3/CarveFoundry/pull/105)
at main **3a467bd6473dadea0eb7a828814d58349e39df7a**.
The native shell now has recognizable File/Edit/View menus, a mode ribbon,
grouped drawing tools, a large light-material canvas with coordinate rulers,
object tree, precise Properties panel, Material setup and status bar. Components
are individually owned by Rust UI modules; no legacy Python UI is revived.

Open/Save As uses the KDE XDG portal with cancellation behavior and unsaved
project protection. A read-only Toolpaths workspace preserves the machine
safety boundary. Automated validation passed: [Rust CI 37871191546](https://github.com/newnetmp3/CarveFoundry/actions/runs/37871191546) on exact head 86cf7415
(38 Rust core + 3 studio tests, strict Clippy, native Linux release).
**Separate human KDE/Wayland QA is NOT complete.** Specific acceptance
cases and screenshots are listed in docs/UI_DESIGN.md.


### UI priority before new engine milestones

Use docs/UI_DESIGN.md and docs/UX_SMOKE.md for real KDE/Wayland
acceptance. Fix clipping, scaling, pen-node dragging, keyboard focus,
native portal dialogs and material/property-pane regressions before
implementing unsupported CAD/CAM tooling. Do not claim to have matched
every feature of commercial software, or unlock NC export.
