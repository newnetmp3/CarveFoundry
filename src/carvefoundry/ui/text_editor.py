"""Compatibility facade for editable CNC text support.

Font discovery, Inspector construction, and live text application are separate
modules so typography work does not grow another monolithic UI mixin.
"""
from __future__ import annotations

from .text_control_builder import TextControlBuilderMixin
from .text_edit_behavior import TextEditBehaviorMixin
from .text_font_catalog import TextFontCatalogMixin


class TextEditorMixin(
    TextFontCatalogMixin,
    TextControlBuilderMixin,
    TextEditBehaviorMixin,
):
    """Compose editable CNC typography behavior for MainWindow."""
