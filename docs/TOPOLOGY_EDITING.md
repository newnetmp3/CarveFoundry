# R1f — Exact 2D vector topology (first source-preserving slice)

This stage adds **design geometry editing only**. It does not generate cutter
paths, machining operations or NC/G-code. Curves remain true circles and cubic
Béziers in the native .cfd file, SVG and DXF interchange.

## Where to find the tools

Drawing workspace → left tool palette → **6 EDIT VECTOR TOPOLOGY**.

- **Split selected edge** — choose an edge from the dropdown and a fraction
  between 0 and 1. Exact line interpolation, circular-angle subdivision
  or de Casteljau cubic subdivision creates a new node. It keeps the original
  first-segment identity and is one undoable CAD edit.
- **Trim end** — choose Start or End of a selected open path, and fraction.
  Removes a fraction of its *terminal segment* analytically while preserving
  that segment's source type. This is not yet a click-to-intersection cutter.
- **Extend straight end** — extends only a terminal straight segment by
  millimetres along its existing axis. Curve extrapolation is not guessed.
- **Join selected** — select exactly two visible, editable *open analytic
  paths*. It automatically chooses the closest endpoints, reverses source
  direction as needed (including Bézier handle order/arc sweep), and retains
  exact curves. If endpoints touch, they share a node. If gap is nonzero
  but within chosen tolerance (max 5 mm), a **real straight bridge edge**
  is added without bending original curves. Result retains the first
  selected ID in deterministic ascending order; second vector is removed.
  Requires matching layer/group membership; text-linked glyphs are refused.
- **Create offset vector** — source-preserving parallel offset for
  straight-only open or closed contours, including miter intersection.
  Positive distance offsets an open path left of its direction, and a
  closed shape OUTWARD regardless of winding. Negative offsets the reverse
  side. Offset adds a new independent editable vector and carries layer,
  while leaving the original unchanged. Sharp, collapsing/self-intersecting
  results are rejected, never approximated from preview sampling.
- **Fillet selected node / Chamfer selected node** — in Nodes mode select
  an *interior* line-line corner of an open vector, choose radius or bevel
  length in mm. A fillet inserts a tangent **true circular arc** with exact
  radius/center. Chamfer inserts a straight connecting edge. Both preserve
  adjacent straight edges and refuse oversize/degenerate corners.

All actions pass through native Rust project validation and one Undo
transaction; invalid edits leave the design as-is. Geometry remains fully
editable as line, arc and cubic source segments.

## Intentionally unsupported

- Offsets of arbitrary cubic curves and general elliptical/variable-radius
  contours. They must use an independently validated native offset solver
  in a later R1f slice—not a polygonized preview approximation.
- Automatic intersection-aware trim, multi-curve extend and closed-loop
  fillets/chamfers. This initial numeric subset performs exact endpoint
  edits and interior line-line corners only.
- Geometry rewriting for text-linked outlines may invalidate editable
  source-text intent; treat node modifications as individual contour edits
  and regenerate from font if needed.

## KDE Plasma Wayland acceptance

- [ ] Create one circular arc and one Bézier. Split each at fraction 0.3;
      original sweep/shape must not change.
- [ ] Trim a cubic end and Undo. Source handles remain editable.
- [ ] Select two touching open paths and Join; Undo restores both.
- [ ] Join near endpoints with 0.2 mm tolerance; visible straight bridge
      must connect without distorting the source arcs.
- [ ] Offset a closed rectangle outward by 2 mm; original stays untouched.
- [ ] In Nodes mode, fillet and chamfer a 90° open polyline corner and Undo.
- [ ] Lock a layer/group; every topology edit must fail without mutations.
- [ ] Export/reimport SVG/DXF; verify arcs/cubics are still source curves.
- [ ] Confirm no CNC NC export or posted G-code becomes available.

**CI does not replace visual geometry or machine QA.** CNC output is
blocked pending the independent R6 machine-safety release gate.

## Verified automated checkpoint

[PR #116](https://github.com/newnetmp3/CarveFoundry/pull/116)
merged after [Rust CI #38011306582](https://github.com/newnetmp3/CarveFoundry/actions/runs/38011306582)
passed 95 Rust tests, strict Clippy and native Linux release build.
Physical KDE/Wayland editing and independent SVG/DXF curve QA are
still outstanding.

**Offset clarification:** closed line-only contours have explicit
self-intersection/degeneracy checks. Open path offsets are bounded and
validated as analytic lines, but overlapping distant segments in a
pathological open polyline are not yet exhaustively checked. Visually
review complex offsets until a robust general contour solver ships.
