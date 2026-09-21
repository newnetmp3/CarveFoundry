"""First-carving welcome, cutter guidance, quality review and setup-sheet UI.

All actions delegate to existing project/CAM/verification services. Neither
onboarding nor advisory UI bypasses independent posted-code export preflight.
"""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPdfWriter, QPixmap, QPolygonF, QTextDocument
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from carvefoundry.core.beginner import (
    MATERIAL_STARTERS,
    cutter_description,
    design_advisories,
    material_starting_values,
    starter_project,
)
from carvefoundry.core.job_sheet import job_sheet_html
from carvefoundry.core.tools import Cutter, ToolType


def _tool_picture(cutter: Cutter) -> QPixmap:
    """Draw a simple, non-photographic cross-section of the chosen bit."""
    image = QPixmap(190, 115)
    image.fill(QColor("#142033"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QColor("#a2d4b4"))
    painter.setBrush(QColor("#70ad92"))
    if cutter.tool_type in {ToolType.V_BIT, ToolType.ENGRAVING_CONE}:
        points = ((70, 12), (120, 12), (120, 38), (96, 98), (94, 98), (70, 38))
    elif cutter.tool_type in {ToolType.BALL_NOSE, ToolType.TAPERED_BALL_NOSE}:
        points = (
            (72, 12), (118, 12), (118, 70), (115, 81), (105, 93),
            (95, 98), (85, 93), (75, 81), (72, 70),
        )
    else:
        points = ((72, 12), (118, 12), (118, 98), (72, 98))
    painter.drawPolygon(QPolygonF([QPointF(x, y) for x, y in points]))
    painter.end()
    return image


class BeginnerWorkflowMixin:
    """Offer an approachable start without maintaining a second CAM state."""

    def _show_first_run_welcome(self) -> None:
        if self._settings.value("onboarding/seen_v1", False, type=bool):
            return
        if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            # Tests can call _show_welcome explicitly; do not flash a dialog
            # over every offscreen MainWindow smoke test.
            return
        if QApplication.activeModalWidget() is not None:
            QTimer.singleShot(1200, self._show_first_run_welcome)
            return
        self._settings.setValue("onboarding/seen_v1", True)
        self._settings.sync()
        self._show_welcome()

    def _show_welcome(self) -> None:
        old = getattr(self, "_beginner_welcome_dialog", None)
        if old is not None:
            old.show()
            old.raise_()
            return
        dialog = QDialog(self)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dialog.setObjectName("BeginnerWelcome")
        dialog.setWindowTitle("Welcome to CarveFoundry")
        dialog.resize(630, 510)
        layout = QVBoxLayout(dialog)
        heading = QLabel("MAKE YOUR FIRST CARVING")
        heading.setObjectName("DialogTitle")
        layout.addWidget(heading)
        intro = QLabel(
            "Start with a real editable project, import your own design, or "
            "learn what the machine and cutters do. Advanced tools are always "
            "available; you do not need them for your first nameplate."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        def action(text: str, callback, description: str) -> None:
            button = QPushButton(text, dialog)
            button.clicked.connect(
                lambda _checked=False: (dialog.close(), callback())
            )
            layout.addWidget(button)
            detail = QLabel(description, dialog)
            detail.setWordWrap(True)
            detail.setObjectName("Muted")
            layout.addWidget(detail)

        action(
            "Create my first nameplate",
            lambda: self._create_starter_project("nameplate"),
            "A 203.2 × 101.6 × 19.05 mm board with editable lettering.",
        )
        action(
            "Try a coaster template",
            lambda: self._create_starter_project("coaster"),
            "A simple 80 mm circular design, centered on the sample stock.",
        )
        action(
            "Import an image, SVG or STL",
            self._import_file,
            "Use your own artwork and then walk through setup and CAM.",
        )
        action(
            "Learn CNC / open the guided workflow",
            self._show_guided_workflow,
            "Work zero → machine → clamps → design → paths → preview → preflight.",
        )
        action(
            "Set up my machine",
            self._show_beginner_machine_setup,
            "Understand machine home versus work zero and review travel limits.",
        )
        action(
            "See cutters and starting settings",
            self._show_beginner_cutter_guide,
            "Illustrated bits, example materials and editable feed/plunge defaults.",
        )
        action(
            "Find a CNC term",
            self._show_cnc_glossary,
            "Search what work zero, feed, stepover, tabs and G-code mean.",
        )
        bottom = QPushButton("Open empty workspace", dialog)
        bottom.clicked.connect(dialog.close)
        layout.addWidget(bottom)
        self._beginner_welcome_dialog = dialog
        dialog.destroyed.connect(
            lambda _obj=None: setattr(self, "_beginner_welcome_dialog", None)
        )
        dialog.show()

    def _create_starter_project(self, kind: str) -> None:
        if self._background_job is not None or (
            self._import_thread is not None and self._import_thread.isRunning()
        ):
            self.statusBar().showMessage("Finish the current operation first.", 5000)
            return

        if getattr(self, "_project_dirty", False):
            message = QMessageBox(self)
            message.setWindowTitle("Replace the current project?")
            message.setText("Your current project has unsaved changes.")
            message.setInformativeText(
                "Save it before starting the example, discard changes, "
                "or cancel."
            )
            message.setStandardButtons(
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel
            )
            message.setDefaultButton(QMessageBox.StandardButton.Save)
            answer = message.exec()
            if answer == QMessageBox.StandardButton.Cancel:
                return
            if answer == QMessageBox.StandardButton.Save:
                self._after_save_action = (
                    lambda: self._create_starter_project(kind)
                )
                if not self._save_project():
                    self._after_save_action = None
                return
        try:
            project = starter_project(kind)
        except (ValueError, RuntimeError) as exc:
            QMessageBox.warning(self, "Starter project", str(exc))
            return
        self._set_project(project, project_path=None, selected_row=1)
        if hasattr(self, "_mark_project_dirty"):
            self._mark_project_dirty()
        self.statusBar().showMessage(
            "Example created. Edit the design, then open Guided Workflow.", 6500
        )
        self._show_guided_workflow()

    def _show_beginner_machine_setup(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Machine Setup · Start Here")
        dialog.resize(580, 370)
        layout = QVBoxLayout(dialog)
        profile = self._active_machine_profile()
        intro = QLabel(
            "<b>Machine home is NOT work zero.</b><br>"
            "Machine home is the controller's reference position. Work zero "
            "is where you tell the machine the carving begins on this board. "
            "CarveFoundry uses stock bottom-left XY0 and stock-top Z0."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        setup = QLabel(
            f"Current configured profile: {profile.name}<br>"
            f"X/Y/Z travel: {profile.work_x_mm:g} × "
            f"{profile.work_y_mm:g} × {profile.work_z_mm:g} mm<br>"
            "These saved dimensions and controller settings must be checked "
            "against your actual machine."
        )
        setup.setWordWrap(True)
        layout.addWidget(setup)
        configure = QPushButton("Review or edit my machine profile")
        configure.clicked.connect(lambda: (dialog.accept(), self._machine_profile()))
        layout.addWidget(configure)
        no_machine = QPushButton("I don't have a CNC machine yet")
        def mark_no_machine() -> None:
            self._settings.setValue("onboarding/no_machine", True)
            self._settings.setValue("onboarding/verified_machine", False)
            self._settings.sync()
            dialog.accept()
            self.statusBar().showMessage(
                "Design mode: you can learn without connecting a machine.", 6500
            )
        no_machine.clicked.connect(mark_no_machine)
        layout.addWidget(no_machine)
        ready = QPushButton("I have verified my machine profile")
        def mark_ready() -> None:
            self._settings.setValue("onboarding/no_machine", False)
            self._settings.setValue("onboarding/verified_machine", True)
            self._settings.sync()
            dialog.accept()
        ready.clicked.connect(mark_ready)
        layout.addWidget(ready)
        close = QPushButton("Close · I'll check later")
        close.clicked.connect(dialog.reject)
        layout.addWidget(close)
        dialog.exec()

    def _show_beginner_cutter_guide(self) -> None:
        dialog = QDialog(self)
        dialog.setObjectName("BeginnerCutterGuide")
        dialog.setWindowTitle("Learn Cutters and Starting Settings")
        dialog.resize(730, 480)
        layout = QVBoxLayout(dialog)
        text = QLabel(
            "These are deliberately modest EXAMPLES, not verified feeds or "
            "speeds for your particular CNC, bit or router. Confirm the "
            "manufacturer's recommendations, flute count, RPM, material, "
            "workholding and dust extraction before machining."
        )
        text.setWordWrap(True)
        layout.addWidget(text)
        content = QHBoxLayout()
        listing = QListWidget(dialog)
        picture = QLabel(dialog)
        picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
        details = QLabel(dialog)
        details.setWordWrap(True)
        details.setMinimumWidth(300)
        right = QVBoxLayout()
        right.addWidget(picture)
        right.addWidget(details)
        content.addWidget(listing)
        content.addLayout(right, 1)
        layout.addLayout(content, 1)
        tools = self._all_tools()
        for cutter in tools:
            listing.addItem(cutter.name)
        material = QComboBox(dialog)
        for starter in MATERIAL_STARTERS:
            material.addItem(starter.name + " · " + starter.description, starter)
        layout.addWidget(material)
        estimate = QLabel(dialog)
        estimate.setWordWrap(True)
        layout.addWidget(estimate)

        def update() -> None:
            index = listing.currentRow()
            if not 0 <= index < len(tools):
                return
            cutter = tools[index]
            starter = material.currentData()
            picture.setPixmap(_tool_picture(cutter))
            details.setText(f"{cutter.name}\n\n{cutter_description(cutter)}")
            feed, plunge, stepdown = material_starting_values(starter, cutter)
            estimate.setText(
                f"Illustrative {starter.name} start: feed {feed:g} mm/min; "
                f"plunge {plunge:g} mm/min; stepdown {stepdown:g} mm. "
                "RPM is NOT configured here—verify it separately."
            )

        listing.currentRowChanged.connect(update)
        material.currentIndexChanged.connect(update)
        listing.setCurrentRow(0)
        selected = self.tool_combo.currentData()
        if isinstance(selected, Cutter):
            for index, tool in enumerate(tools):
                if tool.name == selected.name:
                    listing.setCurrentRow(index)
                    break

        def apply() -> None:
            index = listing.currentRow()
            if not 0 <= index < len(tools):
                return
            cutter = tools[index]
            feed, plunge, stepdown = material_starting_values(
                material.currentData(), cutter,
            )
            for idx in range(self.tool_combo.count()):
                item = self.tool_combo.itemData(idx)
                if isinstance(item, Cutter) and item.name == cutter.name:
                    self.tool_combo.setCurrentIndex(idx)
                    break
            self._before_ribbon_mutation("set project material")
            self.project.material_name = material.currentData().name
            for key, value in (
                ("cam/feed_mm_min", feed),
                ("cam/plunge_mm_min", plunge),
                ("cam/stepdown_mm", stepdown),
            ):
                self._settings.setValue(key, value)
            self._settings.sync()
            # Settings are CAM input. Existing paths retain their OLD feeds:
            # invalidate rather than silently exporting mismatched NC.
            self._after_ribbon_mutation("set project material", True)
            dialog.accept()

        apply_button = QPushButton("Use cutter and example starting values")
        apply_button.clicked.connect(apply)
        layout.addWidget(apply_button)
        cancel = QPushButton("Close without changing settings")
        cancel.clicked.connect(dialog.reject)
        layout.addWidget(cancel)
        dialog.exec()

    def _show_project_notes(self) -> None:
        dialog = QDialog(self)
        dialog.setObjectName("ProjectNotesDialog")
        dialog.setWindowTitle("Project Notes / Carving Log")
        dialog.resize(650, 440)
        layout = QVBoxLayout(dialog)
        intro = QLabel(
            "Record your wood, the cutter and actual router speed, what worked "
            "and what you would change next time. Notes stay inside the CF3D "
            "project and can be undone. Editing notes does not change toolpaths."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        edit = QPlainTextEdit(dialog)
        edit.setObjectName("ProjectNotesText")
        edit.setPlainText(self.project.notes)
        edit.setPlaceholderText(
            "Wood species, cutter, physical spindle setting, "
            "workholding, result and lessons learned…"
        )
        layout.addWidget(edit, 1)
        controls = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel,
            parent=dialog,
        )
        controls.accepted.connect(dialog.accept)
        controls.rejected.connect(dialog.reject)
        layout.addWidget(controls)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_notes = edit.toPlainText()[:20000]
            if new_notes != self.project.notes:
                self._before_ribbon_mutation("edit project notes")
                self.project.notes = new_notes
                self._after_ribbon_mutation("edit project notes", True)
                self.statusBar().showMessage(
                    "Project notes updated. Save the CF3D to retain them.", 5000
                )

    def _show_cnc_glossary(self) -> None:
        terms = {
            "Stock": "The physical wood or material being cut. Measure its real X, Y and thickness.",
            "Machine home": "The controller's reference location. It is NOT the start of your carving.",
            "Work zero": "The origin used by the G-code. CarveFoundry uses stock bottom-left XY and stock-top Z0.",
            "Safe Z": "A retract height above Z0 while moving between cuts. It must clear real clamps/fences.",
            "Toolpath": "The ordered physical cutter movements generated from your design and chosen operation.",
            "Pocket": "Removes material inside a bounded region; use it to recess a shape.",
            "Profile": "Follows a boundary, potentially outside/inside it; cutouts need secure workholding.",
            "V-Carve": "Uses a V-shaped cutter to form variable-width lettering and details.",
            "Roughing": "Clears bulk material, leaving some for the finishing cutter.",
            "Finishing": "Adds closer, cutter-compensated passes for the final surface.",
            "Rest machining": "Targets sampled stock that a previous cutter could not remove.",
            "Feed rate": "Horizontal/cutting speed, here in millimeters per minute—not spindle RPM.",
            "Plunge rate": "Speed when entering the wood in Z; often slower than the cutting feed.",
            "RPM": "Router/spindle revolutions per minute. Check your tool/material combination.",
            "Stepover": "Sideways spacing between neighboring passes; smaller can improve finish but costs time.",
            "Stepdown": "Maximum depth removed in each successive pass.",
            "Workholding": "The clamps, fences, tape or fixture keeping material fixed while machining.",
            "Tabs": "Uncut bridges left on a cutout to hold a part in its board.",
            "Preflight": "Software checks of computed/posted moves against configured limits and keep-outs.",
            "G-code": "Controller commands for motion and machine functions; inspect before running.",
            "Tool change": "Stop, install the next cutter and re-probe Z0 before its next program.",
        }
        dialog = QDialog(self)
        dialog.setObjectName("CncGlossaryDialog")
        dialog.setWindowTitle("CNC Basics · Searchable Glossary")
        dialog.resize(700, 490)
        layout = QVBoxLayout(dialog)
        search = QLineEdit(dialog)
        search.setObjectName("CncGlossarySearch")
        search.setPlaceholderText("Search a CNC word or explanation…")
        layout.addWidget(search)
        entries = QListWidget(dialog)
        entries.setObjectName("CncGlossaryTerms")
        layout.addWidget(entries, 1)
        meaning = QLabel(dialog)
        meaning.setObjectName("CncGlossaryExplanation")
        meaning.setWordWrap(True)
        meaning.setMinimumHeight(66)
        layout.addWidget(meaning)

        def filter_entries(value: str) -> None:
            entries.clear()
            needle = value.casefold().strip()
            for word, explanation in terms.items():
                if needle in (word + " " + explanation).casefold():
                    entries.addItem(word)
            if entries.count():
                entries.setCurrentRow(0)
            else:
                meaning.setText("No matching term. Try 'zero' or 'cutter'.")

        def select_word() -> None:
            item = entries.currentItem()
            meaning.setText(terms[item.text()] if item is not None else "")

        search.textChanged.connect(filter_entries)
        entries.currentRowChanged.connect(select_word)
        filter_entries("")
        button = QPushButton("Open guided first carving")
        button.clicked.connect(
            lambda: (dialog.accept(), self._show_guided_workflow())
        )
        layout.addWidget(button)
        done = QPushButton("Close")
        done.clicked.connect(dialog.reject)
        layout.addWidget(done)
        dialog.exec()

    def _show_carving_quality_inspector(self) -> None:
        dialog = QDialog(self)
        dialog.setObjectName("CarvingQualityInspector")
        dialog.setWindowTitle("Will this design carve as intended?")
        dialog.resize(700, 520)
        layout = QVBoxLayout(dialog)
        title = QLabel("COMPARE THE DESIGN WITH THE PREDICTED CARVE")
        title.setObjectName("DialogTitle")
        layout.addWidget(title)
        intro = QLabel(
            "Check the design below, then simulate the ACTUAL posted NC to see "
            "sampled remaining wood. For 3D operations the viewer can highlight "
            "areas left above the modeled surface (blue) or below it (red). "
            "It cannot predict thin islands breaking, holder collisions, "
            "cutting forces or physical clamping."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        cutter = self.tool_combo.currentData()
        issues = design_advisories(
            self.project,
            cutter if isinstance(cutter, Cutter) else None,
            stale_reason=self._toolpaths_stale_reason,
        )
        for severity, message in issues:
            label = QLabel(f"{severity}: {message}")
            label.setWordWrap(True)
            layout.addWidget(label)
        btns = QHBoxLayout()
        simulate = QPushButton("Compare simulated wood")
        simulate.setEnabled(
            bool(self.project.toolpaths) and not self._toolpaths_stale_reason
        )
        simulate.clicked.connect(
            lambda: (dialog.accept(), self._run_stock_removal(
                spacing_mm=0.6, posted_nc=True
            ))
        )
        btns.addWidget(simulate)
        checks = QPushButton("Run planned-motion preflight")
        checks.setEnabled(
            bool(self.project.toolpaths) and not self._toolpaths_stale_reason
        )
        checks.clicked.connect(
            lambda: (dialog.accept(), self._preflight_toolpaths())
        )
        btns.addWidget(checks)
        layout.addLayout(btns)
        close = QPushButton("Close")
        close.clicked.connect(dialog.reject)
        layout.addWidget(close)
        dialog.exec()

    def _export_setup_sheet(self) -> None:
        if not self.project.toolpaths or self._toolpaths_stale_reason:
            QMessageBox.warning(
                self, "Setup sheet",
                "Generate current toolpaths before printing a job setup sheet.",
            )
            return
        name = "".join(
            char if char.isalnum() or char in "-_ " else "_"
            for char in self.project.name
        ).strip() or "CarveFoundry"
        directory = self.project_path.parent if self.project_path else Path.home()
        filename, _filter = QFileDialog.getSaveFileName(
            self, "Save printable CNC job sheet",
            str(directory / f"{name}_setup.pdf"), "PDF document (*.pdf)",
        )
        if not filename:
            return
        target = Path(filename)
        if target.suffix.lower() != ".pdf":
            target = target.with_suffix(".pdf")
        try:
            previous = getattr(self, "_last_exported_programs", None)
            names = ()
            if previous is not None and previous[0] == (
                self._guided_job_fingerprint()
            ):
                names = previous[1]
            html = job_sheet_html(
                self.project, self._active_machine_profile(),
                output_files=names,
            )
            document = QTextDocument()
            document.setHtml(html)
            from PySide6.QtGui import QPageSize
            writer = QPdfWriter(str(target))
            writer.setPageSize(QPageSize(QPageSize.PageSizeId.Letter))
            writer.setResolution(150)
            document.print_(writer)
            if not target.is_file() or target.stat().st_size == 0:
                raise OSError("The printable document could not be written.")
        except (OSError, ValueError, RuntimeError) as exc:
            QMessageBox.warning(self, "Setup sheet failed", str(exc))
            return
        self.statusBar().showMessage(
            f"Printable setup sheet saved: {target.name}", 7000
        )
