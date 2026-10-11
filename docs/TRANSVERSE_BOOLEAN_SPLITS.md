# R1p — source-exact transverse straight-line Boolean splitting

This is the next native Rust CAD design milestone after the R1o
non-crossing source-true Boolean solver. **CNC / machine G-code is
still disabled.** The workflow is design CAD, not a milling toolpath.

## Native workflow

In **Drawing → Edit Vector Topology → Boolean CAD**, choose two
existing saved compound source regions and click **Union**,
**Intersection** or **A minus B**. The existing R1o solver still
preserves original complete true circular arcs when boundaries do
not cross or touch. The R1p fallback additionally supports **straight
source line loops with strictly transverse internal intersections**,
including many ordinary partially overlapping rectangular regions.

The output is a new set of independent editable native analytic
closed line paths. Fresh nodes are exact bounded line-line
intersection coordinates, not preview samples. New paths have
fresh stable identity; multi-loop output receives a separately
validated persistent compound-region parent hierarchy. Operand
paths/regions are not rewritten. This all occurs as **one Undo
step**; failed geometry creates nothing.

## Analytical safety constraints

The solver first verifies each saved operand region with existing
R1n/R1m original source-shape and parent-hierarchy checks.
Then it attempts the original non-crossing solver. Only if
global disjointness fails, and ALL combined source segments are
true straight lines, it attempts the bounded crossing solver.

The crossing solver:

1. Builds source-world segment endpoints and known inside-left
   material direction from each original loop's analytical signed
   area and its saved even/odd Outline/Hole role.
2. Finds strict segment/segment crossings from the 2D determinant
   equations. Both parameters must be *interior*, not an endpoint.
   It explicitly refuses collinear overlap, T-junctions, tangent
   endpoint contact, numerical near-intersections and degenerate
   splitting. At most **1,024 source edges and 256 true crossings**.
3. Splits each source edge analytically at sorted parameters,
   retaining exact straight subsegments and their real
   intersection nodes, with no rasterization.
4. For each fragment's provably off-other-boundary midpoint, uses
   existing exact analytic parity containment. A fragment is
   retained only when the Boolean result differs across the
   source edge's two sides. It is oriented with resultant material
   on its LEFT, for correct winding of holes and outer loops.
5. Builds a directed graph of the retained fragments. Every used
   vertex must have exactly one incoming and one outgoing edge.
   Non-unique branching, touching, overlapping or unclosed
   chains refuse explicitly.
6. Validates every reconstructed closed result with the native
   256-node per-path safety limit, then re-runs the full R1m
   intersection, nesting and hole classifier. Empty/ambiguous
   results fail closed. All source curves remain untouched.

An already supported R1o non-crossing line or true circular-arc
Boolean does **not** take the new fallback and retains original
analytic curves and complete original nodes exactly.

## Deliberate limitations

- No exact **partial circular-arc intersection splitting** yet.
  Any crossing true arc/cubic source declines the crossing fallback;
  it is NEVER tessellated into a fake straight contour.
- **Collinear overlapping straight lines** (e.g., two rectangles
  with identical top/bottom edges), endpoint touch, T-junctions,
  near-coincident supports, degenerate slivers and edge crossings
  too close to vertices refuse. The general coincident-edge
  Boolean graph is future R1 work.
- Up to 32 source loops, 1,024 line edges, 256 inter-operand
  crossing points, 2,048 generated line fragments, 256 nodes
  in each result path. Larger and numerically unclear inputs
  refuse without changing the design.
- This is not a general curve arrangement, cutter offset,
  pocket/infill, machine clearance proof, or NC export.
  No preview sampling is promoted into persistent geometry.

## Automated cases

`crates/core/tests/transverse_boolean_splits.rs` covers:

- Shifted partially overlapping rectangles with two strict
  crossings and material holes in both source regions.
- Union/Intersection/Difference in both winding directions.
- Ordered, asymmetric B-minus-A reconstruction.
- Output edge primitive purity, precise Boolean point-query
  classification, independently saved result parent links,
  file encode/decode and atomic one-step Undo/Redo.
- Collinear overlap, vertex touching, T-junctions and
  near-coincident slivers refusing without partial mutation.

R1o integration goldens for non-crossing exact circular arcs and
independently hand-authored external SVG/DXF source fixtures
continue to run unchanged.

## Real-machine owner QA still required

- [ ] On Arch KDE Plasma Wayland, create two rectangular compound
      regions shifted in BOTH X and Y so crossings are strictly
      internal; inspect Union, Intersection, A-minus-B.
- [ ] Verify saved geometry is editable in Nodes mode, including
      crossing intersection nodes, normal Undo/Redo, save/reopen.
- [ ] Check the same rectangle pair shifted only in X. The shared
      horizontal edges must refuse with a useful reason.
- [ ] Try exact corner touch, a tangent true arc, cubic sources
      and almost-touching edges: no arbitrary bridging or
      resulting half-open geometry.
- [ ] Import/export accepted result as SVG/DXF and check the
      lines, closure, winding and exact intersection coordinates
      independently in a separate CAD application.
- [ ] Test inspector and canvas controls at 100%, 125%, 150%
      desktop scale; CI is not real KDE/Wayland pointer QA.

**CI / PR merge:** recorded separately after exact head succeeds.
R1 unfinished. R2–R7 future/safety gated. R6 CNC NC export locked.


## Verified CI and merge

[PR #132](https://github.com/newnetmp3/CarveFoundry/pull/132) merged as **dcfa2f32b88d523de700551af02d8cad3353179f**.
Final exact PR head **8f6c92fad0dcd56907271404ad34d8ed4d4c966c**
passed [CI #38159106449](https://github.com/newnetmp3/CarveFoundry/actions/runs/38159106449): **178 Rust tests** (127
core, 9 compound, 8 earlier Boolean, 5 interchange, 6
persistent, 5 new transverse, 18 studio); strict Clippy
and native Linux release compilation. Existing old
crossing-refusal regression and single-loop output expectation
were updated to reflect the strictly supported new geometry.
Manual owner Arch KDE Plasma Wayland UI and independent CAD
application verification remain **unperformed**. Physical NC/
G-code remains disabled pending separate R6 safety signoff.
