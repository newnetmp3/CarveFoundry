# CarveFoundry — pure Rust reboot roadmap

**Direction:** entirely new Rust desktop, Rust-owned project schema, and
incrementally built Rust CAD/CAM. Do not port GUI functions one by one from the
old Python application. Reimplement useful workflows with tests and stable
interfaces, informed by the archived code, without depending on it at runtime.

## Milestone gates

| Phase | Deliverable | Acceptance | State |
|---|---|---|---|
| R0 | Pure Rust monorepo + working 2D canvas | Cargo workspace, geometry, stock/fixture model, versioned files, undo/redo, CI, native window | **Implemented on rust-reboot; CI pending** |
| R1 | Professional vector CAD | Retained line/arc/cubic paths, node/handle editing, snapping, Bézier preservation, real fonts/text, SVG/DXF, layers/grouping, trim/extend, fillet/chamfer | Planned |
| R2 | 3D geometry workspace | Real mesh load/store, multi-part layers, camera/gizmos, material relief, procedural image-to-depth input, robust Wayland viewport QA | Planned |
| R3 | Native job definition and tool library | Physical cutter profiles and materials, ordered typed CAM operations, UUID-linked sources, per-stage invalidation/dependency graph | Planned |
| R4 | Rust 2D/2.5D CAM | Profile, pocket, engraving, V-carving, inlay, contour/texturing, clearance vs cutter geometry, operation arrays, performance parity | Planned |
| R5 | Rust 3D CAM and preview | Roughing, finishing, rest, native stock removal visualization, collision/contact checks and deterministic benchmarks | Planned |
| R6 | CNC-critical safeguards and export | Fixture/holder-aware posted NC preflight, stock/tool/machine bounds, Z clearance, cutter-specific NC stages, re-probe prompts, fail-closed output | Planned |
| R7 | Production reliability + physical QA | Atomic recovery, packaged Linux build, source/project migration tool, golden projects, independent NC validation, KDE/Wayland and Onefinity scrap tests | Planned |

## Immediate next milestones

1. **R0 QA and usability:** pass Rust/Linux CI, improve exact vector selection,
   fixture editing/removal and save/load error feedback; measure native UI
   behavior on KDE Plasma/Wayland before declaring R0 fully accepted.
2. **R1 analytic vector data core:** persistent segment enum (line, circular
   arc, cubic Bézier), exact edge operations, stable node IDs and Undo, full
   schema roundtrip. Avoid sampling analytic curves as the canonical source.
3. **R1 editor UI:** Direct Selection mode and separate whole-object mode,
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

The archived Python application is evidence/reference only; it is not linked
or executed by the clean Rust workspace. A future CF3D-to-CFD migration
must use an explicit, tested one-way tool with clear omissions, not rename
files or infer compatibility.
