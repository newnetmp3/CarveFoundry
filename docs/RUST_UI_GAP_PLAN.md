# Rust UI replacement — delivery-driven migration program

The goal is to **retire the PySide6 interface**, not to duplicate one-off
controls in an unrelated layout preview. Retain the Python CF3D serializer,
CAM generation, machine-safety preflight and postprocessors behind strictly
typed, versioned desktop↔engine boundaries until independently proven Rust
equivalents exist. A Rust desktop with a Python CAM backend **counts as a full
Python UI replacement**, not as a complete Python-language elimination.

**Measured replacement coverage: not yet established.** Prior ~25–30% visual/
feature estimates were qualitative, not tests. The following phases have
binary acceptance gates; work toward the earliest missing end-to-end workflow.

## Migration delivery gates (priority order)

| Gate | Customer-visible workflow | Current state | Acceptance evidence |
|---|---|---|---|
| M0 | Open existing CF3D and see stock, all object identities, visible 2D vectors, 3D object inventory, fixtures and live CAM readiness in one Rust session | **In implementation** — `feature/rust-unified-cf3d-session` | One source deserialization/digest; safe background load; same-hash sections; no partial overwrite; no machine authorization |
| M1 | Edit and save a complete native project from Rust | **Missing** except source-guarded XY-only new-file placement | Versioned atomic project edit API, UUIDs, analytic vectors, transformations, layers, stock/fixtures, full undo/redo, stale CAM and project roundtrips |
| M2 | Author 2D vectors and manage parts in Rust, at Python CAD parity | **Partial** — native layout, arrays, nesting, object snapping | Direct node and curve editing, Pen/text, SVG/DXF import, groups/layers, constraints and all legacy project commands |
| M3 | Manipulate and inspect actual 3D geometry from Rust | **Missing** (inventory is not a renderer) | Interactive mesh viewport, camera/gizmos/layers, import and undo, suitable real-world GPU performance on KDE Wayland |
| M4 | Configure and generate all standard machining jobs from Rust UI | **Read-only CAM stage inspector and settings templates only** | Profile/pocket/engrave/V-Carving/3D/rest, cutter library, progress/cancel, op templates/arrays, project save/stale semantics; Python CAM can compute |
| M5 | Preview, preflight and export full jobs without opening PySide6 | **Missing in Rust UI** | Toolpath + stock-removal view, source/work-zero/safety conditions, cutter-aware clamps/fences, posted-motion preflight, per-tool programs with explicit Z re-probe; no bypass |
| M6 | Replace primary Linux launcher and retire Python GUI | **Not permitted yet** | CF3D golden corpus, Python/Rust workflow equivalence, crash recovery, accessibility, performance, physical KDE Plasma/Wayland and scrap-cut QA, rollback path |

**The dependency order is M0 → M1 → M2/M3 → M4 → M5 → M6.**
Move reusable numeric kernels to Rust alongside those gates when benchmarks
and roundtrip parity warrant it. Do **not** prioritize Rust percentages,
isolated UI cosmetics or unsafe direct CNC output over closing these gates.

### Immediate execution batch — unified CF3D project context (M0)

- Implement `carvefoundry.core.rust_project_session` using one trusted Python
  load and one consistent SHA-256. Return typed stock, loss-aware 2D preview,
  comprehensive item inventory, stock-relative fixture keep-outs and read-only
  CAM-stage report. Reject oversized or internally inconsistent responses.
- Open that session **on a worker** in `rust-ui`, update the whole document
  atomically after validation; show missing 3D objects/fixtures/CAM truth in
  a Job Setup panel, never fake editable 3D or preflight.
- Preserve existing SHA-guarded **new-file-only XY transaction** and
  conservative full CAM stale invalidation. No new CNC machine output.
- Add Python and Rust tests for digest mismatch, invalid fixture data, source
  change races, stable object identity and absence of motion/preflight claims.
  Native Rust build/Clippy and Python 3.12/3.14 CI are required; real KDE
  acceptance is a separate explicit gate.

