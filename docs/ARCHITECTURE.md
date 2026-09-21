# CarveFoundry architecture and module ownership

CarveFoundry is a PySide6 desktop application, a Python project/CAM layer and a
small Rust/PyO3 geometry acceleration library. The UI is Linux/Wayland first.

## UI composition

`ui/project_window.py` is the application window used at startup. It extends
`ui/main_window.py` with dirty-state management, Undo/Redo and guarded
New/Open/Close flows. Keep history ownership there.

`ui/main_window.py` is now intentionally the **composition shell**: it creates
the top-level workspace/widgets, connects major signals, installs shortcuts and
owns shutdown. Feature behavior belongs in narrower controllers/mixins.

| Module | Owner / purpose |
| --- | --- |
| `ui/background_job_controller.py` / `ui/background_jobs.py` | One shared long-running-job lifecycle, cancellation and the single generic status-bar progress indicator; worker/process primitives stay separate from widgets. |
| `ui/import_controller.py` / `ui/import_worker.py` | File selection, import thread/progress lifecycle and atomic prepared-item commit. Import progress is intentionally separate from generic CAM/background progress. |
| `ui/project_file_controller.py` | Base New/Open/Save/Save As/project replacement and normal verified G-code export. `project_window.py` may override history/confirmation behavior. |
| `ui/project_inspector_controller.py` | Layers/Object selector presentation, rename/visibility/lock state, stock controls and Inspector visibility. |
| `ui/selection_transform_controller.py` | Compatibility facade only. Selection lives in `selection_controller.py`; transforms/context/snapping/framing live in `transform_interaction_controller.py`; duplicate/delete/reorder live in `object_lifecycle_actions.py`. |
| `ui/toolpath_state_controller.py` | CAM ready/stale state, output-action enablement, viewport toolpath visibility and invalidation when design/CAM inputs change. |
| `ui/workspace_commands.py` | Compatibility facade only. `workspace_action_registry.py` owns canonical QActions, `workspace_menu_builder.py` owns desktop menus, and `workspace_surface_builder.py` owns the hidden ribbon host plus visible tool rail. |
| `ui/ribbon_actions.py` | Compatibility facade only. State, project-edit/arrange, view simulation, Smart Values and job utilities live in `ribbon_action_state.py`, `project_edit_actions.py`, `view_simulation_actions.py`, `smart_value_actions.py` and `job_utility_actions.py`. |
| `ui/ribbon_design_tools.py` | Paint-style drawing/tool-mode behavior and image trace entry points. |
| `ui/ribbon_cam_actions.py` / `ui/cam_generation_dialog.py` | CAM option state, operation submission, preview and the single CAM configuration/review dialog. The dialog is intentionally cohesive even though its layout is substantial. |
| `ui/ribbon_machine_actions.py` | Cutter library, machine profiles, GRBL/post settings and machine-control commands. |
| `ui/text_editor.py` | Compatibility facade only. Installed-font discovery/grouping lives in `text_font_catalog.py`, Inspector construction in `text_control_builder.py`, and live typography/mesh updates in `text_edit_behavior.py`. |
| `ui/native_viewport.py` / `ui/viewport_gpu.py` | Native QOpenGLWindow renderer, scene overlays and GPU/cache operations. |
| `ui/viewport_widget.py` / `ui/viewport.py` | Public QWidget shell around the native renderer, including rulers, projection/view controls and signal forwarding. |
| `ui/viewport_geometry.py` / `ui/viewport_interactions.py` | Geometry/picking math and user interaction behavior mixed into the native renderer. |
| `ui/inspector_controls.py` / `ui/layout_widgets.py` | Reusable stock/transform control construction and compact Inspector/CAM layout widgets. |
| `ui/two_sided_setup.py` / `core/two_sided.py` | Partition front/back models, bake physical reflection in XY, and save/reload-verify separate CF3D projects. |
| `ui/job_planner.py` / `cam/job_plan.py` | Session-owned generated motion sequence, cutter-stage grouping/reordering, validation and runtime estimates. |
| `ui/stock_simulation.py` / `cam/stock_simulation.py` | Off-thread sampled 2.5D remaining-stock simulation, cutter-profile sweep and result display. |
| `cam/gcode_verify.py` / `cam/virtual_machining.py` | Fail-closed independent NC decoding, posted-motion/fixture verification and verified-G-code-driven stock simulation. |
| `ui/project_recovery.py` / `core/recovery.py` | Atomic CF3D idle checkpoints, checksum verification and restore/cleanup. |
| `ui/batch_layout.py` / `core/batch_layout.py` | Independent editable copies in stock-registered grids with fixture/cutter margin checks. |
| `ui/direct_selection.py` / `core/vector_path.py` | Native Direct Selection and exact node editing for retained Pen/Line XY curves. |
| `ui/guided_workflow.py` | Modeless design-to-CAM workflow with derived live statuses and preflight fingerprint. |
| `ui/interface_settings.py` | Persistent layout/viewport preferences and migration. |
| `ui/planar_operations_actions.py` | Background orchestration and commit of planar Boolean/Offset results. |
| `ui/cam_dialog_help.py` | Pure contextual CAM help text catalog. |

