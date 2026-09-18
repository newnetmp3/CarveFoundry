from PySide6.QtWidgets import QApplication

from carvefoundry.ui.main_window import MainWindow

_APP = QApplication.instance() or QApplication([])

def test_main_window_builds_text_inspector_offscreen() -> None:
    window = MainWindow()
    try:
        assert window.text_font_combo.count() > 0
        assert window.text_font_style_combo.count() > 0
        assert window.text_geometry_combo.count() == 2
        assert window.text_widget.isHidden()
    finally:
        window.close()
