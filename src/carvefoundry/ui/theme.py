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
#RibbonGroupTitle { color: #7f8aa0; font-size: 10px; font-weight: 700; }
QToolButton#RibbonButton {
    background: transparent;
    color: #edf1f7;
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 6px 9px;
    min-width: 54px;
}
QToolButton#RibbonButton:hover { background: #171e31; border-color: #29324a; }
QToolButton#RibbonButton:pressed { background: #202a40; }
QToolButton#RibbonPrimary {
    background: #c8ff3d;
    color: #0b1020;
    border: 0;
    border-radius: 9px;
    padding: 7px 11px;
    font-weight: 800;
}
QToolButton#RibbonPrimary:hover { background: #d5ff68; }
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
QPushButton {
    background: #171e31;
    color: #edf1f7;
    border: 1px solid #29324a;
    border-radius: 8px;
    padding: 7px 10px;
    font-weight: 600;
}
QPushButton:hover { background: #202a40; border-color: #3a465f; }
QPushButton#PrimaryButton { background: #c8ff3d; color: #0b1020; border: 0; }
QSplitter::handle { background: #1c2436; width: 2px; height: 2px; }
QStatusBar { background: #0e1425; color: #8792a8; border-top: 1px solid #1c2436; }
"""
