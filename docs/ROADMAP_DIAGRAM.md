# CarveFoundry — full Rust roadmap progress diagram

**Verified snapshot:** October 9–10, 2026. Native R1f numeric topology
[PR #116](https://github.com/newnetmp3/CarveFoundry/pull/116)
merged into `main` at `5e5747bd6d6f1abd10ffd9d9c5bf9f1233a52a05`.
Its exact head `2c378a3986ac96458f3a2377d1f344cc7923feed`
passed [CI #38011306582](https://github.com/newnetmp3/CarveFoundry/actions/runs/38011306582):
**78 core + 17 studio = 95 tests, strict Clippy, native Linux release**.

```mermaid
flowchart TD
    R0["R0 · Native Rust foundation<br/>DONE IN CODE · Partial desktop QA"]
    subgraph R1["R1 · PROFESSIONAL VECTOR CAD — IN PROGRESS"]
        direction TB
        R1A["DONE · Editable lines/arcs/cubics<br/>Snapping, node/handle drag, precise transforms"]
        R1B["DONE · SVG + DXF source interchange"]
        R1C["DONE · Installed-font vector text"]
        R1D["DONE · Named layers + vector groups · PR #115"]
        R1F["DONE · Exact topology slice · PR #116<br/>Split/trim, join, straight offsets, fillets/chamfers"]
        R1G["NEXT · Advanced topology and interaction<br/>Intersection trim, general curve offsets,<br/>closed/curve corners, practical CAD QA"]
        R1A --> R1B --> R1C --> R1D --> R1F --> R1G
    end
    Q["R1 acceptance gate · Actual KDE/Wayland behavior<br/>Design/SVG/DXF roundtrips, geometry verification"]
    R2["R2 · 3D geometry workspace<br/>PLANNED · Meshes, reliefs, native 3D viewport"]
    R3["R3 · CNC jobs + cutter/material library<br/>PLANNED · Operation definitions and invalidation"]
    R4["R4 · Native Rust 2D/2.5D CAM<br/>PLANNED · Profile, pocket, V-carving, engraving"]
    R5["R5 · Native Rust 3D CAM and simulation<br/>PLANNED · Rough/finish/rest, stock removal"]
    R6["R6 · CNC safety and machine export<br/>BLOCKED · Holder/fixture/post/NC checks"]
    R7["R7 · Production and physical QA<br/>PLANNED · Recovery, packages, Onefinity testing"]
    R0 --> R1A
    R1G --> Q --> R2 --> R3 --> R4 --> R5 --> R6 --> R7
```

### Scope and completeness

| Phase | Software status | Acceptance still required |
|---|---|---|
| **R0** | Rust workspace, project, 2D native UI and CI implemented | Full KDE Plasma/Wayland manual QA |
| **R1** | Core analytic CAD, editor UX, SVG/DXF, fonts, groups/layers and first exact topology tools delivered | Intersection-aware trim/extend, general curve offsets, remaining corner topology, KDE interaction and independent geometry review |
| **R2** | Not started on pure Rust reboot | 3D mesh/relief import, native camera, viewport, transforms |
| **R3** | Not started | Cutter/material sources, typed job operations, dependency invalidation |
| **R4** | Not started | Actual 2D/2.5D machining operations, cutting geometry |
| **R5** | Not started | Rough/finish/rest 3D CAM, stock simulation, deterministic validation |
| **R6** | **Intentionally locked** | Machine, workholding, cutter holder, Z-rapid, postprocessed NC preflight, tool-change probing |
| **R7** | Not started | Atomic recovery, distribution, independent NC verification, supervised physical scrap tests |

This diagram shows *verified feature delivery* rather than invented percentage
completion. Phase durations are unequal: green CAD tests are **not** evidence
of CAM performance, safe machine output or physical Onefinity readiness.

### Immediate next milestone

**R1g** — select a curve intersection visually and trim/explode only
representable source segments, implement robust general curved offsets
without sampling/raster approximations, closed-path corner operations,
and high-priority KDE/Wayland QA. Keep format and undo history stable.

For safe geometric limits and the currently available numeric tools,
see [TOPOLOGY_EDITING.md](TOPOLOGY_EDITING.md).
