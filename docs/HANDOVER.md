# CarveFoundry — rolling Rust reboot handover

## Canonical continuity

At the start of every development chat, read this file, `docs/ROADMAP.md`
and live GitHub branch status. Work from the latest verified source, not from
a prior conversation's assumptions. Update this handover after each meaningful
milestone; CI results must be linked and attributed to the exact commit.

## Reboot decision — October 8, 2026

The owner explicitly requested starting CarveFoundry over from scratch in
**Rust**, instead of continuing the gradual Python-UI replacement.
- Archived previous full Python/PySide6 application:
  `archive/python-ui-2026-10` at historical main commit
  `e5d51de90358e54eea0431841339acb68c71d411`.
- Closed superseded unified-bridge PR #98 without merging.
- New clean Rust source tree in branch `rust-reboot`.
- **No Python dependency** anywhere in the new Cargo workspace.
- This is not a promise of old .cf3d file compatibility, or complete
  CAM parity; it is a fresh application, with new .cfd files.
- Old unrelated open PRs #32 and #33 refer to the archived Python GUI;
  do NOT merge them into the reboot. They were not changed in this reboot.

## Verified baseline R0 — merged on main

- `crates/core/src/geometry.rs`: finite closed polygons, crossing/touching
  checks, point selection.
- `crates/core/src/project.rs`: typed versioned native .cfd design,
  stock XY and thickness, stock-relative fixtures, stable vector IDs,
  bounded JSON files, same-directory atomic staging on save. Legacy CF3D
  is not interpreted.
- `crates/core/src/editor.rs`: validated typed edit actions, contour
  creation/position/lock/remove, stock and fixture changes, one-action
  Undo/Redo and atomic drag cancel.
- `apps/studio/src/main.rs`: native egui desktop, 2D work canvas, zoom,
  visual fence bounds, create/move/select/lock/delete rectangles, property
  editing, stock and fixture inventory and file open/save. **NO CAM.**
- `.github/workflows/rust.yml`: native Rust tests, Clippy, release compile
  and file-format/geometry safety gates.

