# Rust-native UI replacement — functional capability gap plan

The future UI is a **Rust-first desktop workspace**. CNC-critical data and
machining behavior remain on the existing verified engine until equivalent
cross-language functionality has passed direct parity, project roundtrip,
preflight, and physical KDE Plasma/Wayland testing.

The order favors major production gaps rather than cosmetic button parity.
Do not use external product names in UI or feature identifiers.

| Priority | Area | Existing baseline | Rust-native delivery criterion |
|---|---|---|---|
| P0 | Sheet layout and nesting | Python rectangular batch grids; manual layer placement | Polygon-aware contour placement with real cuttable stock margins; expand from first-fit heuristic to rotation/grain, multiple sheets and waste reports |
| P0 | Authoring primitives and array tools | Existing PySide6 shape and vector editor | Rust-native editable vector objects, stock XY0, direct manipulation, array-copy, shared CF3D editing |
| P0 | Trusted engine boundary | Rust numerical PyO3 kernels and Python CAM | Versioned IPC/API with operation metadata, undo transactions, source UUID, signed stale-CAM state; no unverified G-code |
| P1 | Inlay workflow | Generic two-sided/engraving jobs | Paired cavity/plug setup, typed clearance, consistent mirroring and simulation |
| P1 | Toolpath templates | Persistent project operation settings | Saved, versioned reusable parameter/tool templates with safe cutter compatibility checks |
| P1 | Toolpath merging/arrays | Current per-cutter NC stages | Validated compatible-op merge/order and repeated source mapping, never cross-tool silent merge |
| P1 | Vector textures and editing | Curves, node editing, chamfer, fillet | Procedural texture fill, vector smoothing/distortion, accurate on-canvas trim and snapping |
| P2 | Production automation | Existing user workflows and CarveWork | Permission-scoped script/extension points and batch recipe execution |
| P2 | CNC view/simulation parity | Python simulated stock, posted NC preflight | Rust-side display and editing with the exact existing collision, stale-CAM, keep-out gates |

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

## Acceptance rules

- Must build as a native Linux binary and launch on KDE Plasma/Wayland.
- Must keep project save/reload, edit history, object source IDs and stock
  coordinates correct before any UI becomes the default.
- Must not bypass fixture/fence checks, tool-radius clearance, work offsets,
  per-cutter re-probe requirements or stale toolpath export blocking.
- Changes are delivered in PRs with green automated tests; physical device
  interaction and actual machining are reported separately.
