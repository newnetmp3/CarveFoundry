# R1k — source-exact concave circular offset trims

## Opt-in operation and sign convention

In the native Drawing topology panel, select an editable vector and use
**Create rounded offset** (not the legacy tangent/miter **Create offset
vector**). The rounded action now has three local junction strategies:

1. G1-tangent line/circular edges meet exactly without altering their
   source type; a bounded line-line miter remains available.
2. Convex corners on the chosen offset side receive a **true** circular
   radius-|offset| join centered on the original vertex (PR #125).
3. **New R1k subset:** concave sharp line/true-circle and
   true-circle/true-circle corners can be trimmed to exactly one common
   support intersection, only if that point lies strictly within BOTH
   finite displaced edges, preserving the direction of traversal and
   nonzero portions of each original segment.

Open positive offsets are left of traversal, negative right.
Closed positive offsets are outward regardless of winding, based on
Green's theorem exact straight/circular area.

## How the trim is verified

- Construct exact shifted straight segments or circles, retaining all
  original segment identities, circle centers and clockwise flags.
- Solve the *supporting* line-circle quadratic or the two-circle
  intersection equations algebraically; no preview samples are used.
- For every candidate, compute its parameter on each displaced edge.
  A circle must lie on its actual bounded original arc sweep, not just
  anywhere on the full supporting circumference.
- Incoming parameter must be strictly between 0 and 1, outgoing
  likewise: no reverse motion, extension beyond either source edge or
  collapsed zero-length segment. Limit trimmed reach to 12 times the
  signed offset magnitude, consistent with existing bounded miters.
- If exactly one candidate is admissible, use one shared endpoint.
  Zero candidates (including short arcs), two viable candidates,
  coincident circles or unsupported overlaps **fail closed**.
- Validate the entire source and generated exact analytic chain for
  other self-crossings, tangencies, contact, and overlapping edges.
  Closed loops must retain winding. Reject without adding a vector
  or changing Undo/Redo history.
- Every ordinary circle center, exact radius and sweep direction is
  preserved. A separate convex round arc, when used, gets unique
  node and segment IDs. Existing native .cfd schema is unchanged.

The solver does **not** prove that every conceivable offset preserves
global CNC cutter clearance. It does not trim coincident supports,
solve general cubic Bézier parallel curves, merge loops, handle offsets
that collapse arc radii or prove external SVG/DXF interoperability.
No NC toolpath or CNC export is implemented.

## Acceptance on Arch KDE Plasma / Wayland

- [ ] Open line from (0,0) to (10,0), CCW arc from (10,0)
      to (20,-10), center (20,0). Rounded offset at +2 mm
      inserts the existing clockwise convex arc; at -2 mm
      trims the line and arc to one exact intersection around
      (8.167840,-2) and keeps circle radius 12.
- [ ] Reverse that arc-to-line profile; +2 mm trims to the
      corresponding intersection with circle center preserved.
- [ ] Join CCW quarter arcs at (0,-10) from circle centers
      (0,0) and (10,-10). Rounded offset at -2 mm
      trims exactly both radius-12 circles, no synthetic bridge.
- [ ] Shorten the second arc sweep before the would-be intersection.
      Operation must refuse, without creating a new vector.
- [ ] Verify Undo/Redo, layer/group locks, project save/reopen,
      native SVG/DXF export, 100%/125%/150% scaling and external
      independent CAD rendering. The legacy offset mode still
      rejects non-G1 curved corners.
- [ ] Test self-overlap, source zero-length, large offset radius
      collapse, many corner nodes and ambiguous support intersections.

**Automated verification:** [PR #126](https://github.com/newnetmp3/CarveFoundry/pull/126)
merged 907b1509133d09b55503d5ea75253a81abe13ee7;
exact tested source ded15b52f95cdededbd2492a63c1a18208553e44
passed [native CI #38106382405](https://github.com/newnetmp3/CarveFoundry/actions/runs/38106382405):
120 core + 18 studio = 138 tests, strict Clippy and native Linux release.
**Still pending:** independent external CAD roundtrips, real KDE
Wayland GUI acceptance, global complex-offset QA and all CNC gates.
R1 remains in progress; G-code stays disabled.
