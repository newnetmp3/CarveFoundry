# Beta2 desktop handoff

Repository: newnetmp3/CarveFoundry. Branch: Beta2.
Base main commit: 0a7a281b5b622fae9d5fda014cbb532dceadd7da.
This branch implements the user-approved Design/Machine desktop workspaces,
docked machining workflow and persistent Beginner/Advanced experiences.
Nothing in this handoff claims a merge to main. No PR was created by this work.

Implementation: ui/beta_workspace.py composes existing commands and project
state. Machine provides stock/machine/fixture setup, operation creation,
order review, preview, sampled simulation, preflight, setup sheet and export.
Advanced enables inline operation reorder/removal using existing validated
background rebuilding. Beginner provides guidance and a next-step action.
Changing experience sets the default CAM dialog mode; individual dialogs can
still use Simple/Advanced. Machine defaults existing jobs to append, with an
explicit replace option in the existing CAM dialog. Inspector focus commands
return to Design. Layout and experience preferences survive restart.

Local validation: 447 tests passed on each of Python 3.12 and 3.14 using editable
installs; five new Beta2 regressions included. Ruff, Rust formatting, Clippy,
and five Rust tests passed. Visible startup and OpenGL were exercised with
Xvfb/software GL at 1500x900 and 1050x650. GitHub CI status must be checked on
the pushed commit; local checks are not a claim of hosted CI success.

Limitations: generated operations remain session-only; reopening CF3D requires
regeneration. No native Wayland/GPU or physical CNC acceptance was performed.
The optional web prototype and AI models were outside this change. No known
unresolved Beta2 regression was found in the checks above.

Critical conventions: stock-bottom-left work XY0, stock-top Z0. A fence measured
from the bed has top Z = fence height minus stock thickness. Keep fixture
clearance checks and independent posted-G-code verification. GRBL cutter stages
remain separate files: physically stop, swap tools and re-probe Z between them.
Offline validation cannot check real work offsets, clamps or holder reach.

Next: inspect the published Beta2 commit and hosted CI, then user acceptance of
the two workspace layouts on a real desktop. Do not merge without passing CI
and user authorization. No additional feature request is pending.

Cloud commands: source /workspace/setup/activate-carvefoundry.sh, work in the
existing /workspace/CarveFoundry checkout. Use the saved Xvfb startup instructions
for visible OpenGL checks; Qt offscreen supports tests, not a visible viewport.
