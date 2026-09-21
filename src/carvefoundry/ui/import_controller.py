"""File-import lifecycle and progress UI for the main workspace.

Imports use their own QThread worker because they stream one or more source
files into project items. Keeping this separate from generic background CAM
jobs makes both lifecycles easier to reason about and prevents unrelated status
UI from accumulating in the application shell.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread
from PySide6.QtWidgets import QFileDialog, QProgressBar, QStatusBar

from ..core.project import Project, ProjectItem
from ..core.units import ModelUnits
from .import_worker import ImportWorker


class ImportControllerMixin:
    """Own file-import worker state, UI progress, and imported-item commit."""

    def _init_import_controller(self) -> None:
        self._import_thread: QThread | None = None
        self._import_worker: ImportWorker | None = None
        self._import_target_project: Project | None = None

    def _install_import_status_widget(self, status: QStatusBar) -> None:
        """Install import progress ahead of the generic background-job widget."""

        self.import_progress = QProgressBar()
        self.import_progress.setObjectName("ImportProgress")
        self.import_progress.setFixedWidth(300)
        self.import_progress.setTextVisible(True)
        self.import_progress.setFormat("Import · %p%")
        self.import_progress.hide()
        status.insertPermanentWidget(0, self.import_progress)

    def _import_file(self, kind: str | None = None) -> None:
        if self._background_job is not None or (
            self._import_thread is not None and self._import_thread.isRunning()
        ):
            self.statusBar().showMessage("Another operation is running", 3000)
            return

        filters = {
            "SVG": "SVG files (*.svg)",
            "DXF": "DXF files (*.dxf)",
            "STL": "STL files (*.stl)",
            "Image": "Images (*.png *.jpg *.jpeg *.bmp *.webp)",
            "G-code": "G-code (*.nc *.gcode *.tap *.cnc)",
        }
        selected_filter = filters.get(
            kind,
            "Supported designs (*.stl *.svg *.dxf *.png *.jpg *.jpeg *.bmp *.webp "
            "*.nc *.gcode *.tap *.cnc);;All files (*)",
        )

        if kind is None:
            paths, _ = QFileDialog.getOpenFileNames(
                self,
                "Import Design Files",
                str(Path.home()),
                selected_filter,
            )
        else:
            path, _ = QFileDialog.getOpenFileName(
                self,
                f"Import {kind}",
                str(Path.home()),
                selected_filter,
            )
            paths = [path] if path else []

        if not paths:
            self.statusBar().showMessage("Import canceled", 3000)
            return

        self._start_import(paths, kind)

    def _start_import(self, paths: list[str], kind: str | None) -> None:
        thread = QThread(self)
        worker = ImportWorker(paths, kind)
        worker.moveToThread(thread)

        self._import_thread = thread
        self._import_worker = worker
        self._import_target_project = self.project

        thread.started.connect(worker.run)
        worker.progress.connect(self._import_progress_changed)
        worker.finished.connect(self._import_completed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(self._import_failed)
        worker.failed.connect(thread.quit)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(self._import_thread_finished)
        thread.finished.connect(thread.deleteLater)

        self.import_progress.setRange(0, 0)
        self.import_progress.show()
        self.statusBar().showMessage("Loading design…")
        thread.start()

    def _import_progress_changed(self, index: int, total: int, name: str) -> None:
        if index > total:
            self.import_progress.setRange(0, max(1, total))
            self.import_progress.setValue(max(1, total))
            self.import_progress.setFormat("Import ready · %p%")
            self.statusBar().showMessage("Finalizing imported items…")
        elif total <= 1:
            self.import_progress.setRange(0, 0)
            self.import_progress.setFormat(f"Loading {name}…")
            self.statusBar().showMessage(f"Loading {name}…")
        else:
            self.import_progress.setRange(0, total)
            self.import_progress.setValue(max(0, index - 1))
            self.import_progress.setFormat(f"{name} · %p%")
            self.statusBar().showMessage(
                f"Loading {name} ({index}/{total})…"
            )

    def _import_completed(self, infos: object, failures: object) -> None:
        if self.project is not self._import_target_project:
            self._set_activity_info(
                "Import finished, but the active project changed while it was loading.\n\n"
                "The loaded data was not added to the new project."
            )
            self.statusBar().showMessage("Import result discarded — project changed", 6000)
            return

        prepared_list = list(infos)
        failure_list = list(failures)
        if prepared_list:
            self._before_import_items_added(len(prepared_list))

        imported: list[ProjectItem] = []
        source_only_count = 0

        for prepared in prepared_list:
            info = prepared.info
            mesh = info.mesh
            if mesh is None:
                item = ProjectItem(info.path.name, info.path, info.kind)
                source_only_count += 1
            else:
                source_units = ModelUnits.from_metadata(mesh.units)
                transform = self.project.default_transform_for_mesh(mesh, source_units)
                item = ProjectItem(
                    info.path.name,
                    info.path,
                    info.kind,
                    mesh=mesh,
                    transform=transform,
                    source_units=source_units,
                )
                if prepared.gpu_vertex_bytes is not None:
                    self.viewport.prepare_mesh_upload(
                        mesh.mesh,
                        prepared.gpu_vertex_bytes,
                        prepared.gpu_vertex_count,
                    )
            self.project.items.append(item)
            imported.append(item)

        if imported:
            self._invalidate_toolpaths("Project geometry")
            self._refresh_project_list(len(self.project.items))
            if any(item.mesh is not None for item in imported):
                self.viewport.fit_view()
            self._on_import_items_added(len(imported))

        if failure_list:
            failure_text = "\n".join(failure_list[:8])
            if len(failure_list) > 8:
                failure_text += f"\n… and {len(failure_list) - 8} more"
            self._set_activity_info(
                f"Import completed with {len(failure_list)} failure(s)\n\n{failure_text}"
            )

        if imported and failure_list:
            self.statusBar().showMessage(
                f"Imported {len(imported)} file(s); {len(failure_list)} failed",
                8000,
            )
        elif imported:
            message = f"Imported {len(imported)} file(s)"
            if source_only_count:
                message += (
                    f" — {source_only_count} stored as project source asset(s) "
                    "pending dedicated editor support"
                )
            self.statusBar().showMessage(message, 6000)
        else:
            self.statusBar().showMessage(
                f"Import failed for {len(failure_list)} file(s)",
                8000,
            )

    def _before_import_items_added(self, count: int) -> None:
        del count

    def _on_import_items_added(self, count: int) -> None:
        del count

    def _import_failed(self, message: str) -> None:
        self._set_activity_info(f"Import failed\n{message}")
        self.statusBar().showMessage(f"Import failed: {message}", 8000)

    def _import_thread_finished(self) -> None:
        self.import_progress.hide()
        self._import_worker = None
        self._import_thread = None
        self._import_target_project = None

