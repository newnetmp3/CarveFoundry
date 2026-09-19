"""Guided Design → Setup → CAM → Preview → Preflight → Export workflow.

Every button delegates to the real existing command, and status is derived
from the live project, machine and toolpaths; this is not a checklist with
pretend completed operations. CNC preflight still runs independently at export.
"""
from __future__ import annotations

from math import isfinite

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class GuidedWorkflowMixin:
    """Nonmodal workshop guide; never disables viewport navigation."""

    def _guided_job_fingerprint(self) -> tuple:
        return (
            id(self.project),
            tuple(
                (id(path), len(path.moves), path.cutter)
                for path in self.project.toolpaths
            ),
            (
                self.project.stock.width_mm,
                self.project.stock.height_mm,
                self.project.stock.thickness_mm,
                self.project.stock.xy_zero,
            ),
            tuple(repr(fixture) for fixture in self.project.fixtures),
            repr(self._active_machine_profile()),
            repr(self._grbl_post_settings()),
        )

    def _guided_stage_status(self) -> tuple[tuple[str, str, bool, bool], ...]:
        stock = self.project.stock
        good_stock = (
            all(
                isfinite(value) and value > 0
                for value in (stock.width_mm, stock.height_mm, stock.thickness_mm)
            )
            and stock.xy_zero == "bottom_left"
        )
        machine = self._active_machine_profile()
        machine_ready = (
            machine.work_x_mm > 0 and machine.work_y_mm > 0
            and machine.work_z_mm > 0
        )
        visible = sum(
            item.visible and item.mesh is not None
            for item in self.project.items
        )
        has_paths = bool(self.project.toolpaths)
        verified = (
            has_paths and getattr(self, "_guided_preflight_pass", None)
            == self._guided_job_fingerprint()
        )
        return (
            (
                "1 · Stock and work zero",
                f"{stock.width_mm:g} × {stock.height_mm:g} × "
                f"{stock.thickness_mm:g} mm · XY0 {stock.xy_zero} · top Z0",
                good_stock, True,
            ),
            (
                "2 · Machine profile",
                f"{machine.name}: travel {machine.work_x_mm:g} × "
                f"{machine.work_y_mm:g} × {machine.work_z_mm:g} mm",
                machine_ready, True,
            ),
            (
                "3 · Register fences and clamps",
                f"{len(self.project.fixtures)} recorded keep-out(s); "
                "verify against your physical machine before every job",
                bool(self.project.fixtures), True,
            ),
            (
                "4 · Prepare design",
                f"{visible} visible mesh design(s); hidden templates excluded",
                visible > 0, True,
            ),
            (
                "5 · Generate cutter operations",
                f"{len(self.project.toolpaths)} generated operation(s)",
                has_paths, True,
            ),
            (
                "6 · Review full job and preview",
                "Review cutter order, cutout-last, estimated runtime, "
                "stock surface and remaining stock",
                has_paths, has_paths,
            ),
            (
                "7 · CNC preflight",
                (
                    "Passed for this exact machine/stock/fixtures/toolpaths"
                    if verified else
                    "Required: toolpaths and setup must pass before exporting"
                ),
                bool(verified), has_paths,
            ),
            (
                "8 · Export per-cutter programs",
                "Separate files on cutter changes; stop, change cutter and "
                "re-probe stock-top Z0; physically verify fences and clamps",
                bool(verified), bool(verified),
            ),
        )

    def _show_guided_workflow(self) -> None:
        existing = getattr(self, "_guided_workflow_dialog", None)
        if existing is not None:
            existing.show()
            existing.raise_()
            self._refresh_guided_workflow()
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("CarveFoundry — Guided CNC Workflow")
        dialog.setMinimumSize(650, 520)
        dialog.resize(750, 675)
        layout = QVBoxLayout(dialog)
        title = QLabel("FROM DESIGN TO SAFE G-CODE")
        title.setObjectName("DialogTitle")
        layout.addWidget(title)
        intro = QLabel(
            "Follow the steps below in order. Each button opens the actual "
            "CarveFoundry tool; completed checks reflect the CURRENT project. "
            "Orange steps need attention. CNC preflight is not optional, "
            "and a software pass cannot verify your physical clamps or Z probe."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        scroll = QScrollArea(dialog)
        scroll.setWidgetResizable(True)
        body = QWidget(scroll)
        sections = QVBoxLayout(body)
        sections.setSpacing(8)
        rows: list[tuple[QLabel, QLabel, QPushButton]] = []
        commands = (
            ("Edit Stock", self._focus_stock_section),
            ("Machine Profile", self._select_machine_profile),
            ("Clamps / Fences", self._fixture_editor),
            ("Design / Layers", self._show_layers_popup),
            ("Generate Toolpaths", self._calculate_toolpath),
            ("Review Job", self._show_job_planner),
            ("Run Preflight", self._preflight_toolpaths),
            ("Export G-code", self._export_gcode),
        )
        for label, callback in commands:
            row = QWidget(body)
            row_layout = QVBoxLayout(row)
            head = QHBoxLayout()
            title_label = QLabel()
            title_label.setObjectName("PanelHeader")
            head.addWidget(title_label, 1)
            button = QPushButton(label, row)
            button.clicked.connect(
                lambda _checked=False, fn=callback: fn()
            )
            head.addWidget(button)
            row_layout.addLayout(head)
            detail_label = QLabel()
            detail_label.setWordWrap(True)
            row_layout.addWidget(detail_label)
            sections.addWidget(row)
            rows.append((title_label, detail_label, button))
        sections.addStretch()
        scroll.setWidget(body)
        layout.addWidget(scroll, 1)

        note = QLabel(
            "For double-sided work, create separate front/back CF3D projects "
            "first. Complete this guide separately for EACH face, flip the "
            "wood against the fixed stops, verify fixture clearance and "
            "re-probe the newly exposed stock face. For multiple pieces, "
            "set up the Batch Production Grid before generating paths."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        close_button = QPushButton("Close Guide", dialog)
        close_button.clicked.connect(dialog.close)
        layout.addWidget(close_button)
        refresh_timer = QTimer(dialog)
        refresh_timer.setInterval(600)
        refresh_timer.timeout.connect(self._refresh_guided_workflow)
        dialog.destroyed.connect(
            lambda _object=None: self._guided_workflow_closed(dialog)
        )
        self._guided_workflow_dialog = dialog
        self._guided_workflow_rows = rows
        self._guided_workflow_timer = refresh_timer
        self._refresh_guided_workflow()
        refresh_timer.start()
        dialog.show()

    def _refresh_guided_workflow(self) -> None:
        rows = getattr(self, "_guided_workflow_rows", None)
        if rows is None:
            return
        busy = self._background_job is not None or (
            self._import_thread is not None and self._import_thread.isRunning()
        )
        for (title, detail, button), (name, description, ready, allowed) in zip(
            rows, self._guided_stage_status(), strict=True,
        ):
            title.setText(("✓  " if ready else "●  ") + name)
            title.setStyleSheet(
                "color: #62d26f;" if ready else "color: #efa856;"
            )
            detail.setText(description)
            button.setEnabled(allowed and not busy)

    def _guided_workflow_closed(self, dialog) -> None:
        if getattr(self, "_guided_workflow_dialog", None) is dialog:
            self._guided_workflow_dialog = None
            self._guided_workflow_rows = None
            self._guided_workflow_timer = None
