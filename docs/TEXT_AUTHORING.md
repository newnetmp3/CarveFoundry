# Native Rust vector text — R1d

The Drawing workspace contains **Text** and **Text — system fonts…**
commands. Text uses fonts installed in the host Linux system (no fonts
shipped or downloaded by CarveFoundry).

## Creating and editing

1. Choose Text. Select a font family and typeface/variant independently.
2. Enter one line of text, em height in millimetres, additional character
   tracking in millimetres, X coordinate and baseline Y.
3. Create text. Every glyph contour is a native editable path, with
   straight segments and exact cubic curves (font quadratic segments are
   converted algebraically, not rasterized).
4. Select any resulting glyph outline -> Properties -> Edit text source…
   to adjust wording, font, size, tracking or placement. Regeneration
   happens atomically as a single Undo step.

The native .cfd saves both the original text description and its
generated outlines. A computer without the specified font can still
display, edit the individual outlines and export SVG/DXF, but cannot
regenerate from that font until installed. Font binaries are not embedded.

Text remains single-line; shaping/ligatures, bidi and variable-font axis
selection are not provided in this milestone. Missing glyphs, oversized
font files, unrepresentable outlines and disallowed font embedding fail
with an error and leave the design unchanged. Import of text from SVG/DXF
is still unsupported; exporting generated outlines through SVG/DXF works.

## Important geometry behavior

Individual contour paths can be node-edited, duplicated and exported.
Editing the original text source later replaces its old contours with
new ones, so hand-adjusted nodes do not survive reflow. Deleting a
contour detaches the text-source link while keeping the other outlines,
to prevent silent regeneration over an incomplete word.

## Desktop QA on Arch Linux/KDE/Wayland

- [ ] Open Text, confirm installed font families and independently
      selectable variants (Regular, Bold, Condensed and others if installed).
- [ ] Create “US NAVY” at 20 mm; select and node-drag a glyph curve.
- [ ] Edit wording/height/tracking in Properties, regenerate and Undo.
- [ ] Save .cfd, reopen, verify text-source metadata and exact outline paths.
- [ ] Export SVG/DXF and inspect strokes in an independent vector editor.
- [ ] Choose a font with an absent character; failure leaves design intact.
- [ ] Change to a computer without the original font; outlines remain.
- [ ] Verify stock/fixtures unchanged and NC/CNC output still disabled.

CI cannot validate every installed font or KDE portal interaction.

## Verified source/position contract (PR #114)

After creating text, selecting all its outline contours and moving them
together also updates the retained baseline coordinates. Regeneration
therefore retains the new position. Manual movement or node modification
of only one contour remains a direct outline edit: a subsequent text-source
update deliberately resets that shape to the font-defined contour.

Core/studio regression tests passed in CI #38008575719, including real
installed-font cubic extraction, but actual KDE desktop interaction,
font picker presentation and external SVG/DXF validation remain outstanding.
