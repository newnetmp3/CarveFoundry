# CarveFoundry — full Rust roadmap and verified progress

**Verified snapshot:** 2026-10-10/11. Latest R1o [PR #131](https://github.com/newnetmp3/CarveFoundry/pull/131)
merged as 5c19b6e11123e04f8de941e577f4ad7312fa8adb.
Final tested head ff3906801ccc69c58541ac5110726f4556dbb81e
passed [CI #38111276249](https://github.com/newnetmp3/CarveFoundry/actions/runs/38111276249): **173 Rust tests**, strict Clippy,
Linux native release. R0 native Rust foundation implemented,
R1 2D CAD progressing, R2–R7 future or machine safety locked.
CI is not independent KDE Wayland or CNC owner acceptance.

**LATEST R1o VERIFIED:** [PR #131](https://github.com/newnetmp3/CarveFoundry/pull/131) merged
5c19b6e11123e04f8de941e577f4ad7312fa8adb;
exact tested head ff3906801ccc69c58541ac5110726f4556dbb81e
passed [CI #38111276249](https://github.com/newnetmp3/CarveFoundry/actions/runs/38111276249): **173 tests, strict Clippy,
native Linux release**. Exact Union/Intersection/A-minus-B
of disjoint/nested saved CAD regions retains original true
line/circle primitives. Intersecting/tangent contours still
require future analytic edge-splitting. Real KDE/Wayland and
independent third-party CAD application validation unfinished.

**PREVIOUS R1n VERIFIED:** [PR #130](https://github.com/newnetmp3/CarveFoundry/pull/130) merged
c3c32f3f05f60288bfc5dbb52995fa7cc9f79988;
exact tested head 2f4681207447f27d148ebcee13a5b46227041f03
passed [CI #38109518506](https://github.com/newnetmp3/CarveFoundry/actions/runs/38109518506): **165 tests, strict Clippy,
native Linux release**. Saved named compound CAD regions retain
original source IDs AND their proven parent hierarchy; every edit
revalidates nesting. Boolean material queries are analytic-only,
with no generated machining vectors. KDE/Wayland and independent
third-party CAD QA remain pending.

**PREVIOUS R1m VERIFIED:** [Compound closed-loop hierarchy PR #129](https://github.com/newnetmp3/CarveFoundry/pull/129)
merged e57620c289eb06c60dd33c5d243ab1a1ff0aff3a;
exact tested source 16e3e20a904717c9be60f0a0bdbf3a526dd9656f
passed [CI #38108671980](https://github.com/newnetmp3/CarveFoundry/actions/runs/38108671980):
**159 tests, strict Clippy, native Linux release**. Native inspector
classifies separately editable line/circle closed paths by exact
outer/hole/island depth with source-accurate crossing refusal.
Cubic contours, persistent compound regions, and real KDE/Wayland
and third-party CAD acceptance remain outstanding.

**PREVIOUS R1l VERIFIED:** [PR #128](https://github.com/newnetmp3/CarveFoundry/pull/128) merged c34817881242f13ab55fa415c06fa4e22c4ac3ec; exact tested head 79a32dde6121585c84de0553fefd56439f74191f passed [CI #38107633335](https://github.com/newnetmp3/CarveFoundry/actions/runs/38107633335): **150 Rust tests, strict Clippy, Linux release**. Two hand-authored SVG/DXF closed-capsule fixtures and cross-format true-circle geometry tests, plus bounded reentrant profile offsets and whole-chain straight-offset source/output validation. Manual real KDE/Wayland and independent third-party CAD application acceptance remain unfinished.

**PREVIOUS R1k VERIFIED:** [Same-circle angular sweep classification PR #127](https://github.com/newnetmp3/CarveFoundry/pull/127) merged 28d01d35b65a21eba9e2446f1f22d2a04f57a8c4; exact feature head 12b8b275c00ecc9351117ff727b5c0606f6593d1 passed [CI #38107164700](https://github.com/newnetmp3/CarveFoundry/actions/runs/38107164700): **145 tests, strict Clippy, native Linux release**. True adjoining source-circle segments no longer appear as overlaps; repeated angular sweeps fail closed. KDE/Wayland desktop and independent SVG/DXF golden QA remain unfinished.

![Full CarveFoundry R0–R7 roadmap — high-contrast static SVG](ROADMAP_HIGH_CONTRAST.svg)

[Open the full-size high-contrast SVG](ROADMAP_HIGH_CONTRAST.svg). This graphic has explicit foreground/background colors and requires **no Mermaid parser or theme initialization**. If an extension blocks images, the phase/status table below contains the same information.

## What these statuses mean

| Phase | Verified software so far | Outstanding acceptance |
|---|---|---|
| R0 | Rust CAD foundation, desktop and project/Undo tests | Comprehensive real KDE/Wayland user testing |
| **R1** | Baseline 2D CAD, SVG/DXF, text, groups/layers, exact splits/trims/intersections, straight/arc/Bézier extension and CI-verified mixed-offset integrity | **Verified:** convex round joins, concave circular trims and coincident arc sweep classification. Remaining: durable compound region/Booleans, cubic offset policy, KDE UX and third-party CAD viewer acceptance |
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


**R1m verified:** [PR #129](https://github.com/newnetmp3/CarveFoundry/pull/129)
CI-green merged, 159 tests. Read-only, source-exact nested
outline/hole/island roles are now visible in the native inspector.
R1 remains IN PROGRESS pending actual Wayland pointer interaction
and third-party CAD app QA. No compound machining region or NC.
[Read compound contour proof](COMPOUND_CONTOURS.md).


**R1n verified:** [PR #130](https://github.com/newnetmp3/CarveFoundry/pull/130) CI-green merged, **165 tests**.
Optional saved compound region membership stores immutable
parent links to prohibit silent Boolean reinterpretation.
Analytic source curves remain editable; safe inside/outside
parity queries are CAD-only. CNC NC export is still locked.
[Persisted compound CAD contract](PERSISTENT_COMPOUND_REGIONS.md).


**R1o verified:** [PR #131](https://github.com/newnetmp3/CarveFoundry/pull/131) CI-green merged, **173 tests**.
Source-exact Union/Intersection/A minus B of nested/disjoint
saved regions retains genuine line/arc contours, fresh IDs,
Undo and persistent hierarchy. Crossing/tangent/coincident
input geometry still refuses without fabrication.
[Exact Boolean proof and manual QA](EXACT_REGION_BOOLEANS.md).

**R1p active (pending CI):** exact strictly transverse line-line
Boolean splitting and closed-loop stitching for shifted overlapping
straight-edged saved regions. Non-crossing true arcs still retain
original circles. Endpoint/collinear contact and crossing arc/cubic
cases are refused. No CNC.
[Read design proof and manual QA](TRANSVERSE_BOOLEAN_SPLITS.md).