**Validated source state:**
- [PR #99](https://github.com/newnetmp3/CarveFoundry/pull/99) clean Rust
  reboot merged to `main` as `909ae2a4eef989515cb93d66cf9de41f4709f0f3`.
- Exact feature head `916cffe80dd8f1860aa7f4c3552f529eab3db310`
  passed [Rust Reboot CI `37862945581`](https://github.com/newnetmp3/CarveFoundry/actions/runs/37862945581):
  10 Rust core tests, strict Clippy and Linux native release build passed.
  Failed earlier CI runs were lint-only and repaired before this green run.
- `main` now contains only 15 Rust workspace, docs, GitHub CI and launcher
  files. No Python, PySide6, old CF3D conversion, old UI or old CI remains
  in its working tree.
- Superseded PR #98 and old Python-only PRs #32/#33 were closed with
  explanatory comments. All remain in Git history; no features were
  merged from them into the reboot.
- **CNC and physical QA are NOT validated.** Design-only `.cfd`
  projects do not interoperate with legacy `.cf3d`; no safe NC export,
  preflight or CAM engine is installed.

## Verified R1a — retained Rust analytic geometry and direct editing

- [PR #101](https://github.com/newnetmp3/CarveFoundry/pull/101)
  merged to main as **`49a58bf3b0270af52ac526ec05f65e3e2ad50010`**.
  Exact merged-feature head `6511f900bf5b6aadfe67290c4fe059e601aaa9d1`
  passed [Rust Reboot CI `37867505729`](https://github.com/newnetmp3/CarveFoundry/actions/runs/37867505729):
  **26 Rust tests, strict Clippy, native Linux release compilation**.
- New `crates/core/src/path.rs` retains native Line / center-radius Arc /
  Cubic Bézier source data with permanent node and segment identities,
  finite coordinate/radius validation and bounded preview-only sampling.
  No analytic arc/cubic is silently replaced with a sampled polygon.
- `Project.paths` is an optional property in Rust-native `.cfd` schema v1.
  Old reboot projects deserialize unchanged. Global object IDs are validated
  across legacy polygon contours and analytic paths.
- Typed `Editor` commands: create line/arc/cubic, translate path, exact node
  / Bézier handle movements, split straight edges, remove line-only junctions,
  open/close paths, lock/remove, 64-step Undo/Redo and one-Undo drag sessions.
- Native egui has separate Object and Node modes with analytic path stroke,
  visible node/control handles, numeric editing and topology actions.
  Invalid operations roll back. Arc anchor mutations reject until circular
  constraints preserve true radius and center.
- **Not complete R1**: automatic node snapping, handle constraint tools,
  analytic trim/join/chamfer/fillet, SVG/DXF, fonts/text, grouping and layers
  remain. No 3D, CAM, toolpaths, fixture-aware preflight or NC export.
  Physical KDE Plasma/Wayland and Onefinity tests remain unverified.

**Next engineering batch — R1b:** implement source-preserving SVG vector
interchange, robust nearest-feature snapping, smooth-curve controls and
dedicated analytic path selection. Keep zero Python dependencies and validate
backwards `.cfd` compatibility. Deliver in meaningful, green-CI PRs,
update this rolling handover after each merge, then run real KDE Wayland
interaction QA. DO NOT migrate or reintroduce PySide6.

**Physical test gate:** launch on KDE Plasma Wayland and exercise
select/drag, Undo/Redo and file roundtrip. Perform actual Onefinity
scrap testing only after CNC stages, posted preflight, fixture
verification and tool-change probing are implemented.

## Safety-critical invariant summary

Stock lower-left XY0, top-of-stock Z0. Fixture top Z stored relative to
stock top; fence bed height minus material thickness for external hardware.
Manual tool changes require separate NC programs and fresh Z probe.
No CNC export exists; physical Wayland/Onefinity tests remain outstanding.

## Append-only checkpoints

| Date | Work | Verification | Next |
|---|---|---|---|
| 2026-10-08 | Preserve old application; create clean pure Rust workspace with R0 geometry, design editor, file schema and UI | CI pending | Validate full Linux build, record commit, proceed R1 |

| 2026-10-08 | Pure Rust reboot merged to main via PR #99; Python GUI archived, incompatible legacy PRs closed | Rust `37862945581` green: 10 tests/Clippy/Linux release; main `909ae2a4` | R1 analytic vectors; KDE Wayland UI QA; no CNC until R6 |

| 2026-10-08 | Implemented Rust R1a retained lines/arcs/cubics and direct node/handle editing, schema-compatible CFD persistence, strict undoable operations | `feature/rust-r1-analytic-vectors`, native CI pending | Verify green Rust CI, merge then update verified handover; next curve constraints and SVG/DXF |

| 2026-10-08 | PR #101 R1a retained analytic curves and native direct node/handle editing merged to main | [Rust CI `37867505729`](https://github.com/newnetmp3/CarveFoundry/actions/runs/37867505729): 26 tests, strict Clippy, native Linux release; main `49a58bf3` | R1b analytic SVG interchange/snapping/curves and physical KDE Wayland QA |


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

## Investigation record — original node drag regressions (resolved in PR #103)

The user reported the initial Rust vector editor as extremely unusable
(particularly node motion, missing CAD tools). Root causes found:

1. Previous drag hit-testing used current cursor after egui's drag
   threshold, rather than the original button-down position. First
   gesture would miss small nodes/controls, and direct path selection
   was required before any node drag.
2. Absolute-coordinate grid snapping changed the node position abruptly
   on the first movement. Default snapping enabled made this worse.
3. R0 rectangle creation saved non-node-editable polygon contours,
   whereas R1 paths had editable nodes; this was inconsistent with
   user expectations.
4. Arc endpoint dragging always rejected, preventing obvious edits.

`fix/rust-editor-usability-tools`:
- Adds pure `crates/core/src/interaction.rs` first-press, topmost
  node/handle/edge selection plus relative movement snapping and unit
  regressions. Mouse wheel zoom, middle/right pan, Fit View, new
  object/direct-node/Pen modes.
- Adds `crates/core/src/shapes.rs`: editable rectangle, star, polygon,
  circle/ellipse Bézier constructors; lines and 3-point+ polylines
  from Pen. All use versioned `.cfd` analytic vectors.
- Arc endpoint motion refits a true circle preserving signed sweep,
  no source flattening; invalid moves remain transactional.
- Adds undoable duplication, rotate ±90°, mirror X/Y, align stock center,
  visibility toggles, keyboard shortcuts.
- Benchmarked or verified hardware UX: **NOT YET**. Must run CI Rust tests,
  strict Clippy and native Linux release, then manually test KDE
  Plasma/Wayland pointer/drag/cancel/selection flow.

**Follow-on after usability recovery:** resolve any KDE/Wayland QA regressions
first, add precision transformations and keyboard workflows, then
SVG/DXF, fonts/text, layers, and further CNC-free CAD authoring.
Don't reactivate the retired PySide6 application. Preserve stock XY0
bottom left, top-of-stock Z0, and no G-code until R6 preflight gates.

| 2026-10-08 | Rust node-drag and tool-palette repair PR #103 merged to main | [Rust CI `37869621001`](https://github.com/newnetmp3/CarveFoundry/actions/runs/37869621001) green: 38 tests, strict Clippy, native Linux release; main e78c3347 | Manual KDE/Wayland interaction QA; then SVG/DXF and CAD typography |

## Drawing-first Rust UI redesign — PR #105 (CI pending)

The owner supplied visual references from professional CNC drawing software
and requested **interface usability first**, not a new isolated CAM feature.
The implementation lives on feature/rust-design-workspace-ui and is subject
to Rust tests, strict Clippy and native Linux release compilation before
promotion. Manual KDE Plasma/Wayland interaction QA is still outstanding.

- Original monolithic 900+ line studio source decomposed into a lean desktop
  coordinator and modules in apps/studio/src/ui:
  shell.rs, palette.rs, inspector.rs, canvas.rs, theme.rs.
- Desktop layout now has a File/Edit/View/Drawing/Help menu, fast mode and
  shape ribbon, grouped left-side vector tools, expanded material canvas,
  right-side Objects/Properties/Material tabs and context status strip.
- Reliable native KDE/Wayland Open/Save As using the XDG Desktop Portal.
  New/dirty project protections, first Save As, explicit naming actions.
- Existing drawing engine, stable IDs, hit-testing, Pen, transforms and
  undo/redo stay Rust-native. Core now adds validated project/path rename
  commands instead of generating per-keyboard-stroke Undo states.
- Higher-contrast material canvas, bounded background grid and rulers,
  all-path node grips in direct mode, readable selection colors, pan/zoom.
- Toolpaths area explicitly read-only: **no NC export, CAM safety or
  physical CNC validation**.
- Acceptance checklist: docs/UI_DESIGN.md alongside docs/UX_SMOKE.md.
  CI is not proof of correct physical pointer behavior or Wayland scaling.

**Follow-on:** fix any clipping, mis-sized controls, file picker, mouse
capture or mode confusion reported in Wayland QA before new drawing features.
Progress should be measured by common design workflows, not icon count.

