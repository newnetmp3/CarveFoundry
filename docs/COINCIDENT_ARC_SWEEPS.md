# R1k — Coincident circular arc sweep classification

This work makes the CAD intersection checker distinguish **a complete
shared-circle overlap** from an ordinary **shared endpoint between successive
arcs**. It is purely analytic, not a rendered polyline or CNC clearance
claim.

## Geometry and admissibility contract

For two true circular arc segments whose centers are exactly equal:

1. Compare their true source radii. Distinct concentric radii have no
   intersection. Numerically near-equal, but not provably identical,
   supports are conservatively unresolved.
2. Convert each oriented circular sweep to its underlying CCW angular
   coverage in [0, 2π). The arc may be clockwise or counterclockwise:
   traversal direction changes endpoint parameters, not occupied geometry.
3. Split at 0°/360° if needed, forming at most two ordinary intervals.
   Any positive-length common angular interval is a **coincident overlap**
   and is rejected as indeterminate, even if the two paths run in opposite
   directions or wrap the angle seam.
4. When the angular ranges overlap in **zero length only**, verify their
   exact endpoint contacts. The low-level analytic pairwise solver
   retains an isolated shared endpoint with proper t=0/t=1 fractions;
   the on-demand UI scan still filters terminal-only source hits from
   its numbered marker list, avoiding marker clutter.
5. On a single editable chain, only adjacent edges may share their
   expected common node. A remote same-circle contact, multiple
   revolutions, overlapping sweeps or backtracking rejects. This is
   applied to both original and derived mixed offset contours.

The dedicated all-arc closed circular offset solver also runs the
whole-chain analytic validator on its source and output: a shared
center and clockwise flag alone are no longer sufficient to treat
several repeated turns as one simple circle.

The existing CAD drawing actions and offsets remain **source-faithful**.
Valid consecutive same-center arcs can now offset as multiple retained
true circular segments without being mistaken for overlapping geometry.
No flattening, source node-ID changes or native .cfd schema changes
occur. Existing convex round joins and finite concave trims retain
their support and error contracts.

## Intentional limitations

- Nearly but not provably identical centers/radii are conservatively
  marked indeterminate when geometry falls within the numerical
  coincidence threshold. This is preferable to a false safe geometry
  claim; robust near-coincident solver refinement is future work.
- Entirely overlapping concentric arc spans remain unsupported for
  editing intersections; they are **not** silently converted to an
  arbitrary single hit, merged, or deleted.
- Arbitrary cubic Bézier parallel curves, multi-loop polygon topology
  and physical machining clearance are not addressed.
- The renderer, independent SVG/DXF readers and mouse interaction on
  real KDE Plasma Wayland machines require separate acceptance.

## Regression matrix

- [x] CCW arc from 330° to 30°, followed by 30° to 100°: one
      endpoint hit even though the first arc crosses the angular seam
- [x] Reversed scan direction preserves correct endpoint fractions
- [x] Concentric arcs of radii 10 and 20 mm report no crossing and
      no unsupported pair in on-demand scanning
- [x] Opposite-winding arcs with a positive common angular span
      reject, including overlap across 0°/360°
- [x] Open path with genuine adjacent quarter-circle segments passes
      source validity and finite exact offset
- [x] Multi-revolution closed same-center circle rejects before
      standalone circular offset creation
- [x] Closed four-quarter true circle continues to offset inward/outward
- [x] Nonadjacent unexpected same-circle contacts still reject
- [ ] Manually draw and save a split circular profile using native UI,
      check source node IDs, undo, visible linework and zoom
- [ ] Independent SVG/DXF import/export in a third-party CAD editor
- [ ] Arch KDE Plasma Wayland tests at 100%, 125%, 150% scaling

**Verified automated checkpoint:** [PR #127](https://github.com/newnetmp3/CarveFoundry/pull/127)
merged as 28d01d35b65a21eba9e2446f1f22d2a04f57a8c4.
Exact tested source 12b8b275c00ecc9351117ff727b5c0606f6593d1
passed [CI #38107164700](https://github.com/newnetmp3/CarveFoundry/actions/runs/38107164700):
127 core + 18 studio = 145 Rust tests, strict Clippy and native
Linux release build. Real KDE Plasma Wayland and independent
third-party SVG/DXF manual acceptance have **not** been completed.
NC/G-code output remains disabled until the R6 machine safety gate.
