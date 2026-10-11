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

## Verified drawing-first Rust UI redesign — merged PR #105

The owner supplied visual references from professional CNC drawing software
and requested **interface usability first**, not a new isolated CAM feature.
The modular redesign was merged as [PR #105](https://github.com/newnetmp3/CarveFoundry/pull/105), main commit **3a467bd6473dadea0eb7a828814d58349e39df7a**.
Exact feature head **86cf7415469feb6902c462ae57e6c3e7e664703a**
passed [Rust CI run 37871191546](https://github.com/newnetmp3/CarveFoundry/actions/runs/37871191546):
**38 core + 3 native studio tests, strict Clippy and Linux release build**.
Manual KDE Plasma/Wayland interaction QA is **still outstanding**.

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


| 2026-10-09 | PR #105 merged drawing-first native Rust design workspace (menus/ribbon/palette/object inspector/material setup/KDE file picker) | [CI 37871191546](https://github.com/newnetmp3/CarveFoundry/actions/runs/37871191546) green: 38 core + 3 studio tests, Clippy and Linux release; main 3a467bd6 | Manual Wayland layout/input QA and source-first 2D text/SVG/DXF authoring |


## Active usability slice — direct drag-to-draw shapes

Branch `feature/rust-drag-to-draw-cad` implements a more natural creation
workflow: choose a vector shape from the left palette or ribbon, then
**mouse-down and drag its bounding box directly on the stock**. The
drawing is a temporary display preview until the user releases the
primary mouse button; a completed shape creates exactly one validated
Undo history entry. A small/cancelled/out-of-bounds gesture does not
alter the saved project. The shape tool stays active to repeat placement.
Switch Select/Nodes/Pen or Escape to cancel the tool.

- Pure Rust `crates/core/src/placement.rs` normalizes all drag
  directions, preserves off-grid start and enforces finite size/bounds,
  square Circle dimensions and Shift-aspect constraint.
- `apps/studio/src/ui/canvas.rs` renders live editable-shape outline
  and W/H size readout; no provisional objects are added to history.
- The grouped palette, ribbon and Drawing menu now select tools
  instead of instantly dropping arbitrary-offset shapes. For
  keyboard-driven precision, use collapsed Vector Dimensions and
  "Use exact size" to click a precise lower-left placement on the stock with an uncommitted ghost preview.
- Regression tests cover any-corner drag, aspect lock, no movement,
  invalid geometry, non-mutating tool selection, single-step Undo.
- **CI pending.** Human Wayland QA not done. This is design-only;
  native G-code toolpaths and preflight remain blocked.

After merging, continue with normal design workflows: mouse-on-canvas
numeric tool positioning, responsive sidebars, click-vs-drag Pen usability,
native text and SVG vector interchange; do not equate passing CI with
real KDE pointer QA.

## Verified native shape-placement milestone — merged PR #107

- [PR #107](https://github.com/newnetmp3/CarveFoundry/pull/107)
  merged to main as **`49f96f577b2b72fdfb6eee5ae7ab7ce64f878708`**.
  Exact feature head **`d420fc10da94943b8d12d6629f01ebf8c5806649`**
  passed [Rust CI `37872863242`](https://github.com/newnetmp3/CarveFoundry/actions/runs/37872863242):
  **47 core/studio tests, strict Clippy, native Linux release build**.
- The professional CNC-style tool palette now activates a tool rather than
  adding arbitrary-offset geometry. Users drag a diagonal anywhere on
  stock, see a noncommittal outline and live dimensions, and release to
  create exactly one undoable analytic vector. Reverse drags, Circle and
  Shift equal-side constraints, relative snap, minimum size and finite
  bounds are implemented and tested. Escape cancels.
- Numeric width/height entry uses **click-to-place**, with a ghost
  preview anchored at the pointer; no geometry is added until clicked.
  Selected tools remain highlighted. R/C drawing shortcuts, V/N/P mode
  exits and status hints clarify interaction.
- The pure geometry resides in `crates/core/src/placement.rs`; canvas,
  palette and shell only consume its validated placement contract.
- Native project's .cfd serialization and machine/export boundaries
  are unchanged. No NC generator, cutting preflight or physical router
  interaction is implemented. **Manual KDE Plasma Wayland pointer QA is
  still outstanding.**

**Next engineering priority:** perform live KDE/Wayland pointer QA on both
gesture and numeric placement, including 125%/150% scaling, then improve
multi-object selection, precision snapping and editable numeric placement,
plus SVG/text/layer workflows. Do not confuse a green Rust CI with
end-user input verification. Continue pure Rust only.

| 2026-10-08 | PR #107 drag-to-size / exact click-to-place UX merged | [CI 37872863242](https://github.com/newnetmp3/CarveFoundry/actions/runs/37872863242) green: 47 tests, strict Clippy, release; main 49f96f57 | Manual KDE Wayland gesture QA; then multi-select and precise snapping |

## Verified R1 selection and snapping — PR #108 merged

Branch `feature/rust-multiselect-vector-snaps` introduces additive
Shift/Ctrl-click selection, left→right enclosure and right→left crossing
marquees, group drag with an atomic Undo step, and group duplicate/delete
across retained analytic paths and R0 contours. Locked/hidden/unknown group
members fail closed rather than moving a subset. These are editor selection
state and typed operations, not changes to the `.cfd` file format.

`crates/core/src/interaction.rs` now identifies exact source nodes,
straight-segment midpoints and stock corners (not tessellation samples)
using a screen-pixel tolerance. Use these as optional targets for Pen,
exact-size click placement, node moves and Bézier handles. Grid snapping
remains separate and off by default. Disable feature snaps in View &
Snap when precision work requires entirely free movement.

The right Objects tab shows highlighted multi-selection plus bulk actions,
the central canvas shows marquee feedback and visual feature-snap targets,
and the toolbar/status/help explain modifiers and selection count.
Core regression cases cover batch validation, undo/cancel/duplicate/delete,
crossing/enclosure semantics and finite/no-self snap candidates.

[PR #108](https://github.com/newnetmp3/CarveFoundry/pull/108)
merged as main **`7ad69fef3125834898adb24cf68323f5f0ced3f6`**.
Its exact feature head **`b091af41bac0a0a3d0f6c89737cc5b680b6d15b5`**
passed [Rust native CI `37876938223`](https://github.com/newnetmp3/CarveFoundry/actions/runs/37876938223):
**48 core tests + 7 studio tests**, strict Clippy and Linux release build.
KDE Plasma Wayland mouse capture, scaling and real tool feel are
**not** verified by these automated checks.
No CAM, G-code or controller changes.

| 2026-10-08 | PR #108 bulk vector selection and exact endpoint/midpoint/stock-corner snapping merged | [Rust CI `37876938223`](https://github.com/newnetmp3/CarveFoundry/actions/runs/37876938223): 48 core + 7 studio, strict Clippy, Linux release; main `7ad69fef` | Real KDE/Wayland interaction QA; then multi-object alignment, SVG/DXF, typography |

## Precision placement and arrangement milestone — active development

Branch `feature/rust-precision-arrange-tools`: after multi-selection and
real-feature snapping (#108), the next blocker is exact XY placement and
repeatable alignment. New **pure Rust** module `crates/core/src/arrange.rs`
calculates exact retained-geometry bounds of analytic Line, circular Arc
(including in-sweep quadrants), Cubic Bézier (quadratic derivative extrema),
and legacy contour polygons. This avoids relying on a 32-step visual
approximation when positioning carved vectors.

The `Editor` gains a validated one-Undo `Action::Arrange` preserving stable
vector identities, curve definitions, and stock XY0. In addition to
aligning 2+ objects by six edges/centers, users can distribute 3+ vectors
by equal center spacing, or move an *entire selection envelope* to the
stock's left/center/right or bottom/center/top without destroying
relative spacing. Existing fail-closed multi-selection validation
rejects hidden, locked, unknown and duplicate members atomically.

The new modular native `apps/studio/src/ui/arrange.rs` panel, visible under
Drawing → **Precision Align & Position**, supports absolute bounding-left
X and bounding-bottom Y, position resync, nudge buttons and adjustable
0.01–1000 mm step, arrow-key nudges (Shift ×10), alignment, spacing,
and stock-positioning controls. Draft input fields do not modify the
project until the user clicks Set X/Y. Each accepted edit is a single
Undo operation. Undo/Redo still uses the existing project history.

**CI verified as green; KDE Wayland desktop UI QA NOT performed.**
Machine output, toolpaths, posted NC and controller operation remain blocked.

Follow-on: test keyboard modifiers, stock alignment, zero movement,
mixed analytic/legacy selections, changing window sizes and real monitor
scales on KDE; then improve selection behavior and implement native text /
SVG / DXF interoperability without reopening the retired Python GUI.

Additional UI: precise selection envelope and dimension readout on the
canvas; **Shift+F** or **Fit selection** zooms/centers the currently selected
vectors without modifying the project. Fixed quick-shape ribbon buttons to
activate the same drag-to-draw tool as the grouped palette, eliminating the
older arbitrary-offset spawn behavior from that shortcut route.

## Verified Rust precision layout milestone — merged PR #109

- Merged [PR #109](https://github.com/newnetmp3/CarveFoundry/pull/109)
  into main at **`96a9e5ceeb529dc6927fd1ab1fc8f154415a26a0`**.
- Final exact feature head
  **`7b4a22c8877ee36d044c8be856b5723f29d65568`**
  passed [native Rust CI `37961368120`](https://github.com/newnetmp3/CarveFoundry/actions/runs/37961368120):
  **53 core + 9 studio tests**, strict Clippy and Linux release build.
- Exact analytic vector bounding boxes underpin align/distribute, group
  alignment to material, typed lower-left X/Y, keyboard/on-screen
  nudging, Shift+F Fit Selection and canvas dimension display.
  Top-ribbon quick shapes consistently activate drag-to-draw.
- All geometry edits remain atomic, validated and undoable. CNC CAM,
  preflight and post-processing remain *disabled*.
- **Not verified:** manual KDE Plasma/Wayland mouse, keys, XDG portal
  and display-scaling QA (see `docs/UX_SMOKE.md`).

Next prioritize interactive QA on real desktop, then complete durable
native vector interoperability (SVG/DXF), text and font handling, editable
layers and more practical node-level design tools.

| 2026-10-09 | PR #109 precision positioning and layout merged | [Rust CI `37961368120`](https://github.com/newnetmp3/CarveFoundry/actions/runs/37961368120) green: 53 core + 9 studio, strict Clippy, Linux release; main `96a9e5ce` | KDE Wayland usability QA, then SVG/DXF/text authoring |


## Active Rust editor screenshot usability recovery — 2026-10-09

**Latest verified main before branch:** `2dede448676cecd2054a61b407e8b7b1b81e2b64`,
[CI 37961850844](https://github.com/newnetmp3/CarveFoundry/actions/runs/37961850844)
green. No open PRs at kickoff.

Owner screenshot with a selected analytic polyline in Node mode demonstrates
reproducible UX defects: Unicode icon placeholders, wrapped precision XY,
small text and indirect access to the node inspector. The branch
`feature/rust-editor-controls-ux` addresses these in **pure Rust** using
font-independent egui vector icons, two-column tool grids, stable XY and nudge
layout, enhanced text/sidebar sizing, and direct node/handle pick opening
Properties without moving the vector. No .cfd schema, CAM or machine state
was changed. Keep this screenshot-driven UX recovery before feature expansion.

**Branch CI and manual KDE Wayland acceptance pending**: do not report a
merge, successful compilation or machine QA until those results are checked.
Next planned CAD milestones: native SVG/DXF interchange, system text/fonts,
editable layers/grouping and direct curve topology tools. CNC posting stays
disabled pending fixture/cutter/holder validation and posted-code preflight.

## Verified PR #110 — screenshot-driven native Rust editor usability

[PR #110](https://github.com/newnetmp3/CarveFoundry/pull/110)
merged into `main` at **`55d6399b8f235f721048d1f1ec28ab9b60664feb`**,
after its exact final feature commit
`533a57769baab87428d52a9da1819d6a41b61fcb`
passed [Rust CI #37966080362](https://github.com/newnetmp3/CarveFoundry/actions/runs/37966080362):
**53 core tests + 10 studio tests, strict Clippy and Linux release build**.
An initial lint-only failure was fixed before merging.

New UI: font-independent painted shape/eye/lock/nudge icons, readable
quick-action labels, consistent two-column vector/path palette, wider
resizable sidebars and larger default fonts, non-wrapping XY placement
rows, stable alignment grid, and automatic Properties inspector activation
on canvas node/handle selection (non-mutating regression included).
No native schema change, CAM engine or NC-export pathway was introduced.
**Manual KDE Plasma/Wayland pointer, scaling, file picker and panel QA remains outstanding.**
See `docs/UI_DESIGN.md` for the screenshot-specific checklist.

**Next engineering batch:** test user-reported real desktop layouts and
picking gestures, fix any remaining usability defects, then implement
retained-geometry SVG/DXF interchange and real text/font authoring in Rust.
Stay CAD-only until the machining and posted-code safety gates are met.

| 2026-10-09 | PR #110 native editor controls and direct selected-node property UX merged | [Rust CI 37966080362](https://github.com/newnetmp3/CarveFoundry/actions/runs/37966080362) green: 53 core + 10 studio tests, strict Clippy, native release; main `55d6399b` | KDE Wayland manual UI smoke; retained SVG/DXF and font authoring |


## Active follow-up — 2026-10-09 node dragging from owner screencast

The owner uploaded `Screencast_20261009_133456.webm` showing nodes
failing to follow the mouse across multiple frames in the Rust Node editor.
Root cause identified in `apps/studio/src/ui/canvas.rs`: egui
`Response::drag_delta()` is the **per-frame movement**, but all the
`Editor::preview_*_drag` functions reconstruct each frame from the
**original pre-drag model**. Thus a 1–3 pixel per-frame motion kept resetting
the dragged node/vector near its starting position. Shape placement was
similarly affected. This is a proven source-level defect, not a machine
sensitivity setting or a Windows/Wayland mouse problem.

Branch `fix/rust-cumulative-node-drag` (base main `32d69ce6`):
- Use `Response::total_drag_delta()` for absolute pointer displacement
  from initial mouse press, applied consistently to shapes, nodes, Bezier
  controls, complete paths/contours and group moves.
- Retain pre-drag baseline transaction, one Undo commit on release,
  deterministic grid quantization of the entire displacement.
- New studio tests exercise multi-frame cumulative node and path movement,
  stationary frames, off-grid movement and undo.
- Alt temporarily bypasses feature-snap magnetic behavior during node and
  handle dragging; live snap indicator omits actively dragged path.

**CI pending.** Update exact PR/head/run details after green CI, then merge.
Actual owner KDE Plasma Wayland drag feeling must be retested from scratch.
No CAM, G-code output, safety boundary or project schema changed.

This is a high-priority UI blocker; future refactors MUST NOT revert to
per-frame delta in a baseline-based drag preview.


## Verified node-drag fix — merged PR #111

**Merged to main:** [PR #111](https://github.com/newnetmp3/CarveFoundry/pull/111)
at `7ee5cba21afe0f805f1ea9289dfee2309b85ffc9`.
Its final exact feature head `d7304a945afe06929dbc82448aa1e335c31a5fd9`
passed [Rust CI run 37968221186](https://github.com/newnetmp3/CarveFoundry/actions/runs/37968221186):
**53 core + 14 studio tests, strict Clippy, native Linux release build**.

The owner-provided 7-second screencast showed nodes repeatedly falling back
near their original coordinates during drag. Confirmed cause: use of egui
`response.drag_delta()`, which only measures movement **since last frame**,
when all drag preview functions apply an **absolute cumulative displacement**
to a retained pre-drag baseline. This same defect affected shape sizing,
full-vector/path movement and group drags. Both canvas instances were changed
to `response.total_drag_delta()`. Regression tests verify multiframe
movement, stationary-frame stability, grid snapping/off-grid origin,
one-Undo node dragging and full-vector drag. Alt suppresses magnetic snap
during node/handle dragging; active path excluded from drag snap indicator.
Pure Rust schema and safety/CAM/export gates unchanged.

**Manual KDE Plasma/Wayland drag retest is STILL REQUIRED**: after updating
main, create a polyline, select Node mode, drag multiple nodes across long
and short distances, hold still mid-drag, drag Bezier control handles and arc
endpoints, Alt free drag, drag a shape to size, Undo/Redo and save/reopen.
Automated Rust CI is not proof of physical desktop pointer feel.

Next after confirming mouse QA: precise vector import/export and font/text
CAD editing. Never regress absolute drag preview to per-frame deltas.

| 2026-10-09 | PR #111 cumulative drag regression repair merged | [Rust CI 37968221186](https://github.com/newnetmp3/CarveFoundry/actions/runs/37968221186): 53 core + 14 studio, Clippy and Linux release green; main `7ee5cba2` | Retest node/shape/whole-vector drags on KDE Wayland; then SVG/DXF/text |


## Active pure-Rust SVG path interchange — October 9, 2026

Owner confirmed on KDE Plasma/Wayland that direct node dragging from PR #111
**now works**. This closes the previously reported cursor-tracking blocker;
it does not validate every other mouse/scale behavior.

Next roadmap stage branch: `feature/rust-r1-svg-vectors` from verified
main `d16ecb9e3c0b27caf6dd3c75be296226a5fadbac`.

Implementation staged for CI:
- `crates/core/src/svg.rs`: bounded, strict SVG path reader/writer,
  true analytic line/circular arc/cubic segments (no preview sampling),
  mm and viewBox coordinates with CAD bottom-left conversion.
- Explicit error on unsupported curves, elliptical arcs, transformed
  geometry, unsupported shape elements and multi-subpath declarations.
  XML parsing does not interpret scripts, images or references as geometry.
- Stable per-path node/segment identities; native .cfd schema unchanged.
- One undoable `Editor::ImportPaths` transaction validates all vectors
  before mutating a saved design. The imported geometry is separately
  assigned unique project IDs. Both vector and legacy polygon outlines
  can be SVG-exported without G-code or fixtures.
- KDE native File menu uses XDG picker for Import SVG vectors and
  Export SVG drawing; errors leave current design intact.
- Core and studio tests for analytic round-trip, relative closure,
  unsupported geometry rejection, all-or-none imports and Undo.

**Verification pending:** CI tests, strict Clippy, native Linux release
and a manual KDE file-dialog round-trip. Keep a clear distinction between
SVG vector drawing export and CNC NC export (STILL DISABLED).
Next after this coherent batch: DXF interchange, then true system-font
text/vector conversion and layers.

## Verified R1b native SVG path interchange — merged PR #112

The owner confirmed **node dragging now works** on KDE Plasma/Wayland after
PR #111. Subsequent SVG vector interoperability merged via
[PR #112](https://github.com/newnetmp3/CarveFoundry/pull/112)
as `cca178b15c3104bc45f3de05336003bb073a0072`.
Exact tested feature head `043f21ee106734ea46c125c1f63a58df7cfa7aca`
passed [Rust CI 37970424316](https://github.com/newnetmp3/CarveFoundry/actions/runs/37970424316):
**57 core + 15 studio tests, strict Clippy and native Linux release build**.
The first CI attempt needed a test-only `Debug` derive on InspectorTab;
the final run was green.

- Rust `crates/core/src/svg.rs` handles bounded SVG XML and path syntax
  for M/L/H/V/C/A/Z, retaining line, circular arc and cubic Bézier sources
  (stock-bottom-left XY0, SVG upper-left coordinates; millimetres).
- No rasterization/tessellation for source data. Unsupported SVG text,
  elliptical or rotated arcs, arbitrary path commands, shape elements,
  transforms and multiple subpaths are explicitly rejected, not
  silently flattened or dropped.
- `Action::ImportPaths` merges any imported paths atomically, with
  fresh project IDs and one Undo step; invalid paths leave design untouched.
- File menu includes native Import SVG vectors / Export vectors as SVG,
  with errors in status and original `.cfd` file state preserved.
- SVG exports include analytic paths and legacy polygon contours,
  not fixtures/material machining metadata and never G-code.
- Details and step-by-step KDE acceptance in `docs/SVG_INTERCHANGE.md`.

**Remaining real-world QA:** user should run Import and Export through KDE
file picker, roundtrip an SVG with a circle/cubic/polyline, and confirm
coordinates, scale, visibility and undo. CI does not prove portal interaction.

**Next engineering course:** R1 DXF vector exchange (preserve
straight/arc/cubic or explicitly reject unsupported spline constructs),
system font text authoring/conversion, grouping/layers and further vector
topology, while preserving edit and SVG round-trip guarantees. CNC export
remains blocked by native CAM, postprocessor and physical preflight gates.

| 2026-10-09 | PR #112 native source-preserving SVG vector interchange merged | [CI 37970424316](https://github.com/newnetmp3/CarveFoundry/actions/runs/37970424316) green: 57 core + 15 studio, Clippy, native Linux release; main `cca178b1` | KDE SVG import/export QA; then native DXF and system-font vector text |

## R1c DXF interoperability — active 2026-10-09

User continued development with "1". Starting main verified at
87df38b2b16d895369d56b44e3054372b52e4647, no open PRs.
The owner confirmed direct node dragging now works.

PR #113: feature/rust-r1-dxf-interchange adds native, bounded ASCII
DXF source geometry interchange in pure Rust (crates/core/src/dxf.rs).
Supported 2D LINE, ARC, CIRCLE, LWPOLYLINE signed bulges and four-point
clamped degree-3 SPLINE. Explicit INSUNITS scales mm/in/cm/m; unsupported
entities, unknown units, non-planar objects and other spline types fail
closed without silent vector loss. Native exported XDATA retains source
multi-span vector grouping and attributes; third-party CAD tools may
strip XDATA. Files use the native KDE File menu and ImportPaths action
for one undoable atomic operation with unchanged .cfd stock/fixtures.
CNC/NC toolpath export remains entirely disabled.

**Verification pending**: exact PR head Rust CI, final merge, actual KDE
file-dialog and external CAD interchange. Update the rolling record once
the PR has passed core/studio tests, strict Clippy and release compilation.
See docs/DXF_INTERCHANGE.md for supported subset and manual QA.

Next major milestones after verified DXF: editable typography from installed
system fonts, grouping/layers, and CAD curve topology.

## Verified R1c DXF vector interchange — merged PR #113

[PR #113](https://github.com/newnetmp3/CarveFoundry/pull/113)
merged as **08bf16847a65e21b1f58323dd57992d23b490a90**.
Final exact source head
**4f0dc1b581f46a26c536c5955ce8e8df5264548e**
passed [Rust native CI run 37972805832](https://github.com/newnetmp3/CarveFoundry/actions/runs/37972805832):
**61 core + 16 studio tests (77 total), strict Clippy, Linux release build**.

Implemented the pure Rust DXF subset in crates/core/src/dxf.rs:
ASCII, bounded 2D LINE, LWPOLYLINE with signed circular bulges, ARC,
CIRCLE as four exact editable quarter-arcs, and degree-3 nonrational
clamped four-control SPLINE retained as native cubic Bezier.
INSUNITS explicitly supports mm/in/cm/m with conversion to native mm;
unitless/unknown units and unrepresentable/3D entities fail closed.
Regular LWPOLYLINE preserves line/arc paths; multiline and cubic
vector segments export as regular line/polyline/spline entities with
standard registered CarveFoundry XDATA for source path grouping and
attributes on native DXF roundtrips. ImportPaths applies imported vectors
atomically in one Undo step; CAD stock, fixture and .cfd schema unchanged.
Native KDE File actions Import DXF vectors / Export vectors as DXF available.

CI confirms Rust behavior and build, **not** manual KDE portal, scale,
external CAD viewer or representative customer DXF compatibility.
A third-party CAD editor may strip XDATA: analytic entities remain usable
but vector grouping can be lost; no arbitrary INSERT, dimensions, general
SPLINE or nonplanar drawing support yet. See docs/DXF_INTERCHANGE.md.

Next coherent milestone: pure Rust system-font text authoring and editable
vector outlines, then first-class layers/groups and native CAD trim/join.
Keep all native CNC CAM/post/export gates closed until independently safe.

| 2026-10-09 | PR #113 DXF native vector interchange merged | [CI 37972805832](https://github.com/newnetmp3/CarveFoundry/actions/runs/37972805832) green: 61 core + 16 studio, strict Clippy, native Linux release; merged 08bf1684 | KDE DXF picker + third-party CAD roundtrip; system fonts/text and grouping |

## Active R1d editable system-font text — October 9, 2026

Continuing user-requested development (user replied "1"). Verified main
72702f17e64e41c49e210ca196680727a0a9bca2, no open PRs,
main Rust CI 37973399567 passed. Confirmed prior native DXF PR #113.

Feature branch feature/rust-system-font-text introduces pure Rust system font
outlining via fontdb + ttf-parser, installed font family/variant picker,
text, em size, tracking and baseline position editing, and exact quadratic
degree elevation to cubic retained editable CAD geometry (never sampling).
No font files are distributed or embedded. Native .cfd uses optional
backward-compatible text_runs metadata referencing ordinary analytic path
IDs; vector outlines render and export through existing SVG/DXF even when
original fonts are not installed. Editing typography regenerates all
associated outlines in one Undo action. If an individual outline is deleted,
its text-source link detaches safely; remaining outlines persist.

UI: top Drawing and left palette Text buttons, composer dialog,
font family/variant dropdown, accurate CAD positioning controls, and
selected text outline -> Properties -> Edit text source. Missing installed
font on another system prevents re-generation but *not* design loading or
outlines. Manual node edits are allowed, but changing text settings rebuilds
glyphs; this limitation must be visible.

**CI pending:** Rust tests, strict Clippy and release build. Do not call this
merged or hardware-tested until final run green. Manual Arch KDE/Wayland
font list, portal scaling and multiline/non-Latin font limitations require
desktop QA. Next R1e: grouping/layers and outline editing/trim.
CNC posting/machine output is still intentionally disabled.

## Verified R1d retained system-font typography — merged PR #114

[PR #114](https://github.com/newnetmp3/CarveFoundry/pull/114)
merged to main at **fe3cf4c4da05da64d9ea34467750d2ead71cb229**.
Exact tested feature head **87d21253006bcea2e459139e98b78b3b96cd973b**
passed [Rust CI #38008575719](https://github.com/newnetmp3/CarveFoundry/actions/runs/38008575719):
**65 core + 17 studio = 82 tests, strict Clippy, Linux release build**.
Green validation included installed-font extraction of a real rounded glyph,
exact quadratic/cubic math, text save/restore, text create/regenerate Undo,
safe outline detachment, and entire text group drag with baseline updating.

Implemented:
- Pure-Rust fontdb system font discovery + typeface variant dropdown;
  ttf-parser exact TrueType/OpenType glyph geometry, exact quadratic degree
  elevation to cubic Bézier paths, no raster/vector sampling.
- Native Drawing Text tool and Properties -> Edit text source.
  Single-line UTF-8 text, height/tracking, XY baseline controls.
- Optional serde-default text_runs metadata in backward-compatible .cfd;
  individual glyph contours remain ordinary editable analytic paths usable
  even when original system font is not installed.
- Atomic SetText create/regenerate with one Undo history step and no
  partially imported invalid glyphs; missing/locked/out-of-bounds glyph
  validation fails without changing the design.
- Moving all outlines together also moves the retained text baseline
  (so later text reflow keeps the chosen location).
- Font binaries are NOT embedded/distributed. Font embedding permissions
  are checked. SVG/DXF output uses generated ordinary vector outlines.

Important constraints: single line, no full Unicode shaping/ligatures or
bidirectional/variable axis handling, no kerning in this first tranche.
Editing text from source rebuilds all glyph outlines and overwrites manual
node tweaks; deleting one glyph breaks the original text-link intentionally
but leaves remaining independent paths intact.
A missing font on another computer prevents text reflow but **does not**
remove the saved vector outlines. Source metadata is currently an association
across individual glyph vectors, not yet a first-class grouping/layer feature.

**Manual acceptance remaining:** real Arch/KDE Plasma Wayland font dropdown
performance/variants, selected glyph editing, source reflow, physical mouse
group movement and SVG/DXF vector export in independent viewers.
See docs/TEXT_AUTHORING.md.

**NEXT:** native Rust first-class grouping/layers + group-object UX
(selection/hiding/locking/rename and retained text groups), precise
join/trim/offset topology tooling, then more capable font shaping and
fixture-aware CAM modules with machine safety gates. CNC/NC export is
still disabled and must not be enabled without dedicated validation.

| 2026-10-09 | PR #114 system-font vector text merged | [CI 38008575719](https://github.com/newnetmp3/CarveFoundry/actions/runs/38008575719): 65 core + 17 studio, strict Clippy and native Linux release; merged fe3cf4c4 | KDE font picker and vector-text QA; grouping/layers next |

## Active R1e native layers and vector groups — 2026-10-09

The user replied "1" to continue. Baseline verified main
0d78759cfbf1057d8daa10aad14a513d3c8e7150; all follow-up docs CI
for PR #114 was green, and there were no open PRs. The next substantial
Rust slice is feature/rust-r1e-layers-groups.

Pure Rust CAD project organization is kept **separate from analytic path
geometry**:
- Optional serde-default `layers`, `layer_members`, `groups` in native
  .cfd; old files remain loadable at the same schema version.
- A non-serialized virtual Base layer (ID=0) holds unassigned vectors.
  Editable custom layer records support visible, locked and rename.
- Persistent vector groups have stable globally unique group IDs and
  names; flat membership only, no recursive groups or duplicate ownership.
- Object-mode clicks on grouped shapes select the whole group, direct drag
  of one member drags every member in one Undo; Node mode retains access
  to individual anchors and control handles. Marquee expands full groups.
- Layer/group visibility propagates into CAD render, hit test and snap;
  effective editing locks are applied to batch movements and individual
  direct geometry commands. The Inspector has separate Objects/Groups
  and Layers controls; layer assignment and group/ungroup are Undo actions.
- Missing/stale object references and invalid membership are validated,
  and deleting member vectors cleans up orphaned layer/group records.
- Text glyph contour geometry and SVG/DXF authoring data are unchanged.

**CI and desktop verification pending.** Manual KDE Wayland GUI checks:
create three vectors, group two, click one and drag group, switch Node mode
to move a single anchor, hide/lock group, assign a layer and toggle its
visibility, save/reopen .cfd, Undo/Redo all steps, delete a grouped vector.
CNC output is still disabled. Next R1f: source-accurate CAD curve
join/trim/offset topology.

Update this handover with final PR, verified head/run, merge SHA, and exact
test count once all gates pass.

## Verified R1e native vector groups/layers — merged PR #115

[PR #115](https://github.com/newnetmp3/CarveFoundry/pull/115)
merged to `main` at **1034c32628bcc12b0e2322f209d9b1ccf366db08**.
Final exact feature head **7ec60f4c2124b65c901092549de8a4c87afd2ea8**
passed [CI #38010068138](https://github.com/newnetmp3/CarveFoundry/actions/runs/38010068138):
**69 core tests + 17 studio tests (86 total), strict Clippy and native
Linux release compilation**.

- Optional layer/group metadata in backward-compatible .cfd: persistent
  named custom layers, vector memberships, named flat groups. Virtual
  Base layer (ID 0) is always available. Vector/group/layer identities
  are checked against duplicates, missing references and invalid state.
- Objects explorer: group multi-selected vectors, select/drag full groups
  in Object mode, rename and ungroup, independently hide/lock groups.
  Node mode still supports individual editable anchors.
- Dedicated Layers explorer: create, rename, delete, assign membership,
  and toggle visibility or locks. Hidden vectors excluded from drawing,
  picking, marquee and snapping. Geometry edits respect effective locks.
- All organization state changes are individually undoable; deleting a
  member cleans layer/group references and removes invalid small groups.
- Regenerating editable text can preserve common source-layer assignment
  and an existing encompassing vector group. Regression fixtures verify
  text reflow, group drag, undo and project save/restore.
- No changes to analytic curve identities, SVG/DXF authoring data,
  cutter constraints or CNC NC output.

**Manual KDE Plasma/Wayland UI acceptance remains pending**: multi-object
selection, group dragging, group hide/lock, layer assignment and
visibility, .cfd reopen, Ctrl+Z/Ctrl+Y, and text regeneration should be
tested on the user's desktop. CI only proves automated tests/build.

The full progress diagram lives in
[docs/ROADMAP_DIAGRAM.md](ROADMAP_DIAGRAM.md). R0 code is complete with
desktop acceptance outstanding; R1 is advanced but **not fully done**;
R2–R7 are not yet implemented. **Next:** R1f source-accurate trim/join,
extend, offset, fillet/chamfer and associated geometry correctness QA.
CNC CAM/posted NC safeguards remain a later isolated gate.

| 2026-10-09 | PR #115 native layers and groups merged | [CI 38010068138](https://github.com/newnetmp3/CarveFoundry/actions/runs/38010068138): 69 core + 17 studio, strict Clippy, Linux release; merged 1034c326 | Real KDE groups/layers QA; R1f trim/join/offset; CNC export closed |

## Active R1f exact vector topology (first tranche)

User continued with "1" after verified PR #115. Baseline
8325c4e16dc78d2379a0a269cc1cc1dd30c7cd64, CI main green; no open
PRs at kickoff. Branch feature/rust-r1f-exact-vector-topology adds:
exact circular/cubic/line edge subdivision, endpoint trimming of those
original segments, straight end extension, orientation-aware join of two
open paths retaining circle/cubic source (optional true LINE bridge),
non-destructive parallel offset of straight-only paths, and true circular
fillets/straight chamfers at open line-line interior corners. Unsupported
general curve offset/closed-corner intersections fail with explicit errors,
never with raster preview approximation. Includes real UI palette controls
and validated/undoable Editor commands, layer and text safety checks.
See docs/TOPOLOGY_EDITING.md.

CI/merge still pending. Follow up with verified PR, exact CI head/test
counts/merge SHA. Manual desktop and independent SVG/DXF visual checks
still required. Next R1 continuation: click-targeted intersection trim,
closed-path corners, analytic curved offsets, fillet construction across
arc/line and arc/cubic junctions, then complete KDE acceptance before R2.
No CNC postprocessing/NC emission.

## Verified R1f exact analytic topology — merged PR #116

[PR #116](https://github.com/newnetmp3/CarveFoundry/pull/116)
merged to main at **5e5747bd6d6f1abd10ffd9d9c5bf9f1233a52a05**.
Final tested source head **2c378a3986ac96458f3a2377d1f344cc7923feed**
passed [Rust CI #38011306582](https://github.com/newnetmp3/CarveFoundry/actions/runs/38011306582):
**78 core + 17 studio = 95 tests, strict Clippy, native Linux release**.

- Native Rust `crates/core/src/topology.rs` is an exact-source analytic
  editing module, not a sampled display-geometry operation. It includes
  line/circular-arc/cubic splitting (exact Bézier de Casteljau subdivision);
  trimming the first or last open-path segment by fraction; straight-line
  endpoint extension; joining two oriented open paths while reversing
  circular sweep or cubic handle order and adding a real straight bridge
  if a small nonzero gap is allowed.
- New parallel offset remains deliberately restricted to **straight-only**
  open/closed contours: intersection-based miter joins and bounded
  displacement. Closed offset polygon is checked against self-intersection.
  General curved offsets and pathological open-path overlaps require
  a future robust native geometric solver, not a preview approximation.
- Interior *open* line-line corners support true tangent circular fillets
  and straight chamfers. Closed-loop corners and arc/cubic corner cases
  remain explicitly unsupported.
- All editing commands use atomic `Editor::apply`, original geometry
  validation, meaningful failures, Undo, layer/group lock protection,
  text source checks for joining, and layer preservation for new offsets.
- Studio Drawing palette includes **Edit Vector Topology**, numeric
  fraction/mm controls, edge chooser, start/end toggle, Join selected,
  Split, Trim, Extend, Offset, Fillet, Chamfer. Standalone feature guide
  `docs/TOPOLOGY_EDITING.md` includes acceptance and limitations.
- Automated Rust geometric fixtures check exact preservation of sampled
  curve points for split/trim (sampling only in TEST comparison), true
  arc radius, coordinate handling, orientation-aware joins, offset
  non-mutation and undo. Samples are NEVER stored as curves.

**Manual real KDE Plasma/Wayland checks still not run:** use an open
polyline with a 90-degree corner for fillet, test a cubic/arc split,
join endpoints of two separate open paths, offset a rectangle and Undo.
Check export/reimport in independent vector viewers. This is the FIRST
topology tranche, not full R1 completion; no CAM/G-code exists.

**NEXT R1g:** real click-targeted intersection splitting/trimming,
general mathematically sound curved offsets, closed contour corner
fillet/chamfer, more precise DXF/SVG acceptance and desktop QA before R2.
`docs/ROADMAP_DIAGRAM.md` now visualizes all phases R0–R7 including
the new verified R1f slice. CNC/NC export remains gated under R6.

| 2026-10-09/10 | PR #116 exact Rust topology slice merged | [CI #38011306582](https://github.com/newnetmp3/CarveFoundry/actions/runs/38011306582): 78 core + 17 studio, strict Clippy, Linux release; merge 5e5747bd | KDE topology QA, R1g intersection-aware tools and curved offsets |


## R1g active — exact intersections, closed corners and circular offsets

Continuing from verified `main` e49c79883e18478c8c66a0c37b9ae96ca3417cbd;
no open PRs. Branch `feature/rust-r1g-analytic-intersections` implements:

- Native Rust source-curve intersection engine `crates/core/src/intersections.rs`
  for bounded line-line, line-circular arc, and circular arc-circular arc
  segment pairs. Coincident circles and cubic pairs count as unsupported
  rather than producing approximated intersection points. On-demand scan
  caps 150k edge pairs/128 intersections, excludes hidden targets and
  performs no source sampling or frame-by-frame scan.
- Studio numeric topology panel can scan, select from exact crossings,
  render numbered canvas markers and enter a dedicated click-marker mode
  that suspends normal object/node gestures. New atomic editor commands
  recompute and verify selected crossing before Split or terminal Trim:
  changed/hidden geometry rejects without mutation.
- Closed-loop line-line vertices now support native chamfer/true circular
  fillet, including the wraparound vertex. Offset creates non-destructive
  true circular arcs from single open arc or validated common-center,
  consistent-winding closed circle. Arbitrary cubic/elliptical/mixed offsets
  remain unsupported and cannot be approximated as persisted geometry.
- `docs/INTERSECTION_EDITING.md` explains pointer workflow, supported
  geometry, strict refusal behavior and KDE manual acceptance.

CI/PR merge **pending** at this stage: run core/studio tests, strict
Clippy, native Linux release, then update this handover with exact PR/run/
head/merge IDs and the complete R0–R7 roadmap diagram.
Next R1 work after verified merge: general cubic intersections and
mathematically robust curved offsets, targeted extend-to-boundary,
complex corner situations, and real KDE Wayland UX QA. CNC postprocessing
and NC output remain locked.

## Verified R1g exact-intersection and closed-circle CAD — merged PR #117

[PR #117](https://github.com/newnetmp3/CarveFoundry/pull/117)
merged into `main` as **5663414c7f55db12dfe15734d51fa6790d7fd6dd**.
Exact final feature head **c583cf3cd585d82eb729efbecaf5bc2367ba9f2a**
passed [Rust CI #38012411651](https://github.com/newnetmp3/CarveFoundry/actions/runs/38012411651):
**86 core tests + 17 studio tests (103 total), strict Clippy, native
Linux release build**. First run passed all tests but failed a
non-geometric strict Clippy duplicated-branch lint in the new radius
helper; corrected final run green.

Implementation:
- `crates/core/src/intersections.rs`: exact analytic intersections on
  retained line-line, line-true circular arc, and arc-arc segment pairs.
  On-demand candidate scan (<=150k edge pairs, <=128 hits), finite bounds,
  sweep restriction, tangent deduplication. Cubic and coincident-arc pairs
  counted as unsupported instead of being preview-sampled.
- `Action::SplitAtIntersection` and `TrimAtIntersection` recompute and
  revalidate the selected source/reference geometry immediately before
  atomic, one-history-step edit. Moved/missing/hidden/locked sources fail.
  Terminal-only trim is limited to open-path Start/End segments. No
  fabrication of an intersection when a reference has changed.
- Native Studio `Edit Vector Topology` panel adds Find intersections,
  numbered list and canvas markers, on-canvas marker pick mode which
  suspends ordinary vector selection while active.
- Line-line corner true circular fillet and chamfer now support CLOSED
  contours (including first/wraparound vertex), still rejecting
  unsupported curved corners.
- `topology::offset_exact` adds source-exact circular offset for one
  open true circular arc or full concentric all-arc closed circle, along
  with pre-existing straight-line offsets. General cubic/mixed offsets
  fail closed. Native Circle shape currently uses cubic approximations,
  not exact circular arcs: its general curved offset remains blocked.
- `docs/INTERSECTION_EDITING.md` explains scope, explicit errors and
  full desktop acceptance checks; `docs/ROADMAP_DIAGRAM.md` shows R0-R7
  with R1g delivered and R1h/desktop QA outstanding.

**Manual KDE Plasma/Wayland QA remains necessary**: crossing list and
marker click, Split/Trim and Undo, stale-crossing revalidation, closed
fillets at every vertex, offset exact arc vs cubic Circle, SVG/DXF
independent geometry viewer. CI does NOT demonstrate mouse performance
or production machine behavior. CNC G-code/NC export is disabled.

**NEXT R1h:** robust analytic cubic intersections, targeted
extend-to-boundary, general mathematically sound curved offsets,
line/arc/cubic corner workflows, native 2D editor UX/QA and file-format
golden fixtures. R2-R7 remain future phases; machine output gates R6.
User requests `1` to continue, take a substantial next verified slice
without repeated approvals.

| 2026-10-10 | PR #117 exact crossings / closed corners / circular offsets merged | [CI 38012411651](https://github.com/newnetmp3/CarveFoundry/actions/runs/38012411651): 86 core + 17 studio, Clippy, Linux release; main 5663414c | R1h cubic intersection geometry, KDE pointer and independent interchange acceptance |

## Active bug fix — omitted cubic crossings from R1g

The owner supplied a KDE screenshot showing "2 crossings; 5 unsupported
edge pairs" with a five-edge polygon and a blue curved vector. The
original intersection dispatcher returned an unsupported marker for
every pair involving Curve::Cubic. This is a real analytic geometry gap.

Branch fix/r1g-bezier-intersections introduces a pure Rust Bézier
intersection solver for cubic-line, cubic-true-circle (polynomial
root isolation, tangent roots) and cubic-cubic (control-hull interval
subdivision and original-source Newton refinement). Overlaps and
unresolved degenerate cases are explicitly reported as unsupported.
The editor continues to validate hits before atomic Undoable edits.
Tests include screenshot-style polygon/cubic geometry, reverse
parameter order, line/circle tangencies and identical-curve refusal.

CI/merge still pending. After final green tests, strict Clippy and Linux
release, update rolling handover with PR/run/test/merge details. Owner
KDE/Wayland original-project regression still required.
CNC/NC generation remains disabled.

## Verified screenshot-driven Bézier intersection fix — PR #118

The user's Arch KDE screenshot of a five-segment closed orange path
crossed by a blue Bézier showed "2 exact crossings; 5 unsupported edge
pairs". The R1g dispatcher skipped ALL Curve::Cubic-containing pairs.
This bug was reproduced and fixed in
[PR #118](https://github.com/newnetmp3/CarveFoundry/pull/118),
merged to main as **c3f1afc3a7d794b534583b76078edba3bf1a3dee**.
Final tested head **dccd3d38b7a6022ac2f8cf315ceafb030e4b654c**
passed [Rust CI #38013659809](https://github.com/newnetmp3/CarveFoundry/actions/runs/38013659809):
**94 core tests + 17 studio tests = 111**, strict Clippy and native
Linux release compilation.

New pure Rust crates/core/src/bezier_intersections.rs evaluates source
cubic-line polynomial roots (degree 3), cubic-true-circle polynomial
roots (degree 6), and bounded cubic-cubic Bézier hull subdivision with
original analytic curve Newton residual verification. The polynomial
root finder partitions by derivative critical points to detect
tangencies, including even-multiplicity roots. No flattened preview
geometry substitutes for source vectors. Coincident/incomplete/unsafe
edge pairs remain explicitly unsupported instead of fabricated matches.
The existing full GUI pick-marker mode, exact source fractions, stale
hit revalidation, one-history-step Undo and source curve definitions
are unchanged. UI heading/tooltips now accurately include Béziers and
describe true unresolved overlaps rather than falsely implying all
cubics are unsupported. Primary intersection guide updated.

Automated tests include a screenshot-inspired closed five-edge shape
versus curved Bézier, reversed source/reference fraction consistency,
multi-hit cubic-line/cubic-cubic examples, line/cubic tangencies,
cubic-arc/circle hits, coincident Bézier refusals and stale-scan tests.

**Actual original KDE design still needs manual acceptance**:
git pull origin main; cargo run --release -p carvefoundry-studio;
select the closed five-edge object, Find intersections, inspect newly
numbered crossing markers along the blue cubic. Crossings should no
longer show five unsupported pairs solely because they involve a cubic.
Capture the source .cfd or follow-up screenshot if any actual missed
crossing remains, especially endpoints, coincident segments or
within-path self-intersections; those are separate topology gaps.

Next R1h: robust source-preserving cubic/mixed offsets, advanced
intersection-based extensions/complex corners, source selection UX
and independent KDE Wayland/third-party file QA. All CAM/NC machine
output remains disabled pending R6.

| 2026-10-10 | PR #118 Bézier crossing regression repaired | [CI #38013659809](https://github.com/newnetmp3/CarveFoundry/actions/runs/38013659809): 94 core + 17 studio, strict Clippy, Linux release; merged c3f1afc3 | Owner's original 5-edge design desktop QA; R1h offset/extend |

## Active R1h source-accurate Extend-to-Boundary (with marker contrast)

User asked to apply dark number backgrounds to R1g intersection markers,
then continue development. PR #119 fixes UI contrast on native canvas:
opaque dark rounded-number badges, contrasting cyan/amber rings, adaptive
position near canvas viewport edges, and positioning regression tests.
KDE visual acceptance still pending.

Following branch `feature/rust-r1h-extend-to-boundary` builds upon
that UX fix, with an independent substantial R1h geometry tranche:
- `nearest_extension_crossing` casts a bounded forward terminal-line
  ray through the exact analytic line/arc/cubic intersection engine.
  Chooses nearest forward crossing, rejects collinear overlap or
  unresolved degeneracies and enforces max reach 0.001–10000 mm.
- `Action::ExtendToBoundary` checks visible reference/ editable
  source, requires distinct paths and an open straight source terminal,
  and calls the validated existing `extend_line` function. One Undo
  transaction; source geometry stays analytic, reference unchanged.
- Native Drawing topology tools offer two selected vectors, choose
  source vs reference, start/end and maximum reach. No CAM/NC export.
- Tests: line/reference nearest intersection, start vs end, maximum
  reach failure, cubic reference, true arc with two possible hits,
  collinear-overlap refusal, atomic undo, locked/hidden paths.

CI/merge results and current acceptance are recorded in the verified
section below. Next: source-preserving advanced curved offsets,
arc/cubic corner tools, and full KDE/Wayland/CAD interchange QA.

## Verified R1h marker contrast + Extend-to-Boundary — PRs #119 and #120

**Marker readability** [PR #119](https://github.com/newnetmp3/CarveFoundry/pull/119):
merged `398b5e75e262852685bb9c6ad973ee5c0009c580`; exact head
`9d21652a1ee0b1600b3879ab7a756bdc2f4a04d8` passed
[CI 38014413520](https://github.com/newnetmp3/CarveFoundry/actions/runs/38014413520):
**94 core + 18 studio tests (112), strict Clippy, Linux release**.
Native canvas draws high-contrast dark rounded badges with white marker
numbers, amber selected/cyan normal borders, and label positioning
within the viewport. Automated badge placement tests cover corners
and viewport boundaries; actual KDE visual acceptance still pending.

**Targeted straight-end extension** [PR #120](https://github.com/newnetmp3/CarveFoundry/pull/120):
merged `51ab853abb19922f9e589fad0766613a4f5dc863`; exact head
`809f716595cda32a5ce565672fabe602941c8c8f` passed
[CI 38014783760](https://github.com/newnetmp3/CarveFoundry/actions/runs/38014783760):
**99 core + 18 studio tests (117), strict Clippy, Linux release**.

Implementation: `intersections::nearest_extension_crossing` shoots a
bounded straight terminal ray from an OPEN path against every exact
line/true-circle/cubic Bézier segment of a separate reference path.
It chooses the nearest forward hit within explicit maximum reach,
rejects collinear overlaps and numerically unresolved crossings,
and never derives a source point from preview samples. The
`Action::ExtendToBoundary` checks source editability, reference
visibility and distinct source/target identities. Only the source
straight terminal node changes, atomically in ONE Undo operation;
the reference path remains untouched. Two-vector UI lets users
choose source vs target, Start/End and maximum reach.
Regression tests cover first/last, reach bounds, true circular arcs
with two crossings, cubic references and differing origins,
ambiguous collinearity and locked/hidden no-mutation paths.

**Manual KDE Plasma/Wayland acceptance is outstanding** for the user
screenshot marker contrast, actual pointer selection, two-vector
extension controls and save/reopen SVG/DXF. Source edits are validated
by CI but not certified for external CAD or physical CNC.

[Full updated roadmap](ROADMAP_DIAGRAM.md) marks R1h contrast/extension
done in code; **R1 not complete**. Next **R1i**: mathematically sound
general curved offsets and complex line/arc/cubic junction tools,
CAD picker/selection usability QA and independent golden interchange
files. R2-R7 remain planned, and G-code/NC remains gated in R6.

| 2026-10-10 | PR #119 marker badges merged | [CI 38014413520](https://github.com/newnetmp3/CarveFoundry/actions/runs/38014413520): 112 tests, Clippy, Linux release | Manual KDE contrast |
| 2026-10-10 | PR #120 Extend-to-Boundary merged | [CI 38014783760](https://github.com/newnetmp3/CarveFoundry/actions/runs/38014783760): 117 tests, Clippy, Linux release | R1i advanced curve offsets and desktop QA |

## Active R1i — curved endpoint extension addressing owner's KDE screenshot

User selected two vectors (closed pentagon and open Bézier source #5),
but Extend end to reference was disabled because the UI hard-coded
`Curve::Line` eligibility. User replied "1" to the proposal to extend
curved endpoints, meaning CONTINUE.

Branch `feature/rust-r1i-extend-curved-ends` adds a Rust
`curve_extension.rs` module handling exact source-polynomial cubic
continuation and true circular-arc continuation (same center, radius and
winding) to first validated forward crossing with a distinct analytic
reference. The exact source intersection engine handles reference lines,
true circular arcs and cubic Béziers. Straight terminals still dispatch
to the preexisting line extension. Original source geometry retained
as-is; a new analytic segment and node are added, reversible in one Undo
transaction. Cubic continuation algebraically reparameterizes the
existing degree-three polynomial outside [0,1], preserving position, tangent direction and geometric curvature at the seam, not approximated by a straight
tangent line. Curved reach measured by bounded numerical arc-length,
not sampled design geometry. Restrict cubic polynomial extrapolation to
two parameter lengths and arcs to less than one revolution; reject
indeterminate/overlap cases or no crossing.
UI now allows open curve terminals and displays the reason if a source
is closed/locked/hidden, instead of inexplicable greying. Source dropdown
allows the user to pick the open Bézier rather than the closed pentagon.

Tests: cubic forward/backward polynomial continuation, retained curves
and circle radius/winding, undo, invalid paths/limits. Manual user's
exact KDE artwork screenshot, external SVG/DXF and source edit workflow
still require acceptance. See docs/CURVE_EXTENSION.md.

**Final CI/merge verification:** see the section below. Keep manual
KDE and independent file-format verification separate.
R1 remains in progress, R2-R7 are not implemented; CNC/NC remains disabled.

## Verified R1i — open Bézier and circular endpoint extension, PR #121

The owner's KDE screenshot showed two selected analytic vectors
(closed polygon and open Bézier), but **Extend end to reference** was
greyed out because UI required the source terminal segment to be a
straight line. User reply "1" requested continuing the proposal to
support curved endpoint extension.

[PR #121](https://github.com/newnetmp3/CarveFoundry/pull/121)
merged into main as `7f58424451301b8b9be8fbe447b6ab61be0c69a1`.
The EXACT tested feature head
`901460c7447aff05bb0a38c820693cf544b3daa9`
passed [Rust CI 38016223523](https://github.com/newnetmp3/CarveFoundry/actions/runs/38016223523):
**104 core + 18 studio = 122 Rust tests, strict Clippy, Linux release**.
Early CI runs found and fixed two UI borrow/move errors; final exact
revision green.

Delivered pure Rust `crates/core/src/curve_extension.rs`, which
adds source-preserving continuation for any OPEN analytic path whose
selected terminal is:
- Line: existing straight endpoint extension unchanged.
- True circular arc: adds a new arc of the original exact center,
  radius and winding direction up to the nearest forward source-accurate
  reference crossing; max one-turn arc span.
- Cubic Bézier: algebraically reparameterizes the SAME original cubic
  polynomial beyond t=0/t=1 to the first forward source-accurate
  crossing against line/true arc/cubic reference. Appends a new retained
  cubic segment with original node/segment IDs and controls unchanged;
  geometric position, tangent direction, and curvature are smooth
  (G2 continuity). Bounded cubic continuation to two additional
  normalized parameter lengths, with arc-length reach in millimetres.
  Original curve is never flattened to preview geometry.

The existing `Action::ExtendToBoundary` checks current source
lock/visibility/reference state, preserves independent reference
geometry and remains a single Undo/Redo edit. The Drawing topology
panel now enables OPEN Bézier/arc sources and explains *why* a source
is disabled (closed, hidden, locked), instead of silently restricting
to straight segments. Source dropdown picks open Bézier vs closed
polygon. Meaningful errors for nonintersection, zero derivative,
unresolved overlapping reference, max reach and node count.

**Manual KDE Plasma/Wayland acceptance still due** on user's actual
blue Bézier/orange polygon file. The mathematically continued Bézier
MAY NOT cross that particular polygon; in that case the action should
be enabled but return "no forward source-curve intersection" rather
than silently bending a curve. Inspect new segments, Undo, save/reopen
and independent SVG/DXF exports. See docs/CURVE_EXTENSION.md.

`docs/ROADMAP_DIAGRAM.md` now marks PR #121 delivered in R1.
R1 is NOT fully complete; general mixed/cubic offset, advanced curve
corners and deep KDE/Wayland UX + file-interchange QA remain.
R2–R7 are future work and CNC/G-code/NC output remains disabled.

| 2026-10-10 | PR #121 open cubic/arc extension merged | [CI 38016223523](https://github.com/newnetmp3/CarveFoundry/actions/runs/38016223523): 122 tests, Clippy and Linux release; merge 7f584244 | KDE user's exact Bézier screenshot, advanced offsets/corner QA |

## Dark-mode-safe roadmap visualization (docs/UI-only)

A user screenshot showed the assistant's attempted Mermaid theme initialization rendered
`Invalid or unsupported diagram` under an aggressive browser dark-mode extension.
The original repository Mermaid source was valid, but its default theme/stylesheet
was also susceptible to inverted low-contrast text. The roadmap now uses
`docs/ROADMAP_HIGH_CONTRAST.svg`: a self-contained static SVG with explicit
dark backgrounds, near-white text, green implemented, blue active, amber next,
gray future and red locked statuses. `docs/ROADMAP_DIAGRAM.md` embeds the SVG
instead of a Mermaid fenced block, retaining its plain Markdown phase table
as the accessible fallback. This changes **documentation presentation only**:
no Rust CAD behavior, acceptance or CNC/NC safety gate has changed.

If the diagram needs another status update, edit the **SVG artwork and its phase
text together** (and the matching Markdown table). Verify text contrast and
legibility in KDE Firefox with the owner's extension before treating desktop
accessibility as accepted.

## Verified roadmap readability fix — PR #122

[PR #122](https://github.com/newnetmp3/CarveFoundry/pull/122)
merged as `3096e98dde72661f2bad70e6a0914299c33b8a8b`.
Exact tested head `720fd99c71f626f9078ce666f13b5c48e78f4bba`
passed [CI #38102622267](https://github.com/newnetmp3/CarveFoundry/actions/runs/38102622267):
Rust tests, strict Clippy, native Linux release.
The user-visible R0–R7 roadmap now embeds
[high-contrast standalone SVG](ROADMAP_HIGH_CONTRAST.svg), no client-side
Mermaid syntax or theme directives; a readable Markdown table remains
as fallback. Locally rendered SVG passed XML parsing and measured text
contrast ranging from 7.94:1 to 12.98:1. Owner KDE Firefox dark-mode
plugin confirmation is not yet recorded. This was a documentation-only
rendering/accessibility fix, not a change to CAD capabilities or CNC gates.

## Active R1j — exact mixed line / circular-arc tangent offsets

Next step after verified high-contrast roadmap PR #122:
branch `feature/rust-r1j-mixed-line-arc-offsets` from
main `2891401b595c972bf537684eadd3fe8c6e39c2e8`.

Adds `crates/core/src/mixed_offsets.rs`, new source-exact parallel
offset for OPEN/CLOSED paths composed of straight segments and true
circular arcs at **tangent G1 curve joints**. Left-side signed offset
on open, outward/inside independent of winding on closed; closed
winding via exact Green's theorem line+circle sector area. Original
circular centers, sweep direction, source IDs and undoable project
geometry retained. Line/line corners in mixed chains use bounded
analytic miters. Any non-tangent curved joint, radius collapse,
excessive miter or general Bézier cubic offset is explicitly rejected
instead of approximated with preview samples. An arbitrary cubic
polynomial generally has no exact cubic polynomial offset.

Native Drawing topology panel tooltip/help updated. Regression
coverage includes tangent arc+line with exact shifted endpoints,
closed racetrack with independent semicircle centers, inward/outward
winding, line-line miter preceding arc, sharp arc/line refusal,
and editor atomic Undo/layer locks, original not mutated.
See `docs/TANGENT_OFFSETS.md` for actual KDE Wayland acceptance
and important limitations. Global pathological offset topology
certification remains future work. CAM/G-code/NC output still locked.

**Final verification:** PR #123 and CI checks merged and documented
in the verified section below. Retain separate manual KDE/Wayland,
external CAD interoperability and global offset correctness gates.
Next R1: sharp curved round/bevel join, cubic polynomial controlled
approximation with explicit tolerance/type, global intersections,
desktop usability and golden SVG/DXF QA before R2.

## VERIFIED R1j — exact tangent line/arc offsets merged PR #123

[PR #123](https://github.com/newnetmp3/CarveFoundry/pull/123)
merged as `4f8ee59b5d3cabb45ae0ce5ebe24021336c18d5c`.
Final exact feature head `0cb5f1e19e3cbc5a88e48f7eaacc1d530e156049`
passed [CI #38104323749](https://github.com/newnetmp3/CarveFoundry/actions/runs/38104323749):
**109 core + 18 studio = 127 Rust tests**, strict Clippy,
native Linux release. Initial CI passed all tests but encountered
a strict Clippy duplicate if-branch diagnostic in the offset
dispatcher; simplified then final exact head passed all gates.

Native pure Rust `crates/core/src/mixed_offsets.rs` implements
source-exact parallel offsets on mixed straight and TRUE CIRCULAR
arcs with tangent G1 curved junctions, including open and closed
chains with multiple independent circle centers. It uses Green's
theorem for exact circular-sector/straight-line area and correct
closed outward/inward winding sign. Circular arcs keep exact
center/winding/source IDs, lines remain true parallels, line-line
corners use bounded miters; sharp curved junctions, radius collapse,
degenerate area, general cubic Bézier offsets and unsafe miters
fail closed. Editor `OffsetLines` still creates one new editable
vector preserving source layer and one-step Undo. Owner's original
geometry is unmodified and kept in project history. Additional
tests check clockwise arc+line, CCW closed racetrack, inward/outward
radii and winding, mixed corner miters, non-tangency refusal,
project Undo, original path identity and layer locks.

**Important limitation:** This is **tangent line/circle geometry**,
not a general mixed Bézier offset or topologically complete curve
offset engine. Global pathological self-crossing cannot yet be
independently certified from these local tangent tests. See
[docs/TANGENT_OFFSETS.md](TANGENT_OFFSETS.md) for exact scope and
manual KDE/Wayland tests. Real owner desktop, third-party SVG/DXF
and machine QA still outstanding.

Roadmap [docs/ROADMAP_DIAGRAM.md](ROADMAP_DIAGRAM.md) and its
high-contrast SVG have been updated for PR #123, preserving a
readable dark-mode-independent graphic and text fallback. Next
**R1k**: robust sharp arc-line/arc-arc joint treatment, explicit
approximation/error-control model for general cubic offsets if
justified, whole-contour intersection/overlap correctness, desktop
CAD pointer QA, and SVG/DXF golden file checks. R2–R7 remain future
phases; CNC NC output is intentionally disabled pending R6.

| 2026-10-10/11 | PR #123 exact tangent mixed line/arc offsets merged | [CI #38104323749](https://github.com/newnetmp3/CarveFoundry/actions/runs/38104323749): 127 tests, strict Clippy, Linux release; 4f8ee59b | R1k sharp curved joins + global offset QA; KDE acceptance |


## Active R1k — offset contour integrity (work in progress)

Verified baseline remains main cd8b4d7250dc1c463dfed5587e194304f618420d
with R1j [PR #123](https://github.com/newnetmp3/CarveFoundry/pull/123)
merged and exact tested head 0cb5f1e19e3cbc5a88e48f7eaacc1d530e156049
passing [CI #38104323749](https://github.com/newnetmp3/CarveFoundry/actions/runs/38104323749).
Development branch: feature/rust-r1k-global-offset-validation.

Scope: retained analytic line/circle **whole-chain simple-contour guard** for
mixed parallel offsets; run on both existing source and resulting offset,
reject nonadjacent contacts/crossings, improper adjacent contacts, straight
overlap/backtracking and ambiguous concentric arc pairs without mutation.
Bounded at 256 segments and 32,640 unordered pairs, no preview samples
stored or used. Native inspector reports rejected contours; exact arc
centers, radii, Undo, layers and G-code export gating are preserved.
docs/TANGENT_OFFSETS.md specifies manual acceptance and limitation.

This is a **subset**, not closure, of R1k. Next: sharp line/arc and
arc/arc join styles with proof, coincident-circle sweep classification,
robust global offset validity and desktop CAD golden QA. Real KDE
Plasma Wayland and independent SVG/DXF acceptance have NOT run. CI
is pending for this new branch. No NC export/preflight/CNC claims.

| 2026-10-10 | R1k whole-chain analytic offset validation implementation branch | Tests/strict Clippy/native Linux release pending; no merge claimed | Verify CI, merge and update verified checkpoint; then sharp circular joins |


## VERIFIED R1k sub-milestone — full-chain analytic offset integrity, PR #124

[PR #124](https://github.com/newnetmp3/CarveFoundry/pull/124)
merged as main commit **108a93a21bfca8a2a519e740d60991dc6a9f84ed**.
The exact tested feature head **9560aa89ef74098f7e0151f4685a30e3b2d22e8f**
passed [native Rust CI #38105033834](https://github.com/newnetmp3/CarveFoundry/actions/runs/38105033834):
**113 Rust core + 18 studio = 131 tests**, strict Clippy and native
Linux release compilation. GitHub reported all steps successful.

Pure Rust crates/core/src/intersections.rs now includes bounded
validate_simple_analytic_chain, checking **all** pairs of retained
analytic line/circular edges of one mixed chain (up to 256 segments /
32,640 pairs), not visual samples. Adjacent source edges may contact
only at their genuine shared endpoint; remote crossings/touches, line
backtracking/overlap and unresolved coincident circle supports reject.
crates/core/src/mixed_offsets.rs checks both source and generated
exact mixed offset before the Editor inserts the new vector, while
retaining existing circle/line solvers, source layer and atomic Undo.
UI displays explanatory rejection language. Regression tests cover
simple open/closed vectors, crossing and touching, backtracking and
mixed arc-line rejection. Detailed limits and owner KDE checklist:
[docs/TANGENT_OFFSETS.md](TANGENT_OFFSETS.md).

**Scope boundary:** does NOT add round/bevel sharp circular joins,
coincident-arc sweep proof, full generalized offset topology, or
a mathematically controlled cubic parallel-approximation solution.
Global verification applies to the mixed tangent offset path;
standalone circular/straight solvers have their own prior checks.
Physical KDE Plasma/Wayland, DXF/SVG external interoperability and
any machine tests remain UNVERIFIED. CNC/NC G-code remains disabled.

**NEXT R1k/R1:** evaluate exact sharp circular joins with validated
corner admissibility, coincident-arc interval classification, closed
offset topology goldens, source-geometry interchange fixture QA and
actual Arch KDE Wayland gestures; then proceed to R2 (3D CAD) only after
priority desktop R1 usability is acceptable.

| 2026-10-10/11 | PR #124 mixed-offset analytic simple-chain validation merged to main 108a93a2 | [CI #38105033834](https://github.com/newnetmp3/CarveFoundry/actions/runs/38105033834): 131 tests, strict Clippy, Linux release | R1k sharp curved joins and KDE/Wayland/third-party file QA |


## Active R1k convex round-join slice — after verified PR #124

Branch feature/rust-r1k-rounded-convex-offset-joins starts from
main e66401f538eff6d918fbba7ed07b91180f14effa.
Adds a **separate opt-in action** named Create rounded offset in the
native Drawing topology inspector. Existing default Create offset
vector and its rejection behavior are unchanged.

Pure Rust mixed_offsets::offset_round_chain constructs true retained
circle sectors centered on a source vertex, of radius equal to the
signed offset magnitude, for geometrically **convex-on-the-offset-side**
sharp line/line, line/circle and circle/circle seams. Original segment
identities and exact line/circle centers/radii survive; inserted join
nodes/segments get distinct increasing IDs. Open positive means left,
negative right; closed positive means outward independent of winding.
Line-line concave joints use existing bounded analytic miters; sharp
**concave curved** joints reject rather than bridging across the inside
or inventing trimmed arcs. Reversals, cubic offsets, circle collapse,
degenerate sweeps, too many nodes, self-crossings and unresolved circle
overlaps fail closed. Source and output are validated with the R1k
whole-chain analytic check. Standalone concentric circle solver survives.

Editor adds Action::OffsetRounded with project atomic Undo/Redo,
source lock/layer enforcement and independent new offset vector.
Tests cover line→circle and circle→circle sharp joins, outward closed
triangle round joins, rejected inward curved corner and editor
Undo/locked-layer rollback. This does **not** implement concave
circular trimming, general cubic parallel offset or machining safety.

CI verification is pending for this feature branch; do not claim
a merged milestone until the exact head passes tests, strict Clippy
and Linux native release, and PR merge completes. Manual KDE Plasma
Wayland pointer tests and independent SVG/DXF correctness are also
outstanding. CNC/NC remains disabled. Next R1k: safe concave
circle-line/circle-circle trimming, same-center arc interval proof,
offset golden contours, then remaining R1 acceptance before R2.


## VERIFIED R1k — exact convex circular joins, PR #125

[PR #125](https://github.com/newnetmp3/CarveFoundry/pull/125)
merged to main as 3a2e107dd6d07f598788a3493e0e320eafccb5c2.
Exact tested source head ca543417bd2deefbbebf6401c1f06f8b9ef3d82e
passed [Rust CI #38105790548](https://github.com/newnetmp3/CarveFoundry/actions/runs/38105790548):
**118 core + 18 studio = 136 Rust tests**, strict Clippy and
native Linux release compilation. Initial run #38105710124 failed
one incorrect regression assertion that had confused the layer ID
with the independently allocated offset path ID; exact corrected
feature head passed the full pipeline.

The opt-in Create rounded offset (Editor Action::OffsetRounded)
makes source-faithful radius-|offset| circular joins around convex
sharp line/line, line/arc and arc/arc vertices. Original primitive
IDs and circle centers are preserved, generated join elements get
unique IDs, signed open/closed offset convention is maintained and
source/result full-chain analytic crossing checks apply. Existing
miter/tangent mode is unchanged. Layer locks, atomic Undo/Redo
and save compatibility remain in force.

**Not complete R1k:** sharp concave circle joins still need exact
support trimming; coincident arc sweeps need overlap proof; general
Bézier cubic parallels remain unsupported. No real KDE Plasma
Wayland pointer QA, third-party SVG/DXF interoperability acceptance,
CNC tests, R6 safety acceptance or NC export. Next: concave
arc/line and arc/arc trimming, complex golden contours and
real Wayland + external CAD QA before moving toward R2.

| 2026-10-10/11 | PR #125 exact convex rounded offsets merged | [Rust CI #38105790548](https://github.com/newnetmp3/CarveFoundry/actions/runs/38105790548): 136 tests/Clippy/Linux release; merge 3a2e107d | Exact concave arc trims and real KDE/file interchange QA |


## Active R1k — finite-sweep concave circular offset trim

New development branch **feature/rust-r1k-concave-circular-trims**
from verified main e6990a3f1a4615d40aa3033dad457f11e0ef5042
(after merged PR #125, exact CI #38105790548).

The existing opt-in **Create rounded offset** action now accepts a
concave sharp line/circular or circular/circular joint when the
displaced supports yield exactly ONE point that lies strictly inside
BOTH original finite segment sweeps. True line/circle and circle/circle
support intersections are computed mathematically, and each candidate
is tested against the actual bounded arc angles and line parameters.
This removes only edge portions: no circle extrapolation, no reversed
traversal, no zero-length edges, no silent major-arc insertion.
The trim reach is bounded and the R1k source/result global analytic
intersection guard still applies. Convex true radius-|distance|
joins and default legacy tangent/miter offset stay as before.
Same-center circles, ambiguous multiple hits, candidates outside
short arcs, cubic parallels and unsafe radius/topology remain rejected.
No new .cfd schema, CAM or G-code.

Added regression cases for concave line->arc, arc->line, arc->arc,
short-arc refusal and original-identity preservation in
crates/core/src/mixed_offsets.rs. Owner KDE/Wayland acceptance is
described in docs/CONCAVE_OFFSET_TRIMS.md.

**Status: branch implementation, CI / merge not yet verified.**
Follow-on: coincident arc sweep interval classification, larger offset
topology goldens, external SVG/DXF interoperability, Wayland QA.
Do not treat CI as physical CNC safety validation.


## VERIFIED R1k — finite-sweep concave circular offset trimming, PR #126

[PR #126](https://github.com/newnetmp3/CarveFoundry/pull/126)
merged into main as **907b1509133d09b55503d5ea75253a81abe13ee7**.
Exact feature head **ded15b52f95cdededbd2492a63c1a18208553e44**
passed [native Rust CI #38106382405](https://github.com/newnetmp3/CarveFoundry/actions/runs/38106382405):
**120 core + 18 studio = 138 tests**, strict Clippy, native
Linux desktop release build, with no failed CI stages.

Source-exact concave support trimming for opt-in Create rounded offset
uses algebraic line-circle and circle-circle intersections and accepts
only a unique crossing proven to lie inside the finite sweeps of BOTH
displaced incoming/outgoing segments, with nonzero retained lengths,
bounded trim reach and no reversal/extrapolation. Invalid short arcs,
ambiguous overlapping circles, two valid intersections, cubic offsets,
global self-crossings and radius collapse reject without changing the
design. The previous exact convex round joins and original tangent/
miter Create offset vector remain intact. Original analytic segment
IDs, centers and sweep directions, Undo/Redo and layer locks remain
covered by the same editor transaction. Detailed proof and manual
checklist: [CONCAVE_OFFSET_TRIMS.md](CONCAVE_OFFSET_TRIMS.md).

**Next R1k:** coincident-circle sweep interval classification, richer
adversarial closed-contour golden tests, whole-offset topology
verification and real owner Arch KDE Plasma Wayland interactions plus
independent external SVG/DXF file QA. No claim of completed desktop
acceptance, physical router trials, CAM, safety preflight or G-code.
R1 is still IN PROGRESS; R2–R7 remain planned/safety gated.

| 2026-10-10/11 | PR #126 exact concave arc/line and arc/arc finite-sweep trims merged | [CI #38106382405](https://github.com/newnetmp3/CarveFoundry/actions/runs/38106382405): 138 tests, strict Clippy, native Linux release; merge 907b1509 | R1k coincident arc sweeps and goldens; owner KDE/Wayland and third-party interchange |


## Active R1k — coincident true-circle angular sweep proof

Feature branch feature/rust-r1k-coincident-arc-sweeps follows the
verified PR #126 baseline (main 7b3d884c11847f05381e70017dbab3364dcdf5c4).

Pure Rust intersections.rs now classifies pairs of source-true arcs
with the same center using split CCW angular intervals over 0°/360°,
regardless of clockwise/counterclockwise traversal. It distinguishes
one isolated common endpoint (eligible when it is the actual
neighboring node) from a **nonzero angular overlap** (hard error).
Separate concentric radii are disjoint; numerically near-coincident
but not exact supports remain conservatively unresolved. Wrong
nonadjacent contacts still reject, and repeated circle traversals
fail before any offset. The special all-circular closed solver now
validates both source and result against remote overlapping sweeps.
Split true arcs with one common center remain source-retained and
can be offset using the prior exact circle/mixed solver and round
mode. Stable IDs, project schema, atomic Undo, layer locks, and
R6 safety gates are unchanged.

Unit regressions include angular seam endpoints, reversed parameter
order, different-radius concentric circles, backtracking and
multi-revolution overlap, nonadjacent touches, closed four-quarter
circles and split-arc+line exact offsets. See
[COINCIDENT_ARC_SWEEPS.md](COINCIDENT_ARC_SWEEPS.md).

**Status: implementation on branch, CI/PR merge pending.** No real
KDE Wayland owner tests or independent SVG/DXF visual validation.
Next after verified CI: adversarial closed offset golden shapes,
SVG/DXF roundtrips and interaction QA. CAM/NC still intentionally off.


## VERIFIED R1k — coincident circular sweep classification, PR #127

[PR #127](https://github.com/newnetmp3/CarveFoundry/pull/127)
merged as **28d01d35b65a21eba9e2446f1f22d2a04f57a8c4**.
The exact tested feature head **12b8b275c00ecc9351117ff727b5c0606f6593d1**
passed [native Rust CI #38107164700](https://github.com/newnetmp3/CarveFoundry/actions/runs/38107164700):
**127 core + 18 studio = 145 Rust tests**, strict Clippy and
Linux desktop release build. Two earlier CI revisions failed one
Rust inference error then a Clippy nested-if diagnostic; final
exact head completed all gates without failures.

Rust analytic intersections now classify truly same-center circular
arcs by source-accurate angular sweep intervals, split at
0°/360°. Reversed traversal and nonadjacent contacts are checked.
One genuine endpoint contact between neighboring source arcs is
allowed; positive-length common sweep or repeated circle traversal
is a hard overlap error. Distinct concentric radii are disjoint.
Near-coincident but not provably exact supports still fail closed.
The dedicated concentric circle offset now validates full source
and output sweeps, preventing a multi-revolution source from
pretending to be a simple circle. Exact split circular arcs in
mixed profiles remain editable and offset-capable without sampling.
No .cfd schema, original IDs, undo history, layer rules or CNC
output rules changed. Detailed source-level test and owner KDE
acceptance: [COINCIDENT_ARC_SWEEPS.md](COINCIDENT_ARC_SWEEPS.md).

**NEXT R1:** adversarial closed-offset golden profiles, independent
third-party SVG/DXF roundtrip QA, and real owner KDE Plasma Wayland
direct-manipulation acceptance before contemplating R2. R1 remains
IN PROGRESS. R2–R7 future/planned/safety gated. CNC/NC G-code
still intentionally disabled pending R6 preflight and machine QA.

| 2026-10-10/11 | PR #127 coincident true-circle sweep classification merged | [CI #38107164700](https://github.com/newnetmp3/CarveFoundry/actions/runs/38107164700): 145 tests, strict Clippy, Linux release; merge 28d01d35 | R1 goldens and independent KDE/SVG/DXF acceptance |


## Active R1l — independently authored SVG/DXF and closed-offset goldens

New branch feature/rust-r1l-cad-interchange-goldens starts from
verified main 0fae0ede45acc840d1f29349347900ed08fdaa9f,
including R1k PR #127's exact coincident-arc checks.

Rust integration tests in crates/core/tests/interchange_goldens.rs
reference two independently hand-authored 200 mm capsule fixtures
in SVG and ASCII DXF. They compare analytic world XY endpoints,
true arc centers/sweep directions, counts and closure across
native import/export and SVG -> DXF -> SVG conversion, not brittle
exact string equality. The same capsule is offset outward +3 mm
and inward -2 mm with exact 23/18 mm radii and source/result
global validation, then exported/imported as both formats.
A six-node reentrant L-shaped closed contour must round five
outer convex corners and one inner corner without flattening.
The original source stays unchanged. The test matrix also adds
a remote crossing open line-only vector: the legacy straight
offset solver now runs full-chain analytic validation on source
AND result, closing its earlier open self-intersection gap.

Documentation, fixture meaning, and explicit external viewer/KDE
manual acceptance: docs/INTERCHANGE_GOLDENS.md.

**Status: code/fixtures committed on branch; CI and merge pending.**
Independent viewer roundtrips and real Arch KDE/Wayland input QA
remain unverified. CNC NC export is still disabled pending R6
safety gates. Following work: adversarial multiple-loop/cubic
interchange semantics, desktop usability acceptance before R2.


## VERIFIED R1l — hand-authored SVG/DXF goldens and closed-contour validation

[PR #128](https://github.com/newnetmp3/CarveFoundry/pull/128) merged to main as **c34817881242f13ab55fa415c06fa4e22c4ac3ec**.
Exact feature head **79a32dde6121585c84de0553fefd56439f74191f**
passed [CI #38107633335](https://github.com/newnetmp3/CarveFoundry/actions/runs/38107633335): **127 core library + 5 CAD golden integration
+ 18 studio = 150 Rust tests**, strict Clippy and native Linux
desktop release. GitHub reported complete workflow success.

Two independently hand-authored 200×200 mm external-format source
fixtures (SVG A segments and ASCII DXF LWPOLYLINE with true bulges)
encode the same closed capsule. The new integration tests compare
physical world endpoints, original circle centers, arc winding,
node/segment counts, closed status, cross-format SVG and DXF
re-imports and independent fixture agreement. They also check
exact capsule +3/-2 mm offsets (23/18 mm true circular radii),
a six-node reentrant closed L profile with five outward convex
and one inward round join, and failed inward circle collapse.
The prior straight-only offset solver now runs full-chain analytic
source/output intersection checks, so remote self-crossing OPEN
straight profiles reject before editor commit rather than silently
creating invalid miter geometry. No preview points become sources.

Regression contract and explicit *unverified* external CAD viewer
and real Arch KDE Plasma Wayland manual acceptance checklist:
[INTERCHANGE_GOLDENS.md](INTERCHANGE_GOLDENS.md).

**NEXT R1:** real KDE/Wayland pointer UX acceptance, independent CAD
application interoperability, broader hole/compound/multi-loop
geometry and editable cubic offset policy. R1 remains unfinished.
R2–R7 are planned or safety gated. NC/G-code remains disabled;
CI here does not certify machine-safe cutter compensation.

| 2026-10-10/11 | PR #128 SVG/DXF independent-source golden and whole-chain straight offset safety merged | [CI #38107633335](https://github.com/newnetmp3/CarveFoundry/actions/runs/38107633335): 150 tests, strict Clippy, native Linux release; merge c3481788 | R1 owner KDE & external CAD viewer acceptance and complex compound contours |


## Active R1m — native compound contours and analytical hole hierarchy

Branch **feature/rust-r1m-compound-loop-analysis**, from verified
main c0b6f62a854d58fe8fb346afb613d67ed360a865 (PR #128
R1l golden interchange baseline). Rust adds:
- crates/core/src/compound.rs with analyze_compound_paths plus
  CompoundLoop, CompoundRole. It determines outline vs hole vs
  island via proven even/odd nesting depth and immediate parent
  ID; ordering and source winding do not change the hierarchy.
- intersections.rs boundary pair proof detects any crossing,
  tangency, isolated endpoint touch, collinear line overlap,
  unresolved same-circle coincidence and near-coincident
  supports across loops; the containment ray uses exact
  line equations and true circle arc sweeps, not preview samples.
- Only 1–32 source-true closed line/circular-arc loops and
  up to 150,000 exact inter-loop edge pairs. Non-simple loops,
  open vectors, cubic Bézier profiles, overlap/touch and
  unresolved containment fail without mutating CAD sources.
- Native Drawing topology inspector adds **Analyze selected
  closed contours** with per-vector role/depth/parent display.
  The results are read-only, invalidated after edits, and
  rechecked against selected source snapshots for drag/open
  and selection changes.
- Regression tests in crates/core/tests/compound_topology.rs:
  four-level alternating nesting, order/winding reversals,
  separate islands, concentric circle true arcs, mixed
  circle/rectangle, hand-authored SVG/DXF capsule with a hole,
  crossing/tangent/coincidence failures and no project mutation.

**Branch delivered, CI and merge NOT yet verified.** Full operation
and real Wayland pointer QA checklists in
[COMPOUND_CONTOURS.md](COMPOUND_CONTOURS.md). No durable compound
group metadata, native fill/Booleans or cutter-safe hole machining.
R1 remains in progress and G-code export stays disabled until R6.


## VERIFIED R1m — analytic compound closed boundaries, PR #129

[PR #129](https://github.com/newnetmp3/CarveFoundry/pull/129)
merged into main as **e57620c289eb06c60dd33c5d243ab1a1ff0aff3a**.
Exact tested source **16e3e20a904717c9be60f0a0bdbf3a526dd9656f**
passed [Rust CI #38108671980](https://github.com/newnetmp3/CarveFoundry/actions/runs/38108671980):
**127 core + 9 compound integration + 5 interchange golden
+ 18 studio = 159 Rust tests**, strict Clippy and native Linux
release compilation. The first branch CI passed tests but failed
two Clippy needless-range-loop diagnostics; final corrected source
head passed all full workflow gates.

Added pure Rust `compound::analyze_compound_paths` to classify
non-touching nested closed line/true-circle vectors. Exact source
boundary intersections and analytic ray casting derive deterministic
outer material, holes, islands and their immediate parent vector IDs
with parity-independent-of-winding depth. Selection order and
clockwise direction do not change roles. Bounded to 32 loops/150,000
cross-loop edge pairs; touching/crossing boundaries, unresolved
overlaps, open/cubic paths, uncertain containment reject.
Native Drawing/Edit Vector Topology has a read-only
**Analyze selected closed contours** button and visible per-vector
roles/depth/parent. Cached results clear after editor actions or
when selected original curve snapshots no longer match (including
direct node dragging). No mutation, grouping, source IDs or
`.cfd` file format change. No CNC pocketing, Boolean fill or NC.
See [COMPOUND_CONTOURS.md](COMPOUND_CONTOURS.md).

**NEXT R1:** independent owner Arch KDE Plasma Wayland pointer QA
and third-party CAD visual acceptance, then carefully scoped durable
compound/Boolean regions and curved/cubic offset policy. R1 remains
unfinished; R2–R7 future/safety-gated, CNC G-code export disabled.
CI release build is not real-desktop input or physical-machine QA.

| 2026-10-10/11 | PR #129 analytic hole/island hierarchy, native inspector and fail-closed crossing acceptance merged | [CI #38108671980](https://github.com/newnetmp3/CarveFoundry/actions/runs/38108671980): 159 tests/strict Clippy/Linux release; merge e57620c2 | R1 real KDE/Wayland UX and independent external CAD checks; durable compound Booleans |
