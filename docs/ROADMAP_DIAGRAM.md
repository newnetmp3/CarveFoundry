# CarveFoundry — full Rust roadmap progress diagram

**Snapshot:** 2026-10-09 (UTC); PR #115 merged to `main` as
`1034c32628bcc12b0e2322f209d9b1ccf366db08`.
[Rust CI #38010068138](https://github.com/newnetmp3/CarveFoundry/actions/runs/38010068138)
passed **69 core tests, 17 studio tests, strict Clippy and native Linux release**.

```mermaid
flowchart TD
    R0["R0 · Rust foundation and native 2D desktop<br/>DONE IN CODE · KDE full QA pending"]
    subgraph R1["R1 · Professional 2D vector CAD — IN PROGRESS"]
        direction TB
        R1A["DONE · Analytic lines, circular arcs, Béziers<br/>Node editing, shapes, snap, undo, precision"]
        R1B["DONE · Native SVG and DXF interchange"]
        R1C["DONE · Installed-font editable vector text"]
        R1D["DONE · Native layers and vector groups · PR #115"]
        R1E["NEXT · Join / trim / extend / offset<br/>Fillet, chamfer, topology and QA"]
        R1A --> R1B --> R1C --> R1D --> R1E
    end
    QA["R1 acceptance gate · Real KDE/Wayland tests<br/>File interoperability and geometry regression fixtures"]
    R2["R2 · 3D geometry workspace<br/>PLANNED · Mesh/relief/viewports"]
    R3["R3 · CNC jobs, tool and material libraries<br/>PLANNED · Operation identities/invalidation"]
    R4["R4 · 2D / 2.5D Rust CAM<br/>PLANNED · Profile/pocket/V-carving/engraving"]
    R5["R5 · 3D CAM and preview<br/>PLANNED · Rough/finish/rest/stock simulation"]
    R6["R6 · CNC safety and machine export<br/>BLOCKED · Fixture/holder/post/NC preflight"]
    R7["R7 · Production reliability and physical QA<br/>PLANNED · Packaging, migrations, Onefinity scraps"]
    R0 --> R1A
    R1E --> QA --> R2 --> R3 --> R4 --> R5 --> R6 --> R7
```

## Progress interpretation

**R0:** Rust monorepo and functional design desktop shipped and CI-verified;
some real KDE Plasma/Wayland acceptance still remains.

**R1:** Substantial CAD features shipped through [PR #115](https://github.com/newnetmp3/CarveFoundry/pull/115):
retained analytic paths and direct editing, drag correction confirmed by the
owner, precision snapping/transforms, SVG and DXF exchange, native vector
text, now first-class layers and groups. **R1 is not complete** until source-
accurate trim/join/extend/offset, corner operations and focused desktop QA.

**R2–R5:** Mesh and actual native CAM/stock simulation are upcoming;
no claim of toolpath parity or machine readiness is made.

**R6:** Independent *safety gate*: enforce stock/workholding/holder/tool
and machine-travel limits, tool-specific output with mandatory probing,
and validation of the *posted* NC before unlocking any G-code output.

**R7:** Production packaging, recovery, migrations, golden projects,
independent validation and actual machine scrap-cut acceptance.

This visual is intentionally **status-based, not a percentage guess**:
the eight phases differ greatly in scope and are not equally weighted.
Only R0 and the listed R1 slices have code and CI verification. Real desktop
and physical cutting are separate acceptance criteria.
