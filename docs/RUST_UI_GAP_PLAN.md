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

The next engineering slice must establish a testable **read/write CF3D engine
bridge** or a backwards-compatible project editing service so that a Rust
interface can safely replace the project editor. Until then, ship the new
interface alongside the established Linux desktop app. Preserve all known
machine preflight and G-code release gates.

## Acceptance rules

- Must build as a native Linux binary and launch on KDE Plasma/Wayland.
- Must keep project save/reload, edit history, object source IDs and stock
  coordinates correct before any UI becomes the default.
- Must not bypass fixture/fence checks, tool-radius clearance, work offsets,
  per-cutter re-probe requirements or stale toolpath export blocking.
- Changes are delivered in PRs with green automated tests; physical device
  interaction and actual machining are reported separately.
