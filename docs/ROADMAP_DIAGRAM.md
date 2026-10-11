# CarveFoundry — full Rust roadmap and verified progress

**Verified snapshot:** 2026-10-10. Latest Rust CAD feature:
[R1j exact tangent line/arc offsets PR #123](https://github.com/newnetmp3/CarveFoundry/pull/123),
merged as `4f8ee59b5d3cabb45ae0ce5ebe24021336c18d5c`.
Its exact final tested head `0cb5f1e19e3cbc5a88e48f7eaacc1d530e156049`
passed [Rust CI #38104323749](https://github.com/newnetmp3/CarveFoundry/actions/runs/38104323749):
**109 core + 18 studio = 127 tests**, strict Clippy and Linux release.
Earlier R1a–R1i CAD milestones remain merged, including arc/Bézier extension
PR #121 and high-contrast diagram PR #122.

![Full CarveFoundry R0–R7 roadmap — high-contrast static SVG](ROADMAP_HIGH_CONTRAST.svg)

[Open the full-size high-contrast SVG](ROADMAP_HIGH_CONTRAST.svg). This graphic has explicit foreground/background colors and requires **no Mermaid parser or theme initialization**. If an extension blocks images, the phase/status table below contains the same information.

## What these statuses mean

| Phase | Verified software so far | Outstanding acceptance |
|---|---|---|
| R0 | Rust CAD foundation, desktop and project/Undo tests | Comprehensive real KDE/Wayland user testing |
| **R1** | Baseline 2D CAD, SVG/DXF, text, groups/layers, exact splits/trims/intersections, straight/arc/Bézier source extension and tangent mixed line/circular-arc offsets | Sharp curved junction joins, general cubic offsets, global offset-intersection QA, full KDE UX and independent SVG/DXF fixtures |
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
for other source-preserving numeric edits. See [TANGENT_OFFSETS.md](TANGENT_OFFSETS.md) for the newly verified exact line/arc offset scope and explicit refusal cases.
