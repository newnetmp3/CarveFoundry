# CarveFoundry Rust SVG vector interchange — R1b

SVG is a drawing interchange format, **not** the CarveFoundry native project
format and **not** a CNC code format. Save `.cfd` to retain your design
stock, fixtures and history. The SVG export carries vector outlines only.

## Current supported interchange

- Open File -> Import SVG vectors… to merge editable SVG paths into the
  current project as a single Undo step. The stock dimensions are not replaced
  by the SVG viewBox; check the material size and location after importing.
- Open File -> Export vectors as SVG… to write all vector outlines to an SVG.
  Existing straight contour polygons also export as closed paths.
- Import supports M, L, H, V, cubic C, **true circular non-rotated A**
  and Z path commands. Relative and absolute forms are accepted.
- Nodes and true analytic curves remain editable. Source curves are never
  replaced with preview tessellation during import or export.
- SVG uses top-left Y-down coordinates, transformed into stock
  bottom-left XY0, in millimetres. Supported SVG viewBox begins at 0 0,
  uses the same mm dimensions as width/height, or root mm dimensions.
- Maximum 16 MiB input and 512 editable vectors, each at most
  256 analytic segments. Invalid input rejects the entire operation.

## Not yet supported (fail with explicit error)

Text, rectangles/circles not converted to paths, images, external uses,
nested transforms, nonzero viewBox offsets, non-unit drawing scales,
noncircular/rotated elliptical arcs, quadratic/smooth path commands, and
multiple subpaths inside a single path element. Flatten any transforms,
convert graphic shapes to SVG paths, and split multiple subpaths in the
source SVG editor before importing. SVG export does not include layers,
stock fixtures or machining information.

## KDE Plasma Wayland acceptance checklist

- [ ] Create a line, Bézier, circular arc and a closed polyline; export SVG
      using native portal file chooser.
- [ ] Import exported file into a fresh .cfd design. Confirm node counts,
      editable control handles, arc sweep and position in mm.
- [ ] Check exported vector names with quotes/ampersands remain unchanged.
- [ ] Import one SVG with valid and invalid paths: reject all of it, with
      no project mutation or added Undo entry.
- [ ] Ctrl+Z after a valid multi-vector import removes all imported
      vectors in one action while retaining any earlier edits.
- [ ] Cancel native pick/save dialogs: no mutation and no data loss.
- [ ] Verify visible dimensions at 100%, 125% and 150% KDE scale.
- [ ] Confirm SVG file contains no G-code and CAM/NC output remains disabled.

Manual checks are not implied by successful GitHub CI.
