# CarveFoundry — contributor and AI-assistant working rules

CarveFoundry is a Linux/Wayland-first Python/PySide6 + Rust/PyO3 CNC CAD/CAM
desktop application. GitHub: `newnetmp3/CarveFoundry`.

## Delivery standard

- **Never create placeholder UI, inert buttons, fake progress, or partial
  "supported" features.** A proposed addition must include its actual UI (if
  user-facing), core implementation, persisted project data where appropriate,
  correct exports/machine behavior, regression tests, and user documentation.
- If a requested large addition cannot be completed in the current work,
  record it in `docs/ROADMAP.md` as **not implemented** rather than presenting
  it as ready. Distinguish work-in-progress branch changes from merged main.
- Keep the Qt event loop responsive. Run CPU-bound mesh/CAM/export jobs in the
  existing background-process framework and marshal results to the Qt thread.
- Do not merge failing CI. Run Ruff, pytest on supported Python versions,
  Rust formatting/Clippy/tests; inspect failures instead of bypassing tests.
- Confirm a finished GitHub edit through the actual resulting commit/PR, not
  by claiming local user files changed.

## CNC safety

- Work XY is stock bottom-left; Z0 is stock top. Center-zero is a post offset.
- A physical fence measured **from the machine bed** has top Z equal to
  `fence height - stock thickness`. User's typical left fence is 23 mm tall;
  board thickness varies.
- Preserve geometry when optimizing cutting time. Favor local low retracts,
  but NEVER allow a local retract to cross a fixture without sufficient
  fixture clearance. Do not assume work offset, holder geometry, or controller
  state can be checked offline.
- A GRBL program must never silently transition between cutters. Split
  manual tool changes into distinct programs; require a physical stop,
  tool swap, and tool-length re-probe between files.
- Toolpaths are machine motions: edits must be tested for ordering, first
  retract, fixture collision, edge clearance, and Z depth.

## Handoff default — REQUIRED

At the end of every substantial CarveFoundry implementation discussion,
include a **copy-ready compact handoff** for the next ChatGPT/Codex chat.
Include repo/branch/main commit and PR, CI/test status, what was actually
implemented and merged, any known bugs/unverified behavior, current
unfinished work, critical stock/fixture/Onefinity coordinate conventions,
and the user's requested next task. Never call unmerged work finished.
