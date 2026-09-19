"""Generate editable, fixture-checked batch grids in a background job."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)

from carvefoundry.core.batch_layout import batch_grid
from carvefoundry.core.tools import Cutter


class BatchLayoutMixin:
    """Repeat a selected part (or grouped components) on the same stock."""

    def _run_batch_layout(
        self,
        *,
        copies: int,
        columns: int,
        gap_mm: float,
        margin_mm: float,
    ) -> bool:
        if self._background_job is not None:
            self.statusBar().showMessage("Finish the current operation first", 5000)
            return False
        indices = self._selected_design_indices(expand_groups=True)
        sources = tuple(self.project.items[i] for i in indices)
        if not sources or any(not i.visible or i.mesh is None for i in sources):
            self.statusBar().showMessage("Select visible geometry to duplicate.", 6000)
            return False
        cutter = self.tool_combo.currentData()
        if not isinstance(cutter, Cutter):
            self.statusBar().showMessage("Choose a cutter for layout clearance.", 6000)
            return False
        project = self.project
        ids = tuple(source.item_id for source in sources)

        def calculate(progress):
            progress(0.05, "Measuring selected model footprint")
            clones = batch_grid(
                project,
                sources,
                copies=copies,
                columns=columns,
                gap_mm=gap_mm,
                margin_mm=margin_mm,
                cutter_radius_mm=cutter.radius_mm,
            )
            progress(0.95, "Batch grid validated against stock and fixtures")
            return clones

        def finished(clones):
            if self.project is not project or tuple(source.item_id for source in sources) != ids:
                raise ValueError("Batch source changed before completion.")
            self._before_ribbon_mutation("batch grid")
            for source in sources:
                source.visible = False
            start = len(self.project.items)
            self.project.items.extend(clones)
            self._refresh_project_list(start + 1)
            self._select_project_indices(list(range(start, start + len(sources))))
            self.viewport.update()
            self._after_ribbon_mutation("batch grid", True)
            self.statusBar().showMessage(
                f"Created {copies} stock-registered copies "
                f"({len(clones)} models); originals hidden.", 8000
            )

        def failed(message: str):
            self.statusBar().showMessage(
                f"Batch layout failed: {message}", 9000
            )
            self._set_activity_info(f"Batch layout failed\n{message}")

        return self._start_background_job(
            "Lay out batch production",
            task=calculate,
            on_done=finished,
            on_failed=failed,
            indeterminate=True,
        )

    def _batch_layout(self) -> bool:
        indices = self._selected_design_indices(expand_groups=True)
        if not indices:
            self.statusBar().showMessage("Select the batch template object(s).", 6000)
            return False
        cutter = self.tool_combo.currentData()
        if not isinstance(cutter, Cutter):
            self.statusBar().showMessage("Select the clearance cutter first.", 6000)
            return False

        dialog = QDialog(self)
        dialog.setWindowTitle("Batch Production — Grid Layout")
        dialog.setMinimumWidth(530)
        layout = QVBoxLayout(dialog)
        label = QLabel(
            "Repeat the selected part or grouped components across the stock "
            "without changing the templates. Copies remain independent editable "
            "objects. The selected cutter's radius is used for fixture clearance; "
            "recheck the entire cutter set in CNC Preflight."
        )
        label.setWordWrap(True)
        layout.addWidget(label)
        form = QFormLayout()
        copies = QSpinBox(dialog)
        copies.setRange(1, 256)
        copies.setValue(4)
        columns = QSpinBox(dialog)
        columns.setRange(1, 256)
        columns.setValue(2)
        gap = QDoubleSpinBox(dialog)
        gap.setRange(0, 10000)
        gap.setDecimals(3)
        gap.setValue(10)
        gap.setSuffix(" mm")
        margin = QDoubleSpinBox(dialog)
        margin.setRange(0, 10000)
        margin.setDecimals(3)
        margin.setValue(max(10.0, cutter.radius_mm))
        margin.setSuffix(" mm")
        form.addRow("Total copies", copies)
        form.addRow("Columns", columns)
        form.addRow("Gap between parts", gap)
        form.addRow("Margin around stock", margin)
        layout.addLayout(form)

        def copies_changed(value: int):
            columns.setMaximum(value)
        copies.valueChanged.connect(copies_changed)
        info = QLabel(
            f"Stock: {self.project.stock.width_mm:g} × "
            f"{self.project.stock.height_mm:g} mm · "
            f"Clearance cutter: {cutter.name} (radius {cutter.radius_mm:g} mm). "
            "The originals are hidden after all copies validate; this action "
            "supports Undo/Redo. It is a regular grid, not irregular-shape nesting."
        )
        info.setWordWrap(True)
        layout.addWidget(info)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=dialog,
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        return self._run_batch_layout(
            copies=copies.value(),
            columns=columns.value(),
            gap_mm=gap.value(),
            margin_mm=margin.value(),
        )
