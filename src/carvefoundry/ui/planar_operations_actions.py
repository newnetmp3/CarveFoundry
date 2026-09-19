"""Complete menu/rail actions for planar design Booleans and signed offsets."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
)

from carvefoundry.core.planar_operations import (
    BOOLEAN_OPERATIONS,
    PLANAR_KINDS,
    build_planar_result,
)
from carvefoundry.core.project import ProjectItem
from carvefoundry.core.transform import Transform3D
from carvefoundry.core.units import ModelUnits

_LABELS = {
    "union": "Union",
    "subtract": "Subtract",
    "intersect": "Intersect",
    "offset": "Offset",
}


class PlanarOperationsMixin:
    """Operate on *selected* planar shapes; do not mutate original mesh assets."""

    def _planar_operation_form(
        self,
        operation: str,
        items: tuple[ProjectItem, ...],
    ) -> tuple[float, float, str] | None:
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Vector {_LABELS[operation]}")
        form = QFormLayout(dialog)
        if operation == "subtract":
            form.addRow(QLabel(
                f"Keep {items[0].name}; subtract the other selected silhouettes.\n"
                "The base is the first selected item in Layers order."
            ))
        else:
            form.addRow(QLabel(
                "Uses stock-relative XY silhouettes, not 3D mesh Booleans.\n"
                "Creates a new shape with its top at stock Z0; hides the originals."
            ))
        distance = None
        corner = None
        if operation == "offset":
            distance = QDoubleSpinBox(dialog)
            distance.setRange(-5000.0, 5000.0)
            distance.setDecimals(3)
            distance.setSingleStep(0.25)
            distance.setValue(1.0)
            distance.setSuffix(" mm")
            distance.setToolTip("Positive expands; negative contracts. Zero is not allowed.")
            form.addRow("Signed offset", distance)
            corner = QComboBox(dialog)
            corner.addItems(["round", "mitre", "bevel"])
            form.addRow("Corner style", corner)

        depth = QDoubleSpinBox(dialog)
        depth.setRange(0.05, max(0.05, float(self.project.stock.thickness_mm)))
        depth.setDecimals(3)
        depth.setSingleStep(0.25)
        depth.setValue(min(depth.maximum(), max(0.05, self._tool_option_depth_mm)))
        depth.setSuffix(" mm")
        form.addRow("Result depth below Z0", depth)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=dialog,
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return (
            float(depth.value()),
            float(distance.value()) if distance is not None else 0.0,
            corner.currentText() if corner is not None else "round",
        )

    def _run_planar_operation(
        self,
        operation: str,
        *,
        depth_mm: float | None = None,
        offset_mm: float | None = None,
        join_style: str = "round",
    ) -> bool:
        if operation not in BOOLEAN_OPERATIONS | {"offset"}:
            raise ValueError(f"Unknown planar operation: {operation}")
        if self._background_job is not None:
            self.statusBar().showMessage("Finish the current background job first", 4000)
            return False

        indices = self._selected_design_indices()
        required = 1 if operation == "offset" else 2
        if (len(indices) != 1 if operation == "offset" else len(indices) < required):
            self.statusBar().showMessage(
                "Offset: select one shape; Boolean: select two or more shapes.", 6000
            )
            return False
        items = tuple(self.project.items[index] for index in indices)
        if any(item.kind.lower() not in PLANAR_KINDS or item.mesh is None for item in items):
            self.statusBar().showMessage(
                "Select planar design shapes; 3D STL reliefs are not 2D vectors.", 6000
            )
            return False

        if depth_mm is None or (operation == "offset" and offset_mm is None):
            values = self._planar_operation_form(operation, items)
            if values is None:
                return False
            depth_mm, offset_mm, join_style = values
        assert depth_mm is not None
        offset_mm = float(offset_mm or 0.0)
        label = _LABELS[operation]
        source_ids = tuple(item.item_id for item in items)

        def calculate(progress):
            progress(0.1, f"Projecting {len(items)} selected shape(s)")
            result = build_planar_result(
                items,
                operation=operation,
                depth_mm=float(depth_mm),
                offset_mm=offset_mm,
                join_style=join_style,
            )
            progress(0.95, "Validating watertight extrusion")
            return result

        def completed(mesh):
            # No mutation happens until the entire calculation validates.
            if tuple(self.project.items[index].item_id for index in indices) != source_ids:
                raise ValueError("Selection changed; no shapes were modified.")
            stem = f"{items[0].name} {_LABELS[operation]}"
            output = ProjectItem(
                name=self._unique_item_name(stem),
                kind="offset" if operation == "offset" else "boolean",
                mesh=mesh,
                source_units=ModelUnits.MILLIMETERS,
                transform=Transform3D(),
            )
            self._before_ribbon_mutation(f"vector {operation}")
            for item in items:
                item.visible = False
            self.project.items.append(output)
            self._refresh_project_list(len(self.project.items))
            self._select_project_indices([len(self.project.items) - 1])
            self.viewport.update()
            self._after_ribbon_mutation(f"vector {operation}", True)
            self.statusBar().showMessage(
                f"{label}: created {output.name} at stock Z0; originals hidden.", 7000
            )

        return self._start_background_job(
            f"Vector {label}",
            task=calculate,
            on_done=completed,
            indeterminate=True,
        )
