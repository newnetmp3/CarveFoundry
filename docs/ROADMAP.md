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


## UI iteration — drag-to-draw shape tools

Active branch `feature/rust-drag-to-draw-cad`: replace arbitrary-offset
shape spawning with direct bounding-box drawing on the stock. Preview
without modifying the model; commit a single Undo operation on
mouse release. Shift constrains proportions, Circles stay square,
Escape and tiny drags do not change the project, and the numeric
size controls allow precise click-to-place positioning with an uncommitted ghost preview.
Bounded/finite geometry, off-grid origin and reverse-direction
gestures are checked in pure Rust tests. No NC output is enabled.
CI and manual KDE Wayland acceptance are separate gates.

Next prioritize interactive position/size feedback, multi-object
selection, actual vector snapping and vector editing ergonomics,
then SVG/text/layer tools. Do not substitute a decorative UI for
working CAD operations.

## Verified UI slice — direct geometry placement

[PR #107](https://github.com/newnetmp3/CarveFoundry/pull/107)
merged as `49f96f577b2b72fdfb6eee5ae7ab7ce64f878708`, with
[Rust CI run 37872863242](https://github.com/newnetmp3/CarveFoundry/actions/runs/37872863242)
green on exact feature head `d420fc10da94943b8d12d6629f01ebf8c5806649`:
**47 tests, strict Clippy, native Linux release build**.
Users can now draw CAD shapes by press-drag-release on stock, with
noncommittal live outlines and width/height, inverse-corner drawing,
Shift/Circle constraints, relative snapping and one undoable commit.
The numeric alternative places exact-size objects at the clicked stock
position with a ghost preview. CAD data is still Rust-native and no
cutting, CAM or machine-safety feature is enabled.

**Next:** confirm actual KDE Wayland pointer behavior; then deliver
multi-object selection, stronger 2D geometry snapping, text, SVG/DXF,
layers and conventional CAD transformation tools. CNC preflight remains
a separate future release gate.

## Verified R1 precision workflow — PR #108

Native multi-object selection and geometry snapping are the immediate
workflow priority: Shift/Ctrl-click additive selection, CAD enclosure/crossing
marquee, validated atomic group move/duplicate/delete, real vector vertex and
line-midpoint snapping, stock-corner snap, and UI indicators/toggles.
Selection is a transient editor property, **never a .cfd schema change**.
Do not silently apply single-vector mirror/rotate to only part of a group.
Acceptance requires a single Undo step for group editing, fail-closed locks,
no snapping against the actively edited source, and real Wayland pointer QA.
Design-only machine safety boundary unchanged.

Verified merge: `7ad69fef3125834898adb24cf68323f5f0ced3f6`.
Exact feature head `b091af41bac0a0a3d0f6c89737cc5b680b6d15b5` passed
[CI `37876938223`](https://github.com/newnetmp3/CarveFoundry/actions/runs/37876938223):
48 core + 7 studio tests, strict Clippy, native Linux release compilation.
Manual desktop acceptance remains separate; no CNC output is implemented.

## Native precision transforms (implemented in PR #109)

- Use **true geometry bounds** including exact cubic derivative extrema
  and actual circular-arc quadrant extrema, not raster/preview sampling.
- Align selected vectors by six edges/centers, evenly distribute >=3
  by center spacing, and align a whole selection envelope to stock XY0,
  center or far edges.
- Position selected vector(s) at typed *bounding-left X / bottom Y*,
  preserving their relative layout. Explicit Apply and Read buttons
  prevent per-keystroke Undo spam.
- Use arrow keys for configured positive/negative millimeter nudges,
  Shift+arrow ×10, and matching on-screen buttons. Maintain one Undo per
  accepted action and reject locked/hidden groups atomically.
- Keep precision controls visible and grouped with design tools; any
  UI issue on KDE Wayland is a prerequisite fix, not proof of usability
  from green automated tests.
- CNC machine preflight and G-code posting remain disabled.

Design usability follow-up: camera Fit Selection and accurate bounding-box
measurement overlay added alongside precision transforms; ribbon shortcut
buttons now consistently activate shape-placement mode. Neither camera
controls nor measurement overlays mutate native project geometry.

## Verified precision arrangement milestone — PR #109

[PR #109](https://github.com/newnetmp3/CarveFoundry/pull/109)
merged as `96a9e5ceeb529dc6927fd1ab1fc8f154415a26a0`,
with exact head `7b4a22c8877ee36d044c8be856b5723f29d65568`
passing [CI `37961368120`](https://github.com/newnetmp3/CarveFoundry/actions/runs/37961368120):
**53 core + 9 studio tests, strict Clippy and Linux release compilation**.
True retained-curve bounds, group alignment, even spacing, numeric XY
positioning, arrow-key nudges and camera fit are implemented and recorded
in the editable Rust design workflow. Desktop Wayland usability is still
unverified; the machining/NC release gates remain locked.

**Next course:** manual interaction QA, followed by SVG/DXF interoperability,
system-font typography and editable layer management in native Rust.


## Active R1 editor screenshot polish

KDE Wayland selected-path screenshots (2026-10-09) show incorrect fallback
font glyphs and cramped X/Y and shape tool arrangements. Before advancing
toward SVG/DXF, typography and layers, improve the existing *usable* tool
surface. Branch `feature/rust-editor-controls-ux`: egui-native drawn toolbar,
eye/lock and movement icons; two-column narrow tool palette; separate XY
rows; clear selection measurement labels; focused node inspector when a
node/handle is directly chosen; larger typography and responsive panels.
Pending Rust CI and **separate human KDE/Wayland UI tests**. No CAM or NC output.

## Verified UI selected-vector polish — PR #110

[PR #110](https://github.com/newnetmp3/CarveFoundry/pull/110)
merged to `main` at `55d6399b8f235f721048d1f1ec28ab9b60664feb`.
Final PR commit `533a57769baab87428d52a9da1819d6a41b61fcb`
passed [Rust native CI 37966080362](https://github.com/newnetmp3/CarveFoundry/actions/runs/37966080362):
53 core tests, 10 studio tests, strict Clippy, and Linux release compilation.
Font-independent icons, clearer creation tools, readable and stable precision
XY inputs/align controls, selected-node Properties access and font/side-panel
scale improvements are implemented and merged. **Manual KDE Wayland UI and
pointer QA is not yet verified.** No CAM, NC output or format migration was enabled.

**Next**: check actual desktop UI usability at multiple display scales;
then source-preserving SVG/DXF vectors, system fonts and editable grouping.


## R1 urgent node-drag regression — active 2026-10-09

The user's KDE/Wayland screencast shows nodes resetting toward their
original position instead of tracking the mouse. This is a source-level
input contract mismatch: `response.drag_delta()` means motion during the
**current frame**, whereas the validated drag preview always starts from
the original project snapshot. Branch `fix/rust-cumulative-node-drag`
switches all design drags to `response.total_drag_delta()` and adds
multi-frame regression coverage, unrestricted Alt-drag (ignoring feature
snaps), and explicit UI hints. Successful release CI and hands-on KDE
pointer capture QA are separate gates. Do not proceed to SVG/text features
until the existing node dragging workflow is usable. CNC remains disabled.


## Verified R1 native drag recovery — PR #111

[PR #111](https://github.com/newnetmp3/CarveFoundry/pull/111) merged
as `7ee5cba21afe0f805f1ea9289dfee2309b85ffc9`.
Final feature head `d7304a945afe06929dbc82448aa1e335c31a5fd9`
passed [CI 37968221186](https://github.com/newnetmp3/CarveFoundry/actions/runs/37968221186):
**53 core + 14 studio tests**, strict Clippy and native Linux release.
All pre-drag-baseline previews now consume absolute total pointer displacement,
not egui's incremental frame delta. This repairs node, Bezier handle, path,
contour, group and drag-to-size interactions at source level. Alt enables
temporary snap bypass while directly editing a node or handle. Multi-frame
and undo regressions are tested; actual KDE Wayland gestures remain a
separate, pending acceptance check. CNC output remains disabled.

**Next**: validate the owner screencast's direct-node interaction on the
updated desktop, then advance to source-preserving SVG/DXF and system-font
editing with regression fixtures.


## R1b native SVG authoring interoperability — active development

User confirmed PR #111 node dragging works. Begin retained source SVG
import/export on `feature/rust-r1-svg-vectors`:
- Source-preserving cubic, true circular arc and straight path edges.
- CAD millimetres bottom-left, SVG top-left, with explicit unit conversion.
- Reject unsupported transforms/text/ellipses rather than silently flatten.
- One undoable multi-path import; project-native .cfd unchanged.
- File menu native portal chooser, SVG vector output only.
- Roundtrip and hostile/unsupported input tests, CI gates, separate KDE
  desktop acceptance. Native DXF, font text, and layers follow in R1.
- No machine toolpaths, NC export or false cutting-ready claims.

## Verified SVG interchange — PR #112

[PR #112](https://github.com/newnetmp3/CarveFoundry/pull/112)
merged as `cca178b15c3104bc45f3de05336003bb073a0072`.
Exact head `043f21ee106734ea46c125c1f63a58df7cfa7aca`
passed [Rust CI 37970424316](https://github.com/newnetmp3/CarveFoundry/actions/runs/37970424316):
**57 core tests + 15 studio tests, strict Clippy, Linux release build**.

Native SVG path import/export now preserves editable straight, true circular
arc and cubic Bézier sources. It validates dimensions, coordinate conventions
and unsupported SVG structures strictly; imports are atomic, undoable and
cannot silently convert geometric curves into display tessellation.
Native file pickers expose SVG actions without changing `.cfd` schema.
Desktop KDE/Wayland dialog and scale behavior requires manual acceptance.

**Next course:** DXF exchange with the same source-preserving and
fail-closed contracts, followed by system-font text and vector outline
generation, grouping/layer organization and analytic trimming.
SVG output is vector art only; CAM/NC remains disabled.

## R1c — strict editable 2D DXF interchange (active)

PR #113 on feature/rust-r1-dxf-interchange implements pure Rust ASCII DXF
geometry support: LINE, LWPOLYLINE with signed circular arc bulges, ARC,
CIRCLE and clamped non-rational cubic SPLINE. Explicit source units, bounded
coordinates and fail-closed unsupported entities protect CAD geometry.
Native XDATA preserves editable path sequence on roundtrip. Imports are
atomic, one-step undoable, and cannot modify .cfd material/fixtures.
Native KDE File menu provides Import DXF and Export DXF drawing, not NC.
Regressions, strict CI and separate real desktop QA required before mark done.
Next: system-font text and editable layers/grouping.

## Verified native DXF vector interoperability — PR #113

[PR #113](https://github.com/newnetmp3/CarveFoundry/pull/113)
merged as 08bf16847a65e21b1f58323dd57992d23b490a90.
Its exact tested head 4f0dc1b581f46a26c536c5955ce8e8df5264548e
passed [CI 37972805832](https://github.com/newnetmp3/CarveFoundry/actions/runs/37972805832):
61 core + 16 studio tests, strict Clippy, native Linux release.

Native source-preserving DXF: 2D LINE, LWPOLYLINE with circular bulges,
ARC/CIRCLE, and clamped four-point cubic SPLINE. Explicit linear units,
bounded 2D validation, fail-closed unsupported entity handling.
On native-to-native roundtrips DXF XDATA preserves compound vector grouping
and properties. Import uses one Undo transaction, leaves stock/fixtures
unchanged, and cannot enable machine-export functionality. Native File
menu Import DXF/Export DXF now available. KDE portal/external CAD
interoperability still requires a real desktop test.

**Next:** system-font typography with adjustable editable text/vector
outline workflow, followed by first-class grouping and layers, precision
join/trim/offset, and further safe DXF entity support.

## R1d editable font typography — active branch

Native system-font text is implemented under feature/rust-system-font-text
pending strict CI. Use installed TrueType/OpenType fonts, family + variants,
one-line Unicode glyph outlines, height/tracking/baseline and explicit
source metadata in optional project text_runs (backward compatible .cfd).
Exact TTF quadratics become cubic Beziers; no text rasterization.
Atomic regenerate/Undo retains editability, and imported/exported vector
outlines work with existing SVG/DXF. Missing fonts on another computer
must not make saved outlines disappear. Font licensing restrictions are
respected. Later R1e: grouping, layers and outline trimming/joining.
CNC exporter remains disabled. Separate KDE manual QA pending.

## Verified R1d editable typography — PR #114

[PR #114](https://github.com/newnetmp3/CarveFoundry/pull/114)
merged to main as fe3cf4c4da05da64d9ea34467750d2ead71cb229.
Exact head 87d21253006bcea2e459139e98b78b3b96cd973b passed
[CI 38008575719](https://github.com/newnetmp3/CarveFoundry/actions/runs/38008575719):
**65 core + 17 studio tests, strict Clippy, native Linux release build**.

Installed system font family and style picker, retained source editable text,
metric height/spacing/baseline, exact quadratic-to-cubic source geometry,
portable saved vector outlines, one-step Undo regeneration, source baseline
movement during full-label group drag, and source metadata in backward
compatible .cfd are implemented. No font assets are bundled.
Manual KDE real-font usability and third-party SVG/DXF checks are still due.
Text shaping beyond single-line basic glyph advances remains future work.

**Next course:** R1e genuine vector groups/layers with clear object tree
and atomic visibility/locking/selection operations; improve text group UX,
then precise trim/join/offset, then safe native 2.5D/3D CAM milestones.
CNC/NC posting remains disabled until machine-safety validation.

## R1e — native vector layers/groups (active)

Branch feature/rust-r1e-layers-groups introduces backward-compatible
persistent flat groups and custom design layers, layer assignments,
visibility, locking and independent Undo actions. Object-mode selection,
marquee and drag treat a group as one unit; Node mode still edits geometry
directly. Hidden/locked design structures are excluded from hit tests/
snapping and guarded against editing; source Bézier curves, font outlines
and SVG/DXF interchange remain unchanged. Strict Rust CI, desktop scaling
and KDE/Wayland pointer QA required before marking verified. Machine NC
output remains closed. Next R1f: analytic trim/join/offset editing.

## Verified R1e layer/group CAD organization — PR #115

[PR #115](https://github.com/newnetmp3/CarveFoundry/pull/115)
merged as **1034c32628bcc12b0e2322f209d9b1ccf366db08**;
final exact head **7ec60f4c2124b65c901092549de8a4c87afd2ea8**
passed [Rust CI #38010068138](https://github.com/newnetmp3/CarveFoundry/actions/runs/38010068138):
**69 core + 17 studio tests, strict Clippy, native Linux release**.
Persistent named vector groups, editable design layers, Base layer,
visibility, locks, group selection and dragging, undoable membership
edits, compatibility with old .cfd, and text reflow associations are
merged. Automated tests validate project/Undo semantics; direct
KDE/Wayland UX and third-party interchange tests remain incomplete.

**R1 is still in progress**: source-accurate native join/trim/extend,
offsets and fillet/chamfer, plus desktop QA, follow next. The mesh
(R2), job/tool (R3), 2D CAM (R4), 3D CAM (R5), safety/postprocessor (R6)
and production/machine QA (R7) phases remain future work.

**Full visual phase diagram:**
[docs/ROADMAP_DIAGRAM.md](ROADMAP_DIAGRAM.md) — R0 through R7, explicit
finished R1 subfeatures, next tasks, and machine-output safety gate.

## Active R1f — exact line/arc/cubic topology

Branch feature/rust-r1f-exact-vector-topology adds a first numeric vector
topology suite: exact de Casteljau Bézier splitting, retained circular arc
splitting/trimming, open-end line extension, endpoint join with exact
orientation-reversal and optional true straight connecting edge, mitered
line-only offsets, and line-line corner chamfers/tangent circular fillets.
Drawing palette provides discoverable controls. Edits are one undoable
transaction and reject locked/hidden or unsupported geometry. General
curve offsets, arbitrary intersection trimming/extension and closed
contour corner fillets remain future work, not falsely declared complete.
Rust CI and physical KDE/Wayland interaction still need acceptance.
No CAM/NC output is enabled.

## Verified R1f exact-source vector topology — PR #116

[PR #116](https://github.com/newnetmp3/CarveFoundry/pull/116)
merged as **5e5747bd6d6f1abd10ffd9d9c5bf9f1233a52a05**.
Exact source head **2c378a3986ac96458f3a2377d1f344cc7923feed**
passed [CI #38011306582](https://github.com/newnetmp3/CarveFoundry/actions/runs/38011306582):
**78 core + 17 studio tests; strict Clippy; native Linux release**.

Source-preserving numeric tools include exact line/arc/cubic split,
open endpoint trim, straight end extend, orientation-aware open joins,
straight-only non-destructive parallel offsets, and open interior
line-line tangent circular fillets/chamfers. Edits are discoverable
in the Drawing palette and use validated atomic Undo. Unsupported
general curves and complex topology are refused instead of replacing
source geometry with preview tessellation.

**R1 remains in progress.** Next R1g: choose actual intersections
on-canvas, trim/extend against other geometry, robust curved offsets,
closed-path fillet/chamfer, test the whole CAD flow on KDE Wayland.
[Full updated roadmap diagram](ROADMAP_DIAGRAM.md) reflects completed
software slices and remaining R2–R7 phases, including locked CNC NC
posting/preflight under R6. Manual desktop and physical Onefinity
acceptance have not been established.


## R1g active — real intersections and closed/circular CAD topology

Branch `feature/rust-r1g-analytic-intersections` extends exact-source
CAD with selectable on-demand line/true-arc/circle intersections,
revalidated atomic intersection split and open-end trim, canvas markers
and dedicated marker-pick mode, closed line-line fillets/chamfers,
and non-destructive true circular/concentric-circle offsets. Unsupported
cubic intersections and general curve offsets are counted/rejected,
never approximated by on-screen preview tessellation. GUI and geometric
regression tests, strict Rust CI, Linux release and separate KDE/Wayland
acceptance remain release gates. CNC NC export stays disabled.

## Verified R1g exact analytic intersections — PR #117

[PR #117](https://github.com/newnetmp3/CarveFoundry/pull/117)
merged to main at `5663414c7f55db12dfe15734d51fa6790d7fd6dd`.
Exact feature head `c583cf3cd585d82eb729efbecaf5bc2367ba9f2a`
passed [CI 38012411651](https://github.com/newnetmp3/CarveFoundry/actions/runs/38012411651):
**86 core + 17 studio = 103 tests**, strict Clippy and native Linux
release build.

Delivered: precise line-line, line/true arc and arc-arc intersections,
numbered canvas markers and explicit marker-pick mode; edit actions
revalidate geometry and trim only terminal source segments as needed.
Closed straight-contour fillets/chamfers preserve exact circular geometry.
Single true open circular arcs and concentric all-arc closed circles
support exact new offset vectors. Cubic intersection solving, arbitrary
curve offsets and line/arc/cubic compound corner modifications remain
future source-accurate work; unsupported cases are explicitly rejected
rather than sampled. Full real KDE Wayland and SVG/DXF independent QA
is still outstanding. No machining/NC code is enabled.

**NEXT R1h**: bounded analytic cubic intersections and curve-specific
topology, more targeted extend/trim workflows, closed/mixed corners
where mathematically representable, improved on-canvas editing QA,
desktop golden fixtures and original file compatibility testing.

[Full R0–R7 updated roadmap diagram](ROADMAP_DIAGRAM.md)
now marks R1g implemented, R1h current next, R2–R7 planned/gated.

## Active R1g fix — complete ordinary Bézier intersection scanning

A KDE screenshot revealed five Bézier edge pairs skipped during Find
intersections. Add source-analytic cubic-line/circle polynomial roots,
source-checked bounded cubic-cubic intersections and tangency handling.
Retain same hit metadata, canvas markers, stale-hit validation and Undo.
Reject overlap/indeterminate curves; do not sample displayed polylines
as editable vector geometry. CI and owner KDE design retest pending.

## Verified Bézier intersection repair — PR #118

[PR #118](https://github.com/newnetmp3/CarveFoundry/pull/118)
merged as **c3f1afc3a7d794b534583b76078edba3bf1a3dee**.
Exact source head **dccd3d38b7a6022ac2f8cf315ceafb030e4b654c**
passed [Rust CI #38013659809](https://github.com/newnetmp3/CarveFoundry/actions/runs/38013659809):
**94 core + 17 studio = 111 tests, strict Clippy and native release**.

Screenshot-reported five skipped cubic edge pairs prompted bounded
source-geometry cubic–line (degree 3), cubic–true circle (degree 6)
and cubic–cubic intersections. Cubic-line/circle tangencies and
multiple crossings now have tests, plus original-source cubic–cubic
refinement, explicit overlap refusal and screenshot-style regression.
The native inspector supports corresponding marker selection/editing
without changing editable Bézier geometry. Owner's actual KDE design
acceptance remains outstanding.

R1h now prioritizes mathematically robust general curved offsets,
targeted extend-to-boundary, complex corners and desktop/interchange
QA. Full roadmap: [ROADMAP_DIAGRAM.md](ROADMAP_DIAGRAM.md).
CNC NC output remains disabled.

## R1h — Targeted extend-to-boundary and marker contrast (delivered)

Native intersection markers gain dark high-contrast badge backgrounds
and edge-safe placement (PR #119). Extend-to-Boundary uses a straight
terminal ray and current analytic line/circle/Bézier reference segments
to reach the nearest bounded intersection, as one Undo operation.
Native two-vector UI permits source selection, Start/End and max
extension distance. Unsupported collinear overlap/closed source/missing
reference and locked vectors reject without mutation. Distinct from
arbitrary tangent/cubic extrapolation, curved offset solving and CAM.
Strict CI, real KDE Wayland UX and external file QA are separate gates.

## Verified R1h — readable crossing labels and boundary extension

[PR #119](https://github.com/newnetmp3/CarveFoundry/pull/119)
merged as `398b5e75e262852685bb9c6ad973ee5c0009c580` and passed
[CI 38014413520](https://github.com/newnetmp3/CarveFoundry/actions/runs/38014413520):
**94 core + 18 studio tests, strict Clippy, native Linux release**.
Intersection marker numbering now has opaque dark rounded high-contrast
badges, cyan/amber rings and viewport-edge-aware label placement.

[PR #120](https://github.com/newnetmp3/CarveFoundry/pull/120)
merged as `51ab853abb19922f9e589fad0766613a4f5dc863` after final
[CI 38014783760](https://github.com/newnetmp3/CarveFoundry/actions/runs/38014783760):
**99 core + 18 studio tests, strict Clippy, native Linux release**.
New pure Rust Extend-to-Boundary targets the nearest exact forward
intersection of one OPEN straight terminal with a separate visible
line/true-circle/Bézier vector, within a bounded maximum reach. Native
two-vector UI selects source/target, Start/End and reach. Source lock,
reference visibility, collinear overlap, degenerate curves, and no
crossing are validated fail-closed; one Undo preserves source and
reference vector semantics. No G-code/NC.

**Next R1i:** exact robust curved offsets, complex junction fillets and
targeted curve editing, real KDE/Wayland GUI testing, project golden
files, and SVG/DXF interoperability QA. [R0–R7 roadmap diagram](ROADMAP_DIAGRAM.md)
reflects verified delivery but does not equate CAD CI with a finished
machine-control application.

## R1i — continuing cubic Bézier and true circular-arc endpoints (delivered)

React to user KDE screenshot where Extend to Reference was disabled
for an OPEN Bézier despite exactly two vectors selected. Extend native
Rust CAD terminal curve support to retain original polynomial Bézier
shape and true circular arc source types, with new analytic continuation
segments at the nearest actual boundary crossing. No preview sampling,
one atomic Undo, bounded polynomial extrapolation, and clear disabled
reasons for closed/hidden/locked sources. Strict Rust CI and KDE manual
acceptance required. R1 broader advanced offsets and corner solvers
remain future work; CNC/NC export still gated.

## Verified R1i — exact open cubic Bézier/circular source extension

[PR #121](https://github.com/newnetmp3/CarveFoundry/pull/121)
merged `7f58424451301b8b9be8fbe447b6ab61be0c69a1`; exact source
`901460c7447aff05bb0a38c820693cf544b3daa9` passed
[CI 38016223523](https://github.com/newnetmp3/CarveFoundry/actions/runs/38016223523):
**104 core + 18 studio = 122 tests**, strict Clippy and native Linux
release build.

Source-accurate Extend to Reference now works on OPEN line, true
circular arc and cubic Bézier source terminals. Béziers continue
the source polynomial beyond the original parameter range and
retain its geometric tangent/curvature; circular arcs preserve
original center/radius/winding. New nodes/segments are independent
CAD source entities and one undoable operation; existing curve nodes
and handles remain unmodified. Runtime is bounded by mm reach,
one-turn arcs and limited cubic extrapolation; unsupported crossings
reject instead of inventing a preview polyline. UI explains
closed/hidden/locked source restrictions, particularly relevant to
owner's screenshot with a closed pentagon + open Bézier.
See [CURVE_EXTENSION.md](CURVE_EXTENSION.md) and
[complete roadmap diagram](ROADMAP_DIAGRAM.md).

**Next R1 CAD:** robust general curved offsets, multi-curve junction
fillets/chamfers, full KDE real-pointer acceptance and third-party
SVG/DXF golden file roundtrips. R2–R7 are future phases; NC machine
output remains locked by the R6 safety gates.

## Readability of the roadmap diagram

The [full R0–R7 roadmap](ROADMAP_DIAGRAM.md) now embeds a
[high-contrast static SVG](ROADMAP_HIGH_CONTRAST.svg) instead of relying on
Mermaid theme initialization and client-side diagram parsing. The accompanying
Markdown status table is the text-only accessible fallback. This is a docs
fix only; project implementation status is unchanged.

## R1j implementation scope — source-exact tangent line/arc chains

Add exact parallel offsets for open/closed analytic paths mixing
true circular arcs and straight runs at G1-tangent curved joints.
Use Green's theorem analytic area for closed winding, signed offsets,
bounded straight miters and source circle-center/radius changes.
Reject sharp arc corners, invalid radii, general cubic Bézier
offsets and unsupported topology rather than storing a preview
polyline. One atomic Undo, original kept, layer membership retained.
See [TANGENT_OFFSETS.md](TANGENT_OFFSETS.md). Native Rust CI, KDE
Wayland UI and independent DXF/SVG acceptance remain gates;
machine NC output remains disabled.

## Verified R1j — source-accurate tangent mixed line/arc offsets

[PR #123](https://github.com/newnetmp3/CarveFoundry/pull/123)
merged `4f8ee59b5d3cabb45ae0ce5ebe24021336c18d5c`.
Exact head `0cb5f1e19e3cbc5a88e48f7eaacc1d530e156049`
passed [CI #38104323749](https://github.com/newnetmp3/CarveFoundry/actions/runs/38104323749):
**109 core + 18 studio = 127 tests**, strict Clippy, native
Linux release compilation.

Create Offset Vector now retains exact straight and circular
analytic edges on OPEN/CLOSED paths with tangent curved seams;
arcs can have multiple distinct circle centers, and line-line
corners can use bounded miters. Closed outward/inward sign derives
from exact Green's theorem straight/circular areas, not a preview
polygon. Existing direct straight/true-circle offset workflows
remain intact. Sharp arc corners, arbitrary cubic Bézier offsets,
collapsed radii and unsafe miters fail closed rather than being
silently tessellated. These geometry tests are NOT complete global
self-intersection or KDE/Wayland acceptance certification.

[Full high-contrast R0–R7 roadmap](ROADMAP_DIAGRAM.md) and
[exact mixed-offset design limits](TANGENT_OFFSETS.md) describe
the new state. Next **R1k**: mathematically verified junction
join styles and global offset validation, explicit tolerance model
for any future cubic approximation, usability and independent
CAD interchange tests. R2–R7 still planned/gated. NC/G-code
output remains locked behind R6 safety preflight and machine QA.


## Active R1k — analytic whole-chain validation for mixed offsets

The existing exact tangent mixed line/circular offset method is **not
globally topology-certified** by local tangency and winding alone.
Branch feature/rust-r1k-global-offset-validation adds a finite all-edge-pair
analytic intersection check before and after the new mixed offset.
It rejects remote self-intersections, unexpected contacts, collinear
overlap/backtracking and unresolved same-center circle supports, without
sampling visual preview geometry or changing the original. Existing
standalone true-circle and straight-vector offset solvers retain their
own independent checks. Strict Rust CI and KDE Wayland interaction
acceptance remain separate verification gates; do not mark as merged
until final successful CI and PR merge are recorded.

After this sub-milestone: sharp curve-to-curve joins, genuinely complete
topology certification (including coincident-arc sweep reasoning), explicit
accuracy contracts for any cubic parallel approximation, and independent
SVG/DXF goldens. **All machine NC/CNC export remains disabled.**


## VERIFIED R1k subset — analytic contour-integrity gate

[PR #124](https://github.com/newnetmp3/CarveFoundry/pull/124)
merged to main as **108a93a21bfca8a2a519e740d60991dc6a9f84ed**.
Exact source head **9560aa89ef74098f7e0151f4685a30e3b2d22e8f**
passed [CI #38105033834](https://github.com/newnetmp3/CarveFoundry/actions/runs/38105033834):
**113 core + 18 studio tests (131 total), strict Clippy and native
Linux release compilation**.

New mixed line/true-circle tangent offset validation detects source and
result self-crossings, remote touches, backtracking and parallel
line-overlap using retained analytic geometry, independently of pixel
preview and local G1 seam checks. Same-center arc support ambiguities
fail closed until proven; standalone concentric-circle offsets remain
independent. Source vector and project remain unchanged on rejection.
The high-contrast diagram and plain-text phase table are synchronized.
This closes the first R1k **subset**, not all of R1.

**NEXT:** mathematically safe sharp circular joins and coincident-arc
interval classification, fuller offset topology guarantees, real KDE
Wayland pointer testing and independent SVG/DXF golden interoperability.
R2–R7 remain future/gated; CNC/NC export is still disabled.


## Active R1k convex exact round joins (CI/merge pending)

The previous [PR #124](https://github.com/newnetmp3/CarveFoundry/pull/124)
global mixed-offset integrity gate is merged and verified. The new
feature/rust-r1k-rounded-convex-offset-joins branch adds an **explicit**
Create rounded offset native action, separate from existing miter mode.
At a convex sharp line/line, line/true-circle, or true-circle/true-circle
vertex the parallel edges are bridged by a genuine vertex-centered
circular arc of radius exactly the requested offset magnitude, with
the original primitive edges and their stable identities retained.
Open offset sign follows path left/right; closed positive is outward.
All-edge-pair analytic validation applies to source and finished offset.
Concave sharp circular joins, same-center ambiguous overlaps,
arbitrary cubic parallel offsets, excessive topology and unsafe
geometry are rejected. Legacy tangent/miter button unchanged.

Tests plus native Clippy/release CI and separate KDE/Wayland interaction
checks are acceptance gates; do not mark this branch merged until
CI and PR merge are independently verified. See TANGENT_OFFSETS.md.
R2–R7 remain future/locked, CNC G-code export disabled.


## VERIFIED R1k — source-accurate convex circular round offset joins

[PR #125](https://github.com/newnetmp3/CarveFoundry/pull/125)
merged as 3a2e107dd6d07f598788a3493e0e320eafccb5c2;
exact tested head ca543417bd2deefbbebf6401c1f06f8b9ef3d82e
passed [CI #38105790548](https://github.com/newnetmp3/CarveFoundry/actions/runs/38105790548):
**118 core + 18 studio = 136 tests**, strict Clippy,
native Linux release. A second opt-in rounded-offset tool
creates true vertex-centered radius-distance arcs at convex
sharp line/line, line/circular and circular/circular seams,
preserving original analytic segments, independent IDs,
transactional Undo and layer protection. The prior exact
tangent/miter offset mode is retained unchanged.
Global analytic source/result crossing validation applies.

**NEXT R1k:** safe exact concave circular trimming, coincident
arc interval classification and golden contour cases. Real KDE
Plasma Wayland interaction and third-party SVG/DXF still need
manual acceptance. R1 is not fully complete. R2–R7 remain
future/locked and CNC NC output remains disabled.


## Active R1k — bounded concave circular trim intersections

After the verified convex round-join PR #125, native Rounded offset
adds an exact **concave sharp corner** path: finite line/circle or
circle/circle parallel supports are intersected analytically.
Only a UNIQUE in-sweep hit that strictly trims both original edges
is accepted. Circle center, radius, segment identity and sweep
direction are retained. No extension outside original edge sweeps,
no invented round bridge, no preview tessellation. Ambiguous
same-center circles, two viable hits, short-arc misses, collapsing
radii or global self-crossings fail without mutation. Previous
convex joins, default tangent/miter mode, source/layer locks and
atomic Undo continue unchanged.

Branch feature/rust-r1k-concave-circular-trims is **under CI review,
not yet merged**. See docs/CONCAVE_OFFSET_TRIMS.md.
Next R1: coincident-circle sweep analysis, adversarial golden
contours, real KDE Plasma Wayland input and external SVG/DXF QA.
R2–R7 remain future/planned or safety-locked. No G-code export.


## VERIFIED R1k — bounded concave circular trimming, PR #126

[PR #126](https://github.com/newnetmp3/CarveFoundry/pull/126)
merged as **907b1509133d09b55503d5ea75253a81abe13ee7**.
Exact tested feature head **ded15b52f95cdededbd2492a63c1a18208553e44**
passed [CI #38106382405](https://github.com/newnetmp3/CarveFoundry/actions/runs/38106382405):
**120 core + 18 studio = 138 tests**, strict Clippy and
native Linux release build.

Opt-in Create rounded offset now combines retained tangent seams,
true convex round joins and unique concave line/circle/circle support
intersection trims, restricted to the *interiors of both displaced
finite original edge sweeps*. True arc source centers, segment IDs
and direction remain. Zero/ambiguous matches, unwanted edge extension,
coincident unsupported circles, radius collapse and global contour
crossings fail closed. The legacy tangent/miter offset mode is not
replaced. See [CONCAVE_OFFSET_TRIMS.md](CONCAVE_OFFSET_TRIMS.md).

**NEXT:** coincident-circle parameter interval proof, more closed
topology goldens, independent SVG/DXF interoperability and real
KDE Plasma Wayland user interaction acceptance. These software
tests are not physical CNC validation. R1 remains incomplete and
no machine NC/G-code export is enabled (R6 safety gate).


## Active R1k — coincident circular sweeps and repeated-turn safety

Branch feature/rust-r1k-coincident-arc-sweeps refines the exact Rust
source-arc intersection checker. Same-center arcs are classified
by occupied CCW angular intervals (split around 0°/360°), and only
isolated endpoint contacts may be allowed for neighboring segments.
Positive-length common sweeps and multi-revolution paths reject;
distinct concentric radii are nonintersecting, while numerically
near-coincident supports remain conservatively ambiguous. Apply
this to both general mixed analytic offset checks and the dedicated
all-arc circle offset solver. No tessellation or G-code.

Status: **implementation, tests and CI/merge not yet confirmed**.
Manual KDE Wayland and third-party SVG/DXF checks also outstanding.
Detailed examples: [COINCIDENT_ARC_SWEEPS.md](COINCIDENT_ARC_SWEEPS.md).
Next R1: complex closed contour golden fixtures, external CAD
interchange, owner UI/interaction validation. R2–R7 remain gated.


## VERIFIED R1k — source-accurate coincident arc sweep proof

[PR #127](https://github.com/newnetmp3/CarveFoundry/pull/127)
merged as **28d01d35b65a21eba9e2446f1f22d2a04f57a8c4**,
exact feature head **12b8b275c00ecc9351117ff727b5c0606f6593d1**
passed [CI #38107164700](https://github.com/newnetmp3/CarveFoundry/actions/runs/38107164700):
**127 core + 18 studio = 145 tests**, strict Clippy and
Linux release build.

The native Rust intersection checker now differentiates isolated
adjacent same-circle arc endpoint contact from **positive-length
angular overlap**, including reverse winding and 0°/360° seam
crossings. Remote contacts and multi-revolution circular offsets
remain invalid; distinct concentric radii correctly return no
crossing. Simple same-center split circular arcs may now be
offset without a spurious overlapping-support error. No
geometry-source sampling or project-format change. The dedicated
circular offset path now also validates source/output intervals.
See [COINCIDENT_ARC_SWEEPS.md](COINCIDENT_ARC_SWEEPS.md).

**NEXT:** independent SVG/DXF golden-file interoperability and
complex closed offset fixtures; real KDE Plasma Wayland desktop
acceptance remains required. R1 still unfinished, R2–R7
future/planned or safety-gated, CNC/NC G-code output disabled.


## Active R1l — external-source SVG/DXF CAD goldens and closed contour QA

Branch feature/rust-r1l-cad-interchange-goldens adds two
**hand-authored**, never self-exported input fixtures for a
closed exact circular capsule: 200 mm SVG and millimetre
ASCII DXF with bulge semicircles. Native Rust integration tests
compare true source coordinates/centers/directions and verify
native SVG and DXF import-export, cross-format re-import,
+3/-2 mm exact closed capsule offsets, and convex/reentrant
L-shaped rounded closed offsets. Full-chain source/result
analytic intersection validation now applies also to the
previous straight-only offset operation (open or closed):
remote self-crossings fail closed rather than being silently
mitered into unsafe geometry.

**Branch implementation only: CI/merge pending.** External CAD
application and real KDE Wayland GUI acceptance are still NOT
automatically certified. See [INTERCHANGE_GOLDENS.md](INTERCHANGE_GOLDENS.md).
R1 remains incomplete; R2–R7 future/safety gated, NC export disabled.


## VERIFIED R1l — source-format SVG/DXF goldens and full-chain straight offsets

[PR #128](https://github.com/newnetmp3/CarveFoundry/pull/128) merged as **c34817881242f13ab55fa415c06fa4e22c4ac3ec**;
exact tested head **79a32dde6121585c84de0553fefd56439f74191f**
passed [CI #38107633335](https://github.com/newnetmp3/CarveFoundry/actions/runs/38107633335): **127 core + 5 integration goldens + 18 studio =
150 tests**, strict Clippy and Linux native desktop release.

Two independent hand-authored capsule files (200 mm SVG and ASCII
DXF millimetres with exact circular bulges) must decode as the
same true-circle path; both native exporters and cross-format
roundtrips preserve endpoint geometry, circle centers/sweep
flags, segment counts and closure. The test matrix includes
exact +3/-2 mm rounded capsule offsets and reentrant L-profile
round offsets; radius collapse rejects. All-straight offsets
now use the same whole-chain source/output self-crossing gate
as mixed analytic offset paths. See
[INTERCHANGE_GOLDENS.md](INTERCHANGE_GOLDENS.md).

**Not sign-off:** the golden input files are hand-authored tests,
not completed third-party application execution. Real KDE
Wayland gestures/display scaling, compound/hole CAD semantics
and independent external SVG/DXF visual QA remain pending.
R1 in progress. R2–R7 future/safety-gated. CNC NC export disabled.


## Active R1m — source-accurate compound contour and hole nesting

Pure Rust branch feature/rust-r1m-compound-loop-analysis provides a
read-only CAD analysis of selected closed vectors, with true line/arc
boundary intersections and ray containment. It rejects self-crossing
or touching loop boundaries, cubic offsets/containment, open curves,
coincident overlays and topology that is not provably simple.
Nested independent circles/polygons are classified by even/odd depth
as material outline, hole, island, deeper hole, with the parent vector
ID. Native inspector displays results only while the same immutable
source snapshot is selected. Tests cover up to four nesting levels,
mixed arc/line contours, disjoint regions, SVG/DXF capsule inputs
and fail-closed contact. No source curves, group membership, project
schema or machining data are altered. No CNC toolpaths.

**Status: branch unmerged, CI/desktop QA pending.** See
[COMPOUND_CONTOURS.md](COMPOUND_CONTOURS.md). Following R1:
real KDE/Wayland pointer checks, durable compound grouping/region
Booleans only after topology proof, external CAD application QA;
R2–R7 remain future/safety gated.


## VERIFIED R1m — exact compound outer boundaries, holes and islands

[PR #129](https://github.com/newnetmp3/CarveFoundry/pull/129)
merged as **e57620c289eb06c60dd33c5d243ab1a1ff0aff3a**.
Exact tested head **16e3e20a904717c9be60f0a0bdbf3a526dd9656f**
passed [CI #38108671980](https://github.com/newnetmp3/CarveFoundry/actions/runs/38108671980):
**127 core + 9 compound goldens + 5 interchange tests + 18 studio
= 159 Rust tests**, strict Clippy, Linux native release.

Read-only native Drawing topology inspector offers **Analyze selected
closed contours**, identifying parent and even/odd nesting depth for
up to 32 independent closed line/circle paths. Pairwise analytic
boundary checks reject any crossing/touch/overlap; exact circular ray
tests determine which source paths are true holes and nested islands
without changing source curves, IDs, project organization or saved
schema. Result display invalidates whenever edited or selected
source snapshots change. Open/cubic and ambiguous geometry fail
closed; no machining operation or output is generated.
Details: [COMPOUND_CONTOURS.md](COMPOUND_CONTOURS.md).

**NEXT R1:** real KDE Plasma Wayland pointer acceptance, third-party
CAD visual checks, and design-only compound region persistence/
Boolean strategy where mathematically safe. Cubic offset and
toolpath/NC safety gates remain unfinished. R2–R7 future/planned.


## Active R1n — durable source-true compound CAD regions and Boolean membership

Pure Rust branch `feature/rust-r1n-persistent-compound-regions`
stores optional backward-compatible compound-region identity,
name and source membership (no primitive conversion). Current
source loops are revalidated on every atomic edit, drag-preview,
save and reopen. The native topology inspector can name/save and
unlink compound regions; selected members display persistent
roles and cursor material/void parity. The CAD Boolean evaluator
uses exact line/circular-arc containment; material = union of
disconnected outlines minus holes plus nested islands. Query points
on any true boundary refuse ambiguity. No Boolean generated edges,
cubic source approximation or machining toolpath is created.

**CI/merge pending:** golden tests include 4-level parity,
SVG/DXF capsule with a hole, undo/reload, atomic invalid move,
malformed references and boundary-safe refusal. See
[PERSISTENT_COMPOUND_REGIONS.md](PERSISTENT_COMPOUND_REGIONS.md).
R1 still in progress; external GUI/third-party CAD and R6 NC
safety checks outstanding.


**R1n nesting-safety refinement:** saved regions retain each
member's verified parent path ID and recheck it after edits.
A hole moved completely outside its host is no longer silently
interpreted as a new independent outline. Changing the Boolean
relationship requires unlinking/rebuilding the region. This is
part of the pending R1n CI branch, not a finished merge.


## VERIFIED R1n — persistent compound regions and exact CAD Boolean material test

[PR #130](https://github.com/newnetmp3/CarveFoundry/pull/130) merged as **c3c32f3f05f60288bfc5dbb52995fa7cc9f79988**;
exact tested feature head **2f4681207447f27d148ebcee13a5b46227041f03**
passed [CI #38109518506](https://github.com/newnetmp3/CarveFoundry/actions/runs/38109518506): **127 core + 9 compound + 5 interchange + 6
persistent golden + 18 studio = 165 tests**, strict Clippy
and native Linux release build.

Native `.cfd` schema-version-1 files now optionally retain
named source-analytic compound region membership. Each member's
proven parent at creation is retained so a hole moved entirely
outside its parent cannot silently become an independent material
island. Every edit/drag/save/reopen revalidates geometric boundaries
and nesting identity; failure is atomic. Native topology inspector
allows creating and unlinking saved regions, and tests exact
line/circular-arc even/odd material inclusion at cursor XY.
True boundary queries reject rather than guessing, with no
generated Boolean edges, CAM regions, cutter-safe offsets or NC.

Details: [PERSISTENT_COMPOUND_REGIONS.md](PERSISTENT_COMPOUND_REGIONS.md).
R1 remains IN PROGRESS pending real KDE Plasma Wayland pointer
acceptance, third-party SVG/DXF CAD app checks and broader precise
Boolean geometry. R2–R7 remain future/safety gated.


## Active R1o — proven non-crossing source-true Boolean geometry

Feature branch `feature/rust-r1o-exact-region-booleans`
implements exact Union/Intersection/A-minus-B over *two saved
compound CAD regions whose ALL source boundaries are distinct,
simple and non-intersecting*. Only complete original line/true
circular-arc source edges are copied: a Boolean truth-table
on either side of each analytic original contour determines
whether its entire loop is included. The output is independent
new editable native paths with fresh IDs and (when 2+ loops)
a saved parent-verified compound region. Native inspector adds
ordered operand selectors and explicit operation buttons;
atomic Undo/Redo and current R1n persistence still apply.

**Hard limits:** partial overlaps/crossing rectangles require
future source-exact edge splitting and cannot be fabricated by
retaining whole loops; tangent/overlap, unsupported cubics, empty
results, ambiguous geometry, >32 total source loops and
machine-dependent clearances reject. No CAM/G-code.
See [EXACT_REGION_BOOLEANS.md](EXACT_REGION_BOOLEANS.md).
**CI/PR merge pending**, real KDE/Wayland and external CAD app
acceptance remains outstanding; R1 is IN PROGRESS.


## VERIFIED R1o — source-exact Boolean CAD boundary operations

[PR #131](https://github.com/newnetmp3/CarveFoundry/pull/131) merged as **5c19b6e11123e04f8de941e577f4ad7312fa8adb**;
exact tested source **ff3906801ccc69c58541ac5110726f4556dbb81e**
passed [CI #38111276249](https://github.com/newnetmp3/CarveFoundry/actions/runs/38111276249): **127 core + 9 compound + 8
Boolean integration + 5 interchange + 6 persisted-region +
18 studio = 173 tests**, strict Clippy and native Linux release.

Native Drawing inspector now offers ordered saved-region operands
A and B and **Union / Intersection / A minus B**. For two CAD
regions whose complete source boundaries are analytically
proved mutually disjoint, the exact Boolean boundary loops
can be selected WITHOUT splitting or flattening original
line and circular-arc primitives. Fresh independent vectors
and persistent compound ownership (if multiple result loops)
are created as one undoable editor action; both operands
remain intact. Empty results, crossings, tangency, coincident
circles, cubic sources, ambiguity and huge selections refuse.

See [EXACT_REGION_BOOLEANS.md](EXACT_REGION_BOOLEANS.md).
R1 remains IN PROGRESS: ordinary partially overlapping rectangles
need future exact intersection splitting and stitching. Real
KDE Plasma Wayland gestures and third-party CAD application
inspection are still unverified. R6 NC output locked.
