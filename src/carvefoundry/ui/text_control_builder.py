"""Build the Inspector controls for editable CNC text."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontInfo, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class TextControlBuilderMixin:
    """Create and wire the editable-text Inspector controls."""

    def _build_text_controls(self) -> QWidget:
        widget = QWidget()
        widget.setObjectName("TextControls")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 6, 0, 10)
        layout.setSpacing(6)

        heading = QLabel("Text")
        heading.setObjectName("SectionHeading")
        layout.addWidget(heading)

        self.text_editor = QPlainTextEdit()
        self.text_editor.setPlaceholderText("Enter text…")
        self.text_editor.setMinimumHeight(72)
        self.text_editor.setMaximumHeight(120)
        self.text_editor.setMinimumWidth(0)
        self.text_editor.setTabChangesFocus(True)
        self.text_editor.textChanged.connect(self._text_control_changed)
        layout.addWidget(self.text_editor)

        typography_heading = QLabel("Typography")
        typography_heading.setObjectName("TextSubheading")
        layout.addWidget(typography_heading)

        typography_form = QFormLayout()
        self._configure_inspector_form(typography_form)
        layout.addLayout(typography_form)

        installed_families = self._installed_text_font_families()
        self._text_font_aliases = self._fontconfig_text_font_aliases(
            installed_families
        )
        selectable_families = [
            family
            for family in installed_families
            if family.casefold() not in self._text_font_aliases
        ]
        self._text_font_groups = self._group_text_font_families(
            selectable_families
        )

        self.text_font_combo = QComboBox()
        for base_family, variants in self._text_font_groups.items():
            preview_family = variants[0][1]
            self.text_font_combo.addItem(base_family, preview_family)
            item_index = self.text_font_combo.count() - 1
            self.text_font_combo.setItemData(
                item_index,
                QFont(preview_family),
                Qt.ItemDataRole.FontRole,
            )
        self.text_font_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.text_font_combo.setMinimumContentsLength(10)
        self._configure_inspector_field(self.text_font_combo)
        self.text_font_combo.setToolTip(
            "Base font families, previewed in their own typeface. Family-level "
            "alternatives such as Condensed or SemiBold are in Variant."
        )
        typography_form.addRow("Font", self.text_font_combo)

        self.text_font_variant_combo = QComboBox()
        self.text_font_variant_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.text_font_variant_combo.setMinimumContentsLength(8)
        self._configure_inspector_field(self.text_font_variant_combo)
        self.text_font_variant_combo.setToolTip(
            "Installed alternatives belonging to the selected base family."
        )
        typography_form.addRow("Variant", self.text_font_variant_combo)

        default_family = QFontInfo(QFont()).family()
        default_base, _default_variant = self._font_group_for_family(
            default_family
        )
        default_index = self.text_font_combo.findText(default_base)
        self.text_font_combo.setCurrentIndex(max(0, default_index))
        self._refresh_text_font_variants(
            self.text_font_combo.currentText(),
            default_family,
        )
        self.text_font_combo.currentTextChanged.connect(
            self._text_font_group_changed
        )
        self.text_font_variant_combo.currentIndexChanged.connect(
            self._text_font_variant_changed
        )

        self.text_font_style_combo = QComboBox()
        self.text_font_style_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.text_font_style_combo.setMinimumContentsLength(8)
        self._configure_inspector_field(self.text_font_style_combo)
        self.text_font_style_combo.currentTextChanged.connect(
            self._text_style_changed
        )
        typography_form.addRow("Style", self.text_font_style_combo)

        self.text_size_spin = self._configured_spin(
            minimum=1.0,
            maximum=1000.0,
            decimals=1,
            step=1.0,
            suffix=" pt",
        )
        self.text_size_spin.setToolTip(
            "Font point size, matching conventional word-processor sizing."
        )
        self.text_size_spin.valueChanged.connect(self._text_control_changed)
        typography_form.addRow("Size", self.text_size_spin)

        format_bar = QWidget()
        format_bar.setMinimumWidth(0)
        format_layout = QHBoxLayout(format_bar)
        format_layout.setContentsMargins(0, 0, 0, 0)
        format_layout.setSpacing(4)
        self.text_bold_button = QPushButton("B")
        self.text_italic_button = QPushButton("I")
        self.text_underline_button = QPushButton("U")
        self.text_strike_button = QPushButton("S")
        for button, tooltip in (
            (self.text_bold_button, "Bold"),
            (self.text_italic_button, "Italic"),
            (self.text_underline_button, "Underline"),
            (self.text_strike_button, "Strikethrough"),
        ):
            button.setCheckable(True)
            button.setFixedWidth(34)
            button.setToolTip(tooltip)
            if button in (
                self.text_bold_button,
                self.text_italic_button,
            ):
                button.toggled.connect(self._text_emphasis_changed)
            else:
                button.toggled.connect(self._text_control_changed)
            format_layout.addWidget(button)
        format_layout.addStretch(1)
        typography_form.addRow("Effects", format_bar)

        self.text_alignment_combo = QComboBox()
        for title, value in (
            ("Left", "left"),
            ("Center", "center"),
            ("Right", "right"),
            ("Justified", "justify"),
        ):
            self.text_alignment_combo.addItem(title, value)
        self._configure_inspector_field(self.text_alignment_combo)
        self.text_alignment_combo.currentIndexChanged.connect(
            self._text_control_changed
        )
        typography_form.addRow("Align", self.text_alignment_combo)

        self.text_case_combo = QComboBox()
        for title, value in (
            ("Normal", "normal"),
            ("UPPERCASE", "uppercase"),
            ("lowercase", "lowercase"),
            ("Title Case", "title"),
        ):
            self.text_case_combo.addItem(title, value)
        self._configure_inspector_field(self.text_case_combo)
        self.text_case_combo.currentIndexChanged.connect(
            self._text_control_changed
        )
        typography_form.addRow("Case", self.text_case_combo)

        spacing_heading = QLabel("Spacing & layout")
        spacing_heading.setObjectName("TextSubheading")
        layout.addWidget(spacing_heading)

        spacing_form = QFormLayout()
        self._configure_inspector_form(spacing_form)
        layout.addLayout(spacing_form)

        self.text_kerning_check = QCheckBox("Pair kerning")
        self.text_kerning_check.setChecked(True)
        self.text_kerning_check.setToolTip(
            "Use the selected font's kerning pairs when positioning glyphs."
        )
        self.text_kerning_check.toggled.connect(self._text_control_changed)
        spacing_form.addRow(self.text_kerning_check)

        self.text_wrap_check = QCheckBox("Wrap to text box width")
        self.text_wrap_check.toggled.connect(self._text_layout_control_changed)
        spacing_form.addRow(self.text_wrap_check)

        self.text_character_spacing_spin = self._configured_spin(
            minimum=-25.0,
            maximum=100.0,
            decimals=3,
            step=0.1,
            suffix=" mm",
        )
        self.text_character_spacing_spin.valueChanged.connect(
            self._text_control_changed
        )
        spacing_form.addRow(
            "Character spacing",
            self.text_character_spacing_spin,
        )

        self.text_word_spacing_spin = self._configured_spin(
            minimum=-25.0,
            maximum=100.0,
            decimals=3,
            step=0.25,
            suffix=" mm",
        )
        self.text_word_spacing_spin.valueChanged.connect(
            self._text_control_changed
        )
        spacing_form.addRow("Word spacing", self.text_word_spacing_spin)

        self.text_line_spacing_spin = self._configured_spin(
            minimum=25.0,
            maximum=500.0,
            decimals=1,
            step=5.0,
            suffix=" %",
        )
        self.text_line_spacing_spin.valueChanged.connect(
            self._text_control_changed
        )
        spacing_form.addRow("Line spacing", self.text_line_spacing_spin)

        self.text_horizontal_scale_spin = self._configured_spin(
            minimum=10.0,
            maximum=400.0,
            decimals=1,
            step=5.0,
            suffix=" %",
        )
        self.text_horizontal_scale_spin.setToolTip(
            "Horizontally stretch or condense character width."
        )
        self.text_horizontal_scale_spin.valueChanged.connect(
            self._text_control_changed
        )
        spacing_form.addRow(
            "Character width",
            self.text_horizontal_scale_spin,
        )

        self.text_box_width_spin = self._configured_spin(
            minimum=0.1,
            maximum=100000.0,
            decimals=3,
            step=1.0,
            suffix=" mm",
        )
        self.text_box_width_spin.valueChanged.connect(
            self._text_control_changed
        )
        spacing_form.addRow("Text box width", self.text_box_width_spin)

        geometry_heading = QLabel("CNC geometry")
        geometry_heading.setObjectName("TextSubheading")
        layout.addWidget(geometry_heading)

        geometry_form = QFormLayout()
        self._configure_inspector_form(geometry_form)
        layout.addLayout(geometry_form)

        self.text_geometry_combo = QComboBox()
        self.text_geometry_combo.addItem("Filled", "filled")
        self.text_geometry_combo.addItem("Outline", "outline")
        self._configure_inspector_field(self.text_geometry_combo)
        self.text_geometry_combo.currentIndexChanged.connect(
            self._text_geometry_control_changed
        )
        geometry_form.addRow("Geometry", self.text_geometry_combo)

        self.text_outline_width_spin = self._configured_spin(
            minimum=0.05,
            maximum=50.0,
            decimals=3,
            step=0.1,
            suffix=" mm",
        )
        self.text_outline_width_spin.valueChanged.connect(
            self._text_control_changed
        )
        self.text_outline_label = QLabel("Outline width")
        geometry_form.addRow(
            self.text_outline_label,
            self.text_outline_width_spin,
        )

        self.text_depth_spin = self._configured_spin(
            minimum=0.05,
            maximum=1000.0,
            decimals=3,
            step=0.25,
            suffix=" mm",
        )
        self.text_depth_spin.setToolTip(
            "Extruded text thickness. Text top remains at the object's Z level."
        )
        self.text_depth_spin.valueChanged.connect(self._text_control_changed)
        geometry_form.addRow("Depth", self.text_depth_spin)

        self._text_shortcuts: list[QShortcut] = []
        for sequence, callback in (
            ("Ctrl+B", self.text_bold_button.toggle),
            ("Ctrl+I", self.text_italic_button.toggle),
            ("Ctrl+U", self.text_underline_button.toggle),
            ("Ctrl+Shift+X", self.text_strike_button.toggle),
            (
                "Ctrl+L",
                lambda: self.text_alignment_combo.setCurrentIndex(
                    self.text_alignment_combo.findData("left")
                ),
            ),
            (
                "Ctrl+E",
                lambda: self.text_alignment_combo.setCurrentIndex(
                    self.text_alignment_combo.findData("center")
                ),
            ),
            (
                "Ctrl+R",
                lambda: self.text_alignment_combo.setCurrentIndex(
                    self.text_alignment_combo.findData("right")
                ),
            ),
            (
                "Ctrl+J",
                lambda: self.text_alignment_combo.setCurrentIndex(
                    self.text_alignment_combo.findData("justify")
                ),
            ),
        ):
            shortcut = QShortcut(QKeySequence(sequence), widget)
            shortcut.setContext(
                Qt.ShortcutContext.WidgetWithChildrenShortcut
            )
            shortcut.activated.connect(callback)
            self._text_shortcuts.append(shortcut)

        note = QLabel(
            "Font geometry comes from the exact installed system font face. "
            "CarveFoundry refuses silent Qt font substitution when regenerating "
            "text so CNC geometry cannot quietly change typefaces. Selected text "
            "uses the same viewport resize handles as other design objects."
        )
        note.setObjectName("Muted")
        note.setWordWrap(True)
        layout.addWidget(note)

        self.text_font_face_status = QLabel()
        self.text_font_face_status.setObjectName("TextFontFaceStatus")
        self.text_font_face_status.setWordWrap(True)
        layout.addWidget(self.text_font_face_status)

        self.text_font_verify_button = QPushButton("Verify Font Face")
        self.text_font_verify_button.setToolTip(
            "Verify that Qt resolves the selected family and style to the exact "
            "installed face used to generate CNC outlines."
        )
        self.text_font_verify_button.clicked.connect(
            self._verify_selected_text_font_face
        )
        layout.addWidget(self.text_font_verify_button)

        self.text_font_warning = QLabel()
        self.text_font_warning.setObjectName("TextFontWarning")
        self.text_font_warning.setWordWrap(True)
        self.text_font_warning.hide()
        layout.addWidget(self.text_font_warning)

        self.text_cnc_hint = QLabel()
        self.text_cnc_hint.setObjectName("TextCncHint")
        self.text_cnc_hint.setWordWrap(True)
        layout.addWidget(self.text_cnc_hint)

        initial_family = self._selected_text_font_family()
        self._refresh_text_font_styles(initial_family, "Regular")
        self._update_text_editor_preview(initial_family)

        widget.setVisible(False)
        return widget

