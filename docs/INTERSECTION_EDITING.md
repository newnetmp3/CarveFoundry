# R1g — exact 2D intersections, closed corners and circular offsets

All design operations below work in native **Rust CAD**, never on displayed
sampled path points. This is not a cutter-path feature; **NC/G-code remains
disabled**.

## On-canvas intersection workflow

1. In **Drawing → Edit Vector Topology**, select one visible/unlocked
   *analytic source* vector. Keep any reference vectors visible.
2. Select **Find intersections**. This scans the source against other
   visible vector paths **on demand**, never every frame, and reports
   the number of unsupported source/reference edge pairs.
3. Select a numbered intersection from the combo box or enable
   **Pick marker on canvas** and click one of its colored markers.
4. **Split at crossing** inserts an editable node on the source edge at
   its exact fraction. **Trim end to crossing** shortens the source's
   selected Start/End segment, but only for an open path whose intersection
   lies on that terminal segment.
5. Both commands **recompute the crossing immediately before editing**.
   If either vector has moved, become hidden, or the crossing is invalid,
   the edit rejects without any project mutation or Undo entry.

Supported source/reference segment pairs include **line-line,
line–circular arc, arc–arc, cubic Bézier–line, cubic–true-circle arc,
and cubic–cubic**. Polynomial root isolation handles cubic/line and
cubic/circle tangencies; bounded convex-hull interval subdivision
and source-curve refinement handle cubic–cubic. This uses the original
analytic geometry, never the preview polygon. Tangencies and duplicate
edge hits are deduplicated. Only source interior fractions can be split,
while reference endpoints may be used.

Overlapping coincident curves and numerically unresolved configurations
remain explicitly unsupported; a nonzero count reports these exceptions,
not every Bézier pair. At most 128 visible crossings and 150,000
source/reference edge pairs may be examined per scan. Hide unrelated
vectors to narrow huge designs.

Intersections are source-accurate CAD geometry and preserve original
segment types. A scan is intentionally temporary UI data; it is never
serialized into .cfd and never a toolpath. Re-scan after editing.

## Closed-loop corners

The existing **Fillet selected node** / **Chamfer selected node**
commands now accept any line-line vertex of a CLOSED path as well as
interior corners of an open path. Both adjacent edges must be straight.
Fillets introduce a true circular arc with the requested radius;
chamfers introduce an exact straight edge. Over-sized and degenerate
corners are rejected. Arc-line, curve-line and arbitrary cubic corners
are **not** supported.

## Exact circular parallel offsets

**Create offset vector** continues supporting straight-only open/closed
vectors, and now also supports:

- One **true circular** open arc (positive moves to its left side).
- One **closed** concentric all-arc circle, with a shared center and
  winding (positive increases radius/outward).

The new radius and endpoints are computed analytically; the original
circular-arc segment definitions and center remain unchanged.
A negative offset that collapses or reverses radius is rejected.
The native **Circle** shape currently comprises cubic Bézier segments,
not true circular arcs; it is *not* accepted as a circular offset.
Use real circular arcs from DXF or the circular arc tool. General
elliptical/mixed/cubic offsets are future geometric-solver work, not
preview-polyline approximations.

## Desktop acceptance — Arch/KDE Plasma/Wayland

- [ ] Create crossing open lines; scan, choose marker by mouse; split and
      Undo. Repeat trim at crossing for Start/End segments.
- [ ] Move a reference after scanning; a stale edit must reject.
- [ ] Cross a true circular arc with a line. Check the visible chosen
      crossing, exact arc geometry after split, SVG/DXF export/reimport.
- [ ] Scan paths containing cubic segments; unsupported pairs must be
      reported and never presented as exact editable crossings.
- [ ] Fillet and chamfer a rectangle at every index including closing
      vertex 0; verify closed path remains valid and one-step Undo works.
- [ ] Offset a true open circular arc outward/inward and check radius.
- [ ] Offset a concentric full circle comprised of circular arcs.
- [ ] Lock or hide selected layer/group and confirm edits reject.
- [ ] Confirm the normal canvas pointer/Node drag behavior resumes after
      turning off Pick marker mode.
- [ ] Verify CNC toolpath and machine NC export are still inaccessible.

Desktop/independent SVG/DXF acceptance has NOT been established by CI.

## Verified code checkpoint — PR #117

[PR #117](https://github.com/newnetmp3/CarveFoundry/pull/117)
merged at `5663414c7f55db12dfe15734d51fa6790d7fd6dd`
after [Rust CI #38012411651](https://github.com/newnetmp3/CarveFoundry/actions/runs/38012411651)
passed **103 tests**, strict Clippy and Linux native release.
These are automated checks. The KDE Plasma/Wayland pointer and external
CAD file-interchange acceptance checklist above remains **unverified**.

The **Circle** shape constructed in the UI uses four cubic Bézier
segments, not actual circular arcs. Exact concentric circle offset
therefore requires a true circular-arc source, e.g. a DXF CIRCLE.
General cubic offsets are not yet enabled.

## Bézier crossings — R1g follow-up pending CI

Earlier R1g scans only supported line/true-circle edge pairs. A screenshot
of a five-edge polygon intersected by a blue cubic showed "2 exact
crossings; 5 unsupported edge pairs." The missing pairs were cubic.

This follow-up computes cubic-line and cubic-circle roots from their
source polynomials (including tangencies), and cubic-cubic crossings
using bounded control-hull subdivision with source-curve refinement.
No preview sample points are used as design intersections.
Coincident/overlapping or unresolved configurations remain explicitly
unsupported, rather than producing false markers.

The scanner retains source IDs, real curve fractions, the numbered
canvas markers and revalidation before any split/terminal trim.
Splitting keeps true cubic controls, never approximated polylines.

Desktop acceptance: reopen the original design, scan its orange five-edge
shape against the curved blue vector, verify previously missing crossing
markers, click one, split and Undo. Also check tangencies (one marker),
coincident cubic overlap (unsupported), stale moved references (reject),
and SVG/DXF roundtrip retaining true cubic segments.
CI cannot replace actual KDE/Wayland pointer testing.

## Verified Bézier repair — PR #118

[PR #118](https://github.com/newnetmp3/CarveFoundry/pull/118)
was merged to main at c3f1afc3 after
[CI #38013659809](https://github.com/newnetmp3/CarveFoundry/actions/runs/38013659809)
passed **111 Rust tests**, strict Clippy and Linux release.
This resolves the known unconditional skip of all cubic-containing
edge pairs. True coincidence or computationally unresolved overlap
is still explicitly unsupported; that count is not silently hidden.
The owner should retest the original five-edge/blue curve design on
KDE Plasma Wayland and report any remaining skipped crossings.