All mixin methods operate on the **same MainWindow instance** and existing Qt
widgets. UI actions are created once in the action registry and reused by menus,
the hidden compatibility ribbon and the tool rail; do not create parallel state
for the same command.

Prefer responsibility boundaries over arbitrary file-size targets. A large file
is acceptable when it is one cohesive engine (for example the native OpenGL
renderer or CAM generation dialog). Split files when they accumulate unrelated
state/lifecycles or when independent tests/owners become difficult.

Architecture regressions in `tests/test_ui_modularity.py` and
`tests/test_ui_refactor.py` intentionally pin important facade/ownership
boundaries. Put new behavior in the narrowest relevant module instead of
growing `main_window.py`, a facade module, or a generic catch-all controller.

## Model, motion and file formats

- `core/project.py`, `core/history.py`, `core/project_file.py`: design
  state, snapshots and self-contained .cf3d assets. Mesh assets are shared in
  snapshots rather than deep-copied on every Undo.
- `core/planar_operations.py`: XY silhouette Booleans and signed offsets,
  returning Z0-topped, independently triangulated 2.5D shapes. Not 3D mesh
  Booleans.
- `cam/`: cutter-aware toolpath generation, GRBL post, fixture-aware preflight
  and process workers. Toolpaths use stock-bottom-left XY0 and stock-top Z0.
  `cam/rest_machining.py` probes the selected cutter against sampled remaining
  stock from `cam/stock_simulation.py`; it retains only useful contact-safe
  raster centres and lets the existing raster linker handle disjoint regions.
  `cam/job_process.py` simulates previous cutter stages once per Rest request.
  These algorithms are 2.5D approximations, not cutter holder or machine
  collision models; normal export preflight remains mandatory.
- `rust/`: tested native raster/contact kernels; Python reference
  implementations remain available for comparison.

CPU-heavy CAM and mesh work must not run in the GUI event loop; the existing
background thread/process pipeline presents progress and applies validated
results on the Qt thread. Do not move Qt widget mutations into a worker.
Actual export must preflight planner paths, independently decode/verify actual posted G-code including rapids and parking, and split cutter stages for GRBL. Reject unrecognized NC commands; don't silently simulate them.

## Checks before merging

```bash
ruff check src tests
pytest -q
cargo fmt --manifest-path rust/Cargo.toml --check
cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings
cargo test --manifest-path rust/Cargo.toml
```

The CI matrix runs Python 3.12 and 3.14. For UI tests, the
`tests/conftest.py` offscreen/software-OpenGL setup is required. Verify real
interaction, project save/reload and Undo/Redo when changing an interactive
tool, and geometry/motion/preflight tests when changing machinable results.
