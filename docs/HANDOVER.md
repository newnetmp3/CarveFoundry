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