### First follow-on batch — M1 typed mutations

Move from one-off Python subprocess commands to a **single versioned,
auditable transaction protocol**: allowlisted commands, source SHA check,
object UUIDs, immutable originals, atomic new file, direct validation in the
Python domain model and forced downstream CAM invalidation. Add transaction
preview, undo grouping and Rust-native conflict/reload UI. Start with stock
and object transformations only where validated; **never** silently flatten
analytic line/arc/Bézier geometry or ignore locked/hidden objects.

## Historic capability gap inventory (retained for reference)

The earlier feature-priority matrix is maintained below as a historical
feature inventory, but the delivery gates above control execution.

## Initial migration slice

`feature/rust-native-layout-studio` introduces a separate `rust-ui/` Cargo
binary using native egui. It supports shape creation, direct selection and
positioning, editable JSON layout, polygon-aware first-fit arranging, grid
arrays and SVG interchange. It is not a complete application replacement,
and its SVG export is not an NC toolpath.

PR #84 merged the first native Rust Studio interface and PR #85 merged a
**read-only** Python-to-Rust snapshot adapter for closed planar vector outlines
and stock dimensions. The subsequent integration adds the GUI **Import vectors
(read-only)** control and a second KDE desktop launcher. Snapshot import counts
unsupported objects and does not read or overwrite CAM operations or fixtures;
curves are approximated for 2D layout, not preserved as their editable CF3D
analytic sources.

PR #87 delivered
nonblocking bounded multi-sheet first-fit packing, optional right-angle
rotation lock, per-stock preview, nominal area reports, independent plan JSON
and separate SVG contours. It does not yet implement optimal nesting,
variable-size stocks, cutting tabs, clamps, grain direction metadata or CNC
toolpath planning. The original design is preserved transactionally.

PR #90 connected
source-fingerprinted snapshots and permanent object UUIDs to an explicit
**save as new project** action in the Rust Studio. Allowed changes are
only XY translations; changed vector outlines, object identity, names,
stock dimensions or rotation are rejected. The original remains immutable
and all new CF3D machine toolpaths must be regenerated in Python CAM.
This is not general writeback of 3D objects or full CAM editing parity.

PR #89 introduced the
first **bounded native CF3D write boundary** for checked XY movement only:
SHA-256 precondition, stable item UUID, locked object validation, exclusive
new output project, all prior NC motion removed and every CAM operation marked
stale. PR #90 integrated this protected XY-only write as a separate new-file action. It is not full CF3D parity.

The next engineering slice must establish a versioned, tested **read/write
CF3D editing/engine bridge** or equivalent backwards-compatible service with
stable source UUIDs, native Undo/Redo, toolpath invalidation and preserved
preflight, so a Rust UI can actually replace the full project editor. Until
then ship the Rust GUI alongside the trusted Linux CAM application.

## Current planned engine read boundary

PR #91 merged nonblocking **read-only CAM stage inspection** using a
typed SHA-256 guarded Python report and validated Rust schema; stored motion is
always *unverified*. PR #92 merged **versioned reusable CAM parameter templates** backed by
the trusted Python CF3D engine. Existing operations must have matching strategy,
cutter geometry and parameter types, and application writes only a NEW project
with every machining intent stale and all motion removed. CI passed both Python
lanes and native Rust build/Clippy tests. This does not merge toolpaths or
authorize G-code. Paired inlay geometry and complete Rust CAM editing remain
production gaps.

## Acceptance rules

- Must build as a native Linux binary and launch on KDE Plasma/Wayland.
- Must keep project save/reload, edit history, object source IDs and stock
  coordinates correct before any UI becomes the default.
- Must not bypass fixture/fence checks, tool-radius clearance, work offsets,
  per-cutter re-probe requirements or stale toolpath export blocking.
- Changes are delivered in PRs with green automated tests; physical device
  interaction and actual machining are reported separately.
