"""Project lifecycle and standard CNC export commands for the base window.

The richer ProjectWindow subclass overrides history/confirmation behavior, while
this mixin provides the common fallback open/save/new workflow and verified
G-code export used by the application shell.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QMessageBox

from ..cam.job_process import GcodeRequest
from ..core.project import Project
from ..core.project_file import PROJECT_SUFFIX, load_project, save_project


class ProjectFileControllerMixin:
    """Own base project open/save/new state and normal G-code export."""

    def _set_project(
        self,
        project: Project,
        *,
        project_path: Path | None,
        selected_row: int = 0,
    ) -> None:
        self.viewport.set_node_edit_mode(False)
        self.project = project
        self.project_path = project_path
        self._toolpaths_stale_reason = None
        self._prepared_toolpath_geometry = None
        self._prepared_toolpath_stats = None
        self.project_title_label.setText(f"  •  {project.name} Project")
        self.viewport.set_project(project)
        self._measurement = None
        if hasattr(self, "tool_options_measure_label"):
            self.tool_options_measure_label.setText(
                "Drag two points on stock top (XY · Z0)"
            )
        self._refresh_project_list(selected_row)
        self._sync_toolpath_state_from_project()

    def _undo(self) -> None:
        self.statusBar().showMessage("Nothing to undo", 3000)

    def _new_project(self) -> None:
        self._set_project(Project(), project_path=None)
        self.statusBar().showMessage("New project created", 3000)

    def _open_project(self) -> None:
        if self._background_job is not None:
            self.statusBar().showMessage("Another operation is running", 4000)
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open CarveFoundry Project",
            str(self.project_path.parent if self.project_path else Path.home()),
            f"CarveFoundry Projects (*{PROJECT_SUFFIX});;All files (*)",
        )
        if not path:
            return
        project_path = Path(path)

        def load(progress):
            progress(0.05, "Reading project and embedded assets")
            project = load_project(project_path)
            progress(0.95, "Project loaded")
            return project

        def done(result):
            self._set_project(result, project_path=project_path)
            self.statusBar().showMessage(f"Opened {project_path.name}", 5000)

        self._start_background_job(
            "Open project", task=load, on_done=done,
            indeterminate=True,
        )

    def _save_project(self) -> None:
        if self.project_path is None:
            self._save_project_as()
            return
        self._save_project_to(self.project_path)

    def _save_project_as(self) -> None:
        suggested = (
            self.project_path
            if self.project_path is not None
            else Path.home() / f"{self.project.name}{PROJECT_SUFFIX}"
        )
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save CarveFoundry Project",
            str(suggested),
            f"CarveFoundry Projects (*{PROJECT_SUFFIX})",
        )
        if not path:
            return
        self._save_project_to(Path(path))

    def _save_project_to(self, path: Path) -> None:
        if self._background_job is not None:
            self.statusBar().showMessage("Another operation is running", 4000)
            return
        project = self.project
        if project.name == "Untitled":
            project.name = path.stem

        def save(progress):
            progress(0.05, "Compressing project and embedded assets")
            saved = save_project(project, path)
            progress(0.95, "Project written")
            return saved

        def done(saved_path):
            self.project_path = saved_path
            self.project_title_label.setText(f"  •  {project.name} Project")
            self.statusBar().showMessage(f"Saved {saved_path.name}", 5000)

        self._start_background_job(
            "Save project", task=save, on_done=done,
            indeterminate=True,
        )

    def _export_gcode(self) -> None:
        toolpaths = self.project.toolpaths
        if not toolpaths:
            self.statusBar().showMessage(
                "No calculated toolpaths to export", 5000
            )
            return
        base_directory = self.project_path.parent if self.project_path else Path.home()
        toolpath = toolpaths[0]
        project_name = (
            self.project.name if self.project.name != "Untitled"
            else toolpath.name
        )
        suggested = base_directory / f"{project_name}.nc"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export G-code", str(suggested),
            "G-code (*.nc *.gcode *.tap *.cnc);;All files (*)",
        )
        if not path:
            self.statusBar().showMessage("G-code export canceled", 3000)
            return
        request = GcodeRequest(
            toolpaths=list(toolpaths),
            path=path,
            settings=self._grbl_post_settings(),
            stock=self.project.stock,
            machine_profile=self._active_machine_profile(),
            fixtures=tuple(self.project.fixtures),
        )

        def done(result):
            output_files = [Path(name) for name in result["files"]]
            self._last_exported_programs = (
                self._guided_job_fingerprint(),
                tuple(str(file) for file in output_files),
            )
            self._set_activity_info(
                f"G-code exported\nFiles: {len(output_files)}\n"
                + "\n".join(str(file) for file in output_files)
                + f"\n\nOperations: {result['summary']}\n"
                + f"Moves: {result['moves']:,}\n"
                + f"Estimated cutting: {result['minutes']:.1f} min "
                "(rapids excluded)\n"
                + (
                    "One program per cutter stage. Stop, change and "
                    "re-probe the cutter before running the next file."
                    if len(output_files) > 1 else ""
                )
            )
            self.statusBar().showMessage(
                f"Exported {len(output_files)} G-code file(s)", 5000
            )

        def failed(message: str) -> None:
            self._set_activity_info(f"G-code export blocked/failed\n{message}")
            QMessageBox.warning(
                self, "G-code export blocked by preflight", message
            )
            self.statusBar().showMessage("G-code export blocked", 8000)

        self._start_background_job(
            "Export G-code", request=request, on_done=done,
            on_failed=failed,
        )

