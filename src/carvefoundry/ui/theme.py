from __future__ import annotations

# CarveFoundry deliberately shares the visual language of Bi-Weekly Bills while
# adapting it to a CAD/CAM workspace and Office-style ribbon.
APP_STYLESHEET = r"""
QWidget {
    background: #0b1020;
    color: #edf1f7;
    font-family: Inter, "Noto Sans", "DejaVu Sans", sans-serif;
    font-size: 13px;
}
QMainWindow, #AppRoot { background: #0b1020; }
#TitleBar, #RibbonTabBar {
    background: #0e1425;
    border-bottom: 1px solid #232b3e;
}
#AppName { color: #ffffff; font-size: 18px; font-weight: 700; }
#AppAccent { color: #c8ff3d; font-size: 18px; font-weight: 800; }
QTabWidget#Ribbon::pane {
    background: #0e1425;
    border: 0;
    border-bottom: 1px solid #232b3e;
}
QTabWidget#Ribbon QTabBar::tab {
    background: transparent;
    color: #9aa4b8;
    border: 0;
    padding: 8px 16px;
    min-width: 56px;
    font-weight: 600;
}
QTabWidget#Ribbon QTabBar::tab:hover { color: #ffffff; background: #171e31; }
QTabWidget#Ribbon QTabBar::tab:selected {
    color: #c8ff3d;
    border-bottom: 2px solid #c8ff3d;
}
#RibbonPage { background: #0e1425; }
#RibbonGroup {
    background: #12192a;
    border: 1px solid #242e44;
    border-radius: 10px;
}
#RibbonGroupTitle {
    color: #c8ff3d;
    font-size: 10px;
    font-weight: 700;
    border-radius: 5px;
    padding: 1px 5px;
}
#RibbonGroupTitle:hover {
    background: #171e31;
}
#RibbonSelector {
    background: transparent;
}
#RibbonSelectorTitle {
    color: #aeb8ca;
    font-size: 10px;
    font-weight: 700;
}
QComboBox#RibbonCombo {
    background: #0f1626;
    color: #edf1f7;
    border: 1px solid #35415a;
    border-radius: 5px;
    padding: 4px 7px;
    min-height: 24px;
}
QComboBox#RibbonCombo:hover {
    border-color: #c8ff3d;
}
QComboBox#RibbonCombo::drop-down {
    border: 0;
    width: 18px;
}
QToolButton#RibbonButton, QToolButton#RibbonPrimary {
    background: transparent;
    color: #edf1f7;
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 6px 9px;
    min-width: 54px;
}
QToolButton#RibbonPrimary { font-weight: 800; }
QToolButton#RibbonButton:checked, QToolButton#RibbonPrimary:checked {
    background: #202a40;
    color: #edf1f7;
    border-color: #3a465f;
}
QToolButton#RibbonButton:hover, QToolButton#RibbonPrimary:hover {
    background: #c8ff3d;
    color: #0b1020;
    border-color: #c8ff3d;
}
QToolButton#RibbonButton:pressed, QToolButton#RibbonPrimary:pressed {
    background: #9fcf2f;
    color: #07100b;
    border-color: #9fcf2f;
}
QToolButton#RibbonButton:disabled, QToolButton#RibbonPrimary:disabled {
    background: transparent;
    color: #586276;
    border-color: transparent;
}
#WorkspacePanel {
    background: #0e1425;
    border: 1px solid #232b3e;
    border-radius: 12px;
}
#PanelHeader {
    background: #12192a;
    border-bottom: 1px solid #242e44;
    color: #ffffff;
    font-size: 13px;
    font-weight: 700;
}
#CanvasFrame {
    background: #111827;
    border: 1px solid #242e44;
    border-radius: 14px;
}
#ViewportBar {
    background: #12192a;
    border-bottom: 1px solid #242e44;
}
#MeshViewport, #ViewportShell { background: #111827; }
#ViewportRuler {
    background: #0e1425;
    color: #c7d0e0;
    font-size: 10px;
}
#BackplotRoot, #BackplotCanvas { background: #111827; }
#BackplotTopBar, #BackplotTransport {
    background: #0e1425;
    border-bottom: 1px solid #242e44;
}
#BackplotTransport {
    border-top: 1px solid #242e44;
    border-bottom: 0;
}
#BackplotSidebar {
    background: #0e1425;
    border-right: 1px solid #242e44;
}
#BackplotSectionHeader {
    background: #12192a;
    color: #dce4f0;
    border: 1px solid #242e44;
    border-radius: 5px;
    padding: 5px 7px;
    font-weight: 700;
}
QPlainTextEdit#BackplotCode {
    background: #f7f8fa;
    color: #1a2230;
    border: 1px solid #2a3550;
    border-radius: 5px;
    selection-background-color: #d9e8ba;
    selection-color: #111827;
    padding: 3px;
}
#BackplotDRO {
    background: #0a0f1c;
    color: #c8ff3d;
    border: 1px solid #2a3550;
    border-radius: 4px;
    padding: 6px;
    font-family: monospace;
    font-size: 16px;
    font-weight: 700;
}
#BackplotTransport QToolButton {
    background: #20283a;
    color: #ffffff;
    border: 1px solid #35415a;
    border-radius: 5px;
    min-width: 34px;
    min-height: 28px;
}
#BackplotTransport QToolButton:hover {
    background: #c8ff3d;
    color: #0b1020;
    border-color: #c8ff3d;
}
#SectionHeading { color: #ffffff; font-weight: 700; padding-top: 4px; }
#TransformControls { border-top: 1px solid #242e44; }
#CanvasHint { color: #7f8aa0; font-size: 13px; }
#CanvasTitle { color: #ffffff; font-size: 22px; font-weight: 700; }
#AccentText { color: #c8ff3d; font-weight: 700; }
#Muted { color: #7f8aa0; }
QListWidget, QTreeWidget {
    background: #0f1626;
    border: 0;
    outline: 0;
}
QListWidget::item, QTreeWidget::item { padding: 6px; }
QListWidget::item:selected, QTreeWidget::item:selected {
    background: #232d43;
    color: #ffffff;
}
QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox {
    background: #0f1626;
    color: #edf1f7;
    border: 1px solid #2a3550;
    border-radius: 8px;
    padding: 6px 8px;
}
QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus {
    border-color: #c8ff3d;
}
QCheckBox { color: #cbd3e0; spacing: 7px; }
QCheckBox::indicator {
    width: 15px;
    height: 15px;
    border: 1px solid #3a465f;
    border-radius: 4px;
    background: #0f1626;
}
QCheckBox::indicator:checked {
    background: #c8ff3d;
    border-color: #c8ff3d;
}
QPushButton {
    background: #171e31;
    color: #edf1f7;
    border: 1px solid #29324a;
    border-radius: 8px;
    padding: 7px 10px;
    font-weight: 600;
}
QPushButton#PrimaryButton { font-weight: 800; }
QPushButton:hover {
    background: #c8ff3d;
    color: #0b1020;
    border-color: #c8ff3d;
}
QPushButton:pressed {
    background: #9fcf2f;
    color: #07100b;
    border-color: #9fcf2f;
}
QPushButton:disabled {
    background: #12192a;
    color: #586276;
    border-color: #20283a;
}
QSplitter::handle { background: #1c2436; width: 2px; height: 2px; }
QProgressBar#ImportProgress {
    background: #0f1626;
    border: 1px solid #2a3550;
    border-radius: 5px;
    min-height: 10px;
    max-height: 10px;
}
QProgressBar#ImportProgress::chunk {
    background: #c8ff3d;
    border-radius: 4px;
}
QStatusBar { background: #0e1425; color: #8792a8; border-top: 1px solid #1c2436; }
"""
