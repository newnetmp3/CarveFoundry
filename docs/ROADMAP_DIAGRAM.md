# CarveFoundry — full Rust roadmap and verified progress

**Verified snapshot:** 2026-10-10/11. Latest Rust CAD feature:
[R1k analytic mixed-offset integrity PR #124](https://github.com/newnetmp3/CarveFoundry/pull/124),
merged as `108a93a21bfca8a2a519e740d60991dc6a9f84ed`.
Its exact tested feature head `9560aa89ef74098f7e0151f4685a30e3b2d22e8f`
passed [Rust CI #38105033834](https://github.com/newnetmp3/CarveFoundry/actions/runs/38105033834):
**113 core + 18 studio = 131 tests**, strict Clippy and Linux release.
Previous R1j tangent mixed line/arc offsets PR #123 and R1a–R1i
remain merged; the high-contrast static roadmap is retained.

**LATEST R1l VERIFIED:** [PR #128](https://github.com/newnetmp3/CarveFoundry/pull/128) merged c34817881242f13ab55fa415c06fa4e22c4ac3ec; exact tested head 79a32dde6121585c84de0553fefd56439f74191f passed [CI #38107633335](https://github.com/newnetmp3/CarveFoundry/actions/runs/38107633335): **150 Rust tests, strict Clippy, Linux release**. Two hand-authored SVG/DXF closed-capsule fixtures and cross-format true-circle geometry tests, plus bounded reentrant profile offsets and whole-chain straight-offset source/output validation. Manual real KDE/Wayland and independent third-party CAD application acceptance remain unfinished.

**PREVIOUS R1k VERIFIED:** [Same-circle angular sweep classification PR #127](https://github.com/newnetmp3/CarveFoundry/pull/127) merged 28d01d35b65a21eba9e2446f1f22d2a04f57a8c4; exact feature head 12b8b275c00ecc9351117ff727b5c0606f6593d1 passed [CI #38107164700](https://github.com/newnetmp3/CarveFoundry/actions/runs/38107164700): **145 tests, strict Clippy, native Linux release**. True adjoining source-circle segments no longer appear as overlaps; repeated angular sweeps fail closed. KDE/Wayland desktop and independent SVG/DXF golden QA remain unfinished.

![Full CarveFoundry R0–R7 roadmap — high-contrast static SVG](ROADMAP_HIGH_CONTRAST.svg)

[Open the full-size high-contrast SVG](ROADMAP_HIGH_CONTRAST.svg). This graphic has explicit foreground/background colors and requires **no Mermaid parser or theme initialization**. If an extension blocks images, the phase/status table below contains the same information.

## What these statuses mean

| Phase | Verified software so far | Outstanding acceptance |
|---|---|---|
| R0 | Rust CAD foundation, desktop and project/Undo tests | Comprehensive real KDE/Wayland user testing |
| **R1** | Baseline 2D CAD, SVG/DXF, text, groups/layers, exact splits/trims/intersections, straight/arc/Bézier extension and CI-verified mixed-offset integrity | **Verified:** convex round joins, concave circular trims and coincident arc sweep classification. Remaining: compound/hole topology QA, cubic offset policy, KDE UX and third-party CAD viewer acceptance |
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
for other source-preserving numeric edits. See [TANGENT_OFFSETS.md](TANGENT_OFFSETS.md) for exact line/arc offsets and R1k whole-chain intersection validation, plus explicit refusal cases.


**R1k continuing:** PRs #125 and #126 have verified source-accurate
convex round joins and finite concave circular trims. Coincident arc
overlap proof, cubic parallels, complex closed contours, real KDE
desktop acceptance and external CAD goldens remain unfinished.
The high-contrast graphic keeps R1 in progress.


**R1k concave trim follow-on verified:** [PR #126](https://github.com/newnetmp3/CarveFoundry/pull/126),
exact 138-test CI green. Ambiguous coincident supports remain unsupported.
R1 still in progress, no CNC output. See
[CONCAVE_OFFSET_TRIMS.md](CONCAVE_OFFSET_TRIMS.md).


**R1k verified — angular sweep proof:** PR #127 passed exact CI and
merged. Valid adjacent arc endpoints are retained; overlapping sweeps,
remote contacts and repeated circles remain disallowed. The roadmap
keeps R1 in progress until real KDE/Wayland and independent SVG/DXF
acceptance. See [COINCIDENT_ARC_SWEEPS.md](COINCIDENT_ARC_SWEEPS.md).


**R1l verified:** PR #128 CI-green merged. Hand-authored SVG/DXF
source fixtures, exact analytic closed-contour offset goldens and
straight source/result crossing guards landed. Third-party CAD
application and KDE Plasma Wayland manual acceptance still pending.
[Read interchange goldens](INTERCHANGE_GOLDENS.md).


**R1m active (pending CI):** read-only, analytic outline/hole/island
hierarchy for separate non-touching closed line/true-circle loops.
Native Drawing inspector shows depth and parent; all original CAD
source identities remain. No compound machining region or NC output.
[See compound contour proof and manual acceptance](COMPOUND_CONTOURS.md).
