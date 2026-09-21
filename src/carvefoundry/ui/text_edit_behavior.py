"""Synchronize editable text properties and regenerate text geometry."""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase, QFontInfo

from ..core.font_handler import describe_qt_font_face
from ..core.primitives import text_mesh
from ..core.project import ProjectItem, TextProperties


class TextEditBehaviorMixin:
    """Apply text/font/layout edits to project items and CNC geometry."""

    def _legacy_text_properties(self, item: ProjectItem) -> TextProperties:
        dimensions = (
            np.asarray(item.mesh.dimensions, dtype=float)
            * float(item.source_units.millimeters_per_unit)
            if item.mesh is not None
            else np.array((40.0, 12.0, 1.0), dtype=float)
        )
        content = item.name.strip() or "Text"
        return TextProperties(
            content=content,
            font_family=QFontInfo(QFont()).family(),
            size_pt=max(6.0, float(dimensions[1]) * 72.0 / 25.4),
            box_width_mm=max(0.1, float(dimensions[0])),
            depth_mm=max(0.05, float(dimensions[2])),
        )

    def _refresh_text_font_styles(
        self,
        family: str,
        preferred: str | None = None,
    ) -> None:
        styles = list(QFontDatabase.styles(family))
        if not styles:
            styles = ["Regular"]

        current = preferred or self.text_font_style_combo.currentText()
        self.text_font_style_combo.blockSignals(True)
        try:
            self.text_font_style_combo.clear()
            self.text_font_style_combo.addItems(styles)
            index = self.text_font_style_combo.findText(current)
            if index < 0:
                index = self.text_font_style_combo.findText("Regular")
            self.text_font_style_combo.setCurrentIndex(max(0, index))
        finally:
            self.text_font_style_combo.blockSignals(False)

    def _update_text_editor_preview(
        self,
        requested_family: str | None = None,
    ) -> None:
        family = (
            requested_family
            or self._selected_text_font_family()
            or QFont().family()
        )
        preview_font = QFont(family)
        style = self.text_font_style_combo.currentText()
        if style:
            preview_font.setStyleName(style)
        if self.text_bold_button.isChecked():
            preview_font.setBold(True)
        if self.text_italic_button.isChecked():
            preview_font.setItalic(True)
        preview_font.setUnderline(self.text_underline_button.isChecked())
        preview_font.setStrikeOut(self.text_strike_button.isChecked())
        preview_font.setPointSizeF(
            max(10.0, min(22.0, float(self.text_size_spin.value())))
        )
        self.text_editor.setFont(preview_font)

    def _update_text_font_availability(self, requested_family: str) -> None:
        installed = set(QFontDatabase.families())
        if requested_family and requested_family not in installed:
            fallback = self._selected_text_font_family()
            self.text_font_face_status.setText("Font face: unresolved")
            self.text_font_warning.setText(
                f"Font “{requested_family}” is not installed. "
                f"Showing {fallback or 'the system fallback'} for editing only; "
                "CarveFoundry will not regenerate CNC text with a substituted font."
            )
            self.text_font_warning.show()
            return

        family = self._selected_text_font_family() or requested_family
        style = self.text_font_style_combo.currentText() or "Regular"
        try:
            face = describe_qt_font_face(family, style)
        except ValueError as exc:
            self.text_font_face_status.setText("Font face: unresolved")
            self.text_font_warning.setText(str(exc))
            self.text_font_warning.show()
            return

        self.text_font_face_status.setText(
            f"Font face: {face.display_name}  •  exact"
        )
        self.text_font_warning.clear()
        self.text_font_warning.hide()

    def _verify_selected_text_font_face(self) -> None:
        family = self._selected_text_font_family()
        style = self.text_font_style_combo.currentText() or "Regular"
        try:
            face = describe_qt_font_face(family, style)
        except ValueError as exc:
            self._update_text_font_availability(family)
            self.statusBar().showMessage(
                f"Font verification failed: {exc}",
                7000,
            )
            return
        self._update_text_font_availability(family)
        self.statusBar().showMessage(
            f"Exact font verified: {face.display_name}",
            4000,
        )

    def _sync_text_controls(self, item: ProjectItem) -> None:
        properties = item.text_properties or self._legacy_text_properties(item)
        family = properties.font_family or QFont().family()
        canonical_family, alias_style = self._canonical_text_font_family(
            family
        )
        installed_families = set(QFontDatabase.families())
        display_family = (
            canonical_family
            if canonical_family in installed_families
            else QFont().family()
        )

        self._updating_text_controls = True
        try:
            self.text_editor.setPlainText(properties.content)
            base_family, _variant = self._font_group_for_family(
                display_family
            )
            font_index = self.text_font_combo.findText(base_family)
            self.text_font_combo.setCurrentIndex(max(0, font_index))
            self._refresh_text_font_variants(
                self.text_font_combo.currentText(),
                display_family,
            )
            display_family = self._selected_text_font_family()
            self._refresh_text_font_styles(
                display_family,
                alias_style or properties.font_style,
            )
            self.text_size_spin.setValue(properties.size_pt)
            style_bold, style_italic = self._text_style_traits(
                display_family,
                self.text_font_style_combo.currentText(),
            )
            self.text_bold_button.setChecked(
                properties.bold or style_bold
            )
            self.text_italic_button.setChecked(
                properties.italic or style_italic
            )
            self.text_underline_button.setChecked(properties.underline)
            self.text_strike_button.setChecked(properties.strikeout)

            alignment_index = self.text_alignment_combo.findData(
                properties.alignment
            )
            self.text_alignment_combo.setCurrentIndex(
                max(0, alignment_index)
            )
            case_index = self.text_case_combo.findData(properties.case_mode)
            self.text_case_combo.setCurrentIndex(max(0, case_index))

            self.text_kerning_check.setChecked(properties.kerning)
            self.text_wrap_check.setChecked(properties.wrap_to_width)
            self.text_character_spacing_spin.setValue(
                properties.character_spacing_mm
            )
            self.text_word_spacing_spin.setValue(
                properties.word_spacing_mm
            )
            self.text_line_spacing_spin.setValue(
                properties.line_spacing_percent
            )
            self.text_horizontal_scale_spin.setValue(
                properties.horizontal_scale_percent
            )
            self.text_box_width_spin.setValue(
                max(0.1, properties.box_width_mm or 0.1)
            )

            geometry_index = self.text_geometry_combo.findData(
                properties.geometry_mode
            )
            self.text_geometry_combo.setCurrentIndex(
                max(0, geometry_index)
            )
            self.text_outline_width_spin.setValue(
                properties.outline_width_mm
            )
            self.text_depth_spin.setValue(properties.depth_mm)
        finally:
            self._updating_text_controls = False

        self._update_text_font_availability(family)
        self._update_text_editor_preview(display_family)
        self._update_text_control_enablement()

    @staticmethod
    def _text_style_traits(
        family: str,
        style: str,
    ) -> tuple[bool, bool]:
        font = QFontDatabase.font(family, style, 12)
        return font.bold(), font.italic()

    def _set_text_emphasis_buttons_from_style(self) -> None:
        family = self._selected_text_font_family()
        style = self.text_font_style_combo.currentText()
        style_bold, style_italic = self._text_style_traits(
            family,
            style,
        )
        self.text_bold_button.blockSignals(True)
        self.text_italic_button.blockSignals(True)
        try:
            self.text_bold_button.setChecked(style_bold)
            self.text_italic_button.setChecked(style_italic)
        finally:
            self.text_bold_button.blockSignals(False)
            self.text_italic_button.blockSignals(False)

    def _choose_text_style_for_emphasis(
        self,
        *,
        bold: bool,
        italic: bool,
    ) -> None:
        family = self._selected_text_font_family()
        styles = list(QFontDatabase.styles(family))
        if not styles:
            return

        current = self.text_font_style_combo.currentText()
        candidates = [
            style
            for style in styles
            if self._text_style_traits(family, style) == (bold, italic)
        ]
        if not candidates:
            return

        preferred = current if current in candidates else candidates[0]
        index = self.text_font_style_combo.findText(preferred)
        if index >= 0 and index != self.text_font_style_combo.currentIndex():
            self.text_font_style_combo.blockSignals(True)
            try:
                self.text_font_style_combo.setCurrentIndex(index)
            finally:
                self.text_font_style_combo.blockSignals(False)

    def _text_emphasis_changed(self, _checked: bool) -> None:
        if self._updating_text_controls:
            return
        self._choose_text_style_for_emphasis(
            bold=self.text_bold_button.isChecked(),
            italic=self.text_italic_button.isChecked(),
        )
        self._text_control_changed()

    def _text_style_changed(self, _style: str) -> None:
        if self._updating_text_controls:
            return
        self._set_text_emphasis_buttons_from_style()
        self._update_text_font_availability(
            self._selected_text_font_family()
        )
        self._text_control_changed()

    def _text_font_group_changed(self, base_family: str) -> None:
        if self._updating_text_controls:
            return
        self._refresh_text_font_variants(base_family)
        self._apply_text_font_selection_change()

    def _text_font_variant_changed(self, _index: int) -> None:
        if self._updating_text_controls:
            return
        self._apply_text_font_selection_change()

    def _apply_text_font_selection_change(self) -> None:
        family = self._selected_text_font_family()
        preferred_style = self.text_font_style_combo.currentText() or "Regular"
        self._refresh_text_font_styles(family, preferred_style)
        self._set_text_emphasis_buttons_from_style()
        self._update_text_font_availability(family)
        self._update_text_editor_preview(family)
        self._text_control_changed()

    def _text_layout_control_changed(self, _checked: bool) -> None:
        self._update_text_control_enablement()
        self._text_control_changed()

    def _text_geometry_control_changed(self, _index: int) -> None:
        self._update_text_control_enablement()
        self._text_control_changed()

    def _update_text_control_enablement(self) -> None:
        if not hasattr(self, "text_wrap_check"):
            return
        # Width also defines the alignment frame when wrapping is off, so it
        # remains editable at all times. Wrap only controls line breaking.
        self.text_box_width_spin.setEnabled(True)
        outline_enabled = (
            self.text_geometry_combo.currentData() == "outline"
        )
        self.text_outline_width_spin.setVisible(outline_enabled)
        self.text_outline_label.setVisible(outline_enabled)
        self.text_outline_width_spin.setEnabled(outline_enabled)
        self._update_text_cnc_hint()

    def _update_text_cnc_hint(self) -> None:
        if not hasattr(self, "text_cnc_hint"):
            return
        cutter = (
            self.tool_combo.currentData()
            if hasattr(self, "tool_combo")
            else None
        )
        diameter = getattr(cutter, "diameter_mm", None)
        if diameter is None:
            self.text_cnc_hint.setText(
                "Choose a cutter on Toolpaths to compare it with text geometry."
            )
            return

        diameter = float(diameter)
        if (
            self.text_geometry_combo.currentData() == "outline"
            and self.text_outline_width_spin.value() < diameter
        ):
            self.text_cnc_hint.setText(
                f"Machining warning: {self.text_outline_width_spin.value():.3f} mm "
                f"outline is narrower than the {diameter:.3f} mm active cutter. "
                "Use a smaller cutter, widen the outline, or use a V-carve strategy."
            )
            return

        self.text_cnc_hint.setText(
            f"Active cutter: {diameter:.3f} mm. Fine glyph details may require "
            "a smaller cutter or V-carve; Preview the calculated toolpath before cutting."
        )

    def _text_control_changed(self, *_args) -> None:
        if self._updating_text_controls:
            return
        self._update_text_control_enablement()
        self._update_text_editor_preview()
        self._text_update_timer.start()

    def _text_properties_from_controls(self) -> TextProperties:
        return TextProperties(
            content=self.text_editor.toPlainText(),
            font_family=self._selected_text_font_family(),
            font_style=self.text_font_style_combo.currentText() or "Regular",
            size_pt=float(self.text_size_spin.value()),
            bold=self.text_bold_button.isChecked(),
            italic=self.text_italic_button.isChecked(),
            underline=self.text_underline_button.isChecked(),
            strikeout=self.text_strike_button.isChecked(),
            alignment=str(
                self.text_alignment_combo.currentData() or "left"
            ),
            character_spacing_mm=float(
                self.text_character_spacing_spin.value()
            ),
            word_spacing_mm=float(self.text_word_spacing_spin.value()),
            kerning=self.text_kerning_check.isChecked(),
            line_spacing_percent=float(self.text_line_spacing_spin.value()),
            horizontal_scale_percent=float(
                self.text_horizontal_scale_spin.value()
            ),
            wrap_to_width=self.text_wrap_check.isChecked(),
            box_width_mm=float(self.text_box_width_spin.value()),
            depth_mm=float(self.text_depth_spin.value()),
            geometry_mode=str(
                self.text_geometry_combo.currentData() or "filled"
            ),
            outline_width_mm=float(
                self.text_outline_width_spin.value()
            ),
            case_mode=str(self.text_case_combo.currentData() or "normal"),
        )

    def _before_text_properties_change(self, _index: int) -> None:
        """History hook supplied by project_window.MainWindow."""

    def _after_text_properties_change(self, _index: int) -> None:
        """History hook supplied by project_window.MainWindow."""

    def _apply_text_properties_from_controls(self) -> None:
        if self._updating_text_controls:
            return
        index = self._selected_item_index()
        item = self._selected_item()
        if (
            index is None
            or item is None
            or item.kind.lower() != "text"
            or item.mesh is None
            or item.locked
        ):
            return

        properties = self._text_properties_from_controls()
        if not properties.content.strip():
            self.statusBar().showMessage(
                "Text object cannot be blank",
                3500,
            )
            return
        if item.text_properties == properties:
            return

        try:
            properties.validate()
            generated_mesh = text_mesh(properties=properties)
        except (RuntimeError, ValueError) as exc:
            self._set_activity_info(f"Text update failed\n{exc}")
            self.statusBar().showMessage(
                f"Could not update text: {exc}",
                6000,
            )
            return

        self._before_text_properties_change(index)
        item.mesh = generated_mesh
        item.text_properties = properties
        # Loaded generated objects can point at a materialized embedded STL.
        # Once edited, saving must embed the newly generated mesh instead.
        item.source_path = None
        self._invalidate_toolpaths("Text geometry")
        self._sync_transform_controls(item)
        self.selection_info.setText(self._mesh_properties_text(item))
        row = index + 1
        self.object_selector.blockSignals(True)
        try:
            self.object_selector.setItemText(
                row,
                self._object_selector_text(item),
            )
        finally:
            self.object_selector.blockSignals(False)
        list_item = self.project_list.item(row)
        if list_item is not None:
            kind = item.kind.upper()
            content_preview = " ".join(
                properties.content.splitlines()
            ).strip()
            if len(content_preview) > 90:
                content_preview = content_preview[:87].rstrip() + "…"
            list_item.setToolTip(
                f"{kind} • {item.name}"
                + (
                    f"\nContent: {content_preview}"
                    if content_preview
                    else ""
                )
                + "\nDouble-click or press F2 to rename."
            )
        self.viewport.set_selected_item(index)
        self.viewport.update()
        self._after_text_properties_change(index)
        self.statusBar().showMessage(
            f"Updated text: {item.name}",
            2500,
        )

    def _focus_text_editor(self) -> None:
        item = self._selected_item()
        if item is None or item.kind.lower() != "text":
            return
        self._ensure_inspector_visible()
        self.text_editor.setFocus(Qt.FocusReason.OtherFocusReason)
        self.text_editor.selectAll()
