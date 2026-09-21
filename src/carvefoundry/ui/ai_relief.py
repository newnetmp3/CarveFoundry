"""Local AI bas-relief creation dialog and automatic STL import."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from carvefoundry.core.ai_relief import ReliefRequest


def build_ai_relief_dialog(parent, *, width_mm: float, height_mm: float, thickness_mm: float):
    """Build a real input form; no ML weights are loaded on the GUI thread."""
    dialog = QDialog(parent)
    dialog.setWindowTitle("Generate local AI bas-relief")
    dialog.setMinimumWidth(540)
    layout = QVBoxLayout(dialog)
    notice = QLabel(
        "Generate a 2.5D relief using LOCAL AI. An image uses Depth Anything V2; "
        "a text prompt first creates a reference image with SD-Turbo. "
        "The first run downloads model weights, then runs inference locally."
    )
    notice.setWordWrap(True)
    layout.addWidget(notice)
    form = QFormLayout()
    layout.addLayout(form)
    source = QComboBox()
    source.addItem("From image", "image")
    source.addItem("From text prompt", "prompt")
    form.addRow("Source", source)

    image_row = QWidget()
    image_layout = QHBoxLayout(image_row)
    image_layout.setContentsMargins(0, 0, 0, 0)
    image_path = QLineEdit()
    image_path.setObjectName("AiReliefImagePath")
    image_path.setPlaceholderText("Local PNG, JPEG, WEBP, BMP…")
    browse = QPushButton("Browse…")
    image_layout.addWidget(image_path, 1)
    image_layout.addWidget(browse)
    form.addRow("Reference image", image_row)

    prompt = QPlainTextEdit()
    prompt.setObjectName("AiReliefPrompt")
    prompt.setPlaceholderText(
        "Example: A Navy Chief anchor with heavy chain and raised USN lettering"
    )
    prompt.setFixedHeight(78)
    form.addRow("Prompt", prompt)

    def choose_image():
        path, _ = QFileDialog.getOpenFileName(
            dialog, "Choose relief reference", str(Path.home()),
            "Images (*.png *.jpg *.jpeg *.webp *.bmp);;All files (*)"
        )
        if path:
            image_path.setText(path)

    browse.clicked.connect(choose_image)

    def switch_mode():
        image_row.setVisible(source.currentData() == "image")
        prompt.setVisible(source.currentData() == "prompt")

    source.currentIndexChanged.connect(switch_mode)
    switch_mode()

    def mm_field(default: float, minimum: float, maximum: float) -> QDoubleSpinBox:
        control = QDoubleSpinBox()
        control.setDecimals(2)
        control.setRange(minimum, maximum)
        control.setSuffix(" mm")
        control.setValue(max(minimum, min(maximum, default)))
        return control

    width = mm_field(max(1, width_mm - 20), 1, 10000)
    height = mm_field(max(1, height_mm - 20), 1, 10000)
    backing = mm_field(min(1.5, max(0.1, thickness_mm / 4)), 0.1, 100)
    relief = mm_field(min(4.0, max(0.1, thickness_mm - backing.value())), 0.1, 100)
    samples = QSpinBox()
    samples.setRange(32, 384)
    samples.setValue(256)
    samples.setToolTip("Maximum samples on the longer axis. 256 ≈ 260k faces; 384 ≈ 590k.")
    invert = QCheckBox("Reverse estimated foreground/background")
    blur = mm_field(0.6, 0, 12)
    blur.setSuffix(" px")
    form.addRow("Relief width", width)
    form.addRow("Relief height", height)
    form.addRow("Raised depth", relief)
    form.addRow("Backing thickness", backing)
    form.addRow("Grid resolution", samples)
    form.addRow("Invert depth", invert)
    form.addRow("Depth smoothing", blur)

    reminder = QLabel(
        "Millimeters; XY bottom-left / stock-top Z0 after import. "
        "The STL is a closed heightfield, not a full 360° sculpture. "
        "Generated subject depth is inferred, not physically measured. "
        "Text generation may be extremely slow without a GPU; "
        "review SD-Turbo's model license before commercial use."
    )
    reminder.setWordWrap(True)
    layout.addWidget(reminder)
    errors = QLabel("")
    errors.setObjectName("AiReliefValidation")
    errors.setWordWrap(True)
    layout.addWidget(errors)
    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Generate STL…")
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    fields = {
        "source": source, "image": image_path, "prompt": prompt,
        "width": width, "height": height, "backing": backing,
        "relief": relief, "samples": samples, "invert": invert,
        "smoothing": blur, "errors": errors, "buttons": buttons,
    }
    return dialog, fields


class AiReliefMixin:
    def _generate_ai_relief(self) -> None:
        if self._background_job is not None or (
            self._import_thread is not None and self._import_thread.isRunning()
        ):
            self.statusBar().showMessage("Finish the current operation first", 4000)
            return
        stock = self.project.stock
        dialog, f = build_ai_relief_dialog(
            self, width_mm=stock.width_mm,
            height_mm=stock.height_mm, thickness_mm=stock.thickness_mm,
        )
        selected_request: list[ReliefRequest] = []

        def accept():
            mode = f["source"].currentData()
            image = f["image"].text().strip() if mode == "image" else ""
            prompt = f["prompt"].toPlainText().strip() if mode == "prompt" else ""
            if f["width"].value() > stock.width_mm or f["height"].value() > stock.height_mm:
                f["errors"].setText("Relief XY size must fit inside the current stock.")
                return
            if f["backing"].value() + f["relief"].value() > stock.thickness_mm:
                f["errors"].setText(
                    "Backing + raised depth exceeds stock thickness. "
                    "Reduce the height or increase stock thickness."
                )
                return
            if not image and not prompt:
                f["errors"].setText("Select an image or enter a prompt.")
                return
            directory = self._settings.value("ai_relief/last_directory", str(Path.home()))
            path, _ = QFileDialog.getSaveFileName(
                dialog, "Save generated relief STL",
                str(Path(directory) / "CarveFoundry_Relief.stl"),
                "STL mesh (*.stl)",
            )
            if not path:
                return
            if Path(path).suffix.lower() != ".stl":
                path += ".stl"
            request = ReliefRequest(
                output_path=path, width_mm=f["width"].value(),
                height_mm=f["height"].value(), relief_depth_mm=f["relief"].value(),
                backing_thickness_mm=f["backing"].value(),
                grid_samples=f["samples"].value(), image_path=image,
                prompt=prompt, invert_depth=f["invert"].isChecked(),
                smoothing_px=f["smoothing"].value(),
            )
            try:
                request.validate()
            except ValueError as exc:
                f["errors"].setText(str(exc))
                return
            self._settings.setValue("ai_relief/last_directory", str(Path(path).parent))
            selected_request.append(request)
            dialog.accept()

        f["buttons"].accepted.connect(accept)
        if dialog.exec() != QDialog.DialogCode.Accepted or not selected_request:
            return

        def done(result):
            output = str(result["path"])
            self.statusBar().showMessage(
                f"AI relief saved: {Path(output).name}; importing STL…", 6000
            )
            # Reuse the established STL subprocess parser, GPU upload and
            # Undo/Redo hooks rather than constructing a special mesh item.
            self._start_import([output], "STL")

        def failed(message: str):
            self._set_activity_info("Local AI relief generation failed\n\n" + message)
            self.statusBar().showMessage(
                f"Local AI relief failed: {message[:180]}", 10000
            )

        self._start_background_job(
            "Local AI bas-relief",
            request=selected_request[0],
            on_done=done,
            on_failed=failed,
            indeterminate=True,
            cancelable=True,
        )
