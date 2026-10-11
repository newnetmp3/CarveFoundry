# CarveFoundry — full Rust roadmap and verified progress

**Snapshot:** 2026-10-10. Latest verified code merge:
[R1i curved endpoint extension PR #121](https://github.com/newnetmp3/CarveFoundry/pull/121),
`7f58424451301b8b9be8fbe447b6ab61be0c69a1`.
Exact tested head `901460c7447aff05bb0a38c820693cf544b3daa9`
passed [Rust CI #38016223523](https://github.com/newnetmp3/CarveFoundry/actions/runs/38016223523):
**104 core + 18 studio = 122 tests**, strict Clippy and native Linux
release. Older numbered marker contrast PR #119 and straight extension
PR #120 are also merged.

![Full CarveFoundry R0–R7 roadmap — high-contrast static SVG](ROADMAP_HIGH_CONTRAST.svg)

[Open the full-size high-contrast SVG](ROADMAP_HIGH_CONTRAST.svg). This graphic has explicit foreground/background colors and requires **no Mermaid parser or theme initialization**. If an extension blocks images, the phase/status table below contains the same information.

## What these statuses mean

| Phase | Verified software so far | Outstanding acceptance |
|---|---|---|
| R0 | Rust CAD foundation, desktop and project/Undo tests | Comprehensive real KDE/Wayland user testing |
| **R1** | Most baseline 2D CAD, interop, text, groups/layers, exact split/trim/join, line/true-circle intersections and corners | Robust mixed/cubic offsets, advanced multi-curve corners, full KDE UX and independent SVG/DXF fixtures |
| R2 | Not implemented in pure Rust reboot | 3D mesh/relief workspace and viewport |
| R3 | Not implemented | CNC job, tool/material catalogs, dependency invalidation |
| R4 | Not implemented | 2D/2.5D machining and safe operation geometry |
| R5 | Not implemented | 3D machining and trustworthy stock simulation |
| R6 | Intentionally **blocked** | Holder/fixture/stock/machine-travel/postprocessed NC preflight and independent safety review |
| R7 | Not implemented | Packaging, recovery, migrations, goldens and real machine scrap testing |

**No invented overall percentage.** R0 and code-delivered portions of R1
have CI verification, not blanket real-desktop certification. R2–R7 differ
vastly in scope from R1 and are not equally weighted. Machine NC export
remains disabled until all independent R6 validation gates are ready.

See [INTERSECTION_EDITING.md](INTERSECTION_EDITING.md) for supported
line/arc/Bézier intersections, [CURVE_EXTENSION.md](CURVE_EXTENSION.md)
for exact Bézier/arc extension, and [TOPOLOGY_EDITING.md](TOPOLOGY_EDITING.md)
for other source-preserving numeric edits.
