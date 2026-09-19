from __future__ import annotations

# CarveFoundry deliberately shares the visual language of Bi-Weekly Bills while
# adapting it to a CAD/CAM workspace and Office-style ribbon.
APP_STYLESHEET = r"""
QWidget {
    background: #0b1020;
    color: #edf1f7;
    font-family: Inter, "Noto Sans", "DejaVu Sans", sans-serif;
    font-size: 12px;
}
QMainWindow, #AppRoot { background: #0b1020; }
#TitleBar, #RibbonTabBar {
    background: #0e1425;
    border-bottom: 1px solid #232b3e;
}
#AppName { color: #ffffff; font-size: 16px; font-weight: 700; }
#AppAccent { color: #c8ff3d; font-size: 16px; font-weight: 800; }
#MachineStatus {
    background: #151b2a;
    color: #8f9aae;
    border: 1px solid #303a50;
    border-radius: 8px;
    padding: 4px 8px;
    font-size: 10px;
    font-weight: 800;
}
#MachineStatus[connected="true"] {
    background: #152516;
    color: #c8ff3d;
    border-color: #5b7a2a;
}
QPushButton#TitleQuickButton {
    background: transparent;
    color: #aeb8ca;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 4px 7px;
    font-size: 11px;
    font-weight: 700;
}
QPushButton#TitleQuickButton:hover {
    background: #202a40;
    color: #c8ff3d;
    border-color: #35415a;
}
QTabWidget#Ribbon::pane {
    background: #0e1425;
    border: 0;
    border-bottom: 1px solid #232b3e;
}
QTabWidget#Ribbon QTabBar::tab {
    background: transparent;
    color: #9aa4b8;
    border: 0;
    padding: 6px 12px;
    min-width: 48px;
    font-weight: 600;
}
QTabWidget#Ribbon QTabBar::tab:hover { color: #ffffff; background: #171e31; }
QTabWidget#Ribbon QTabBar::tab:selected {
    color: #c8ff3d;
    border-bottom: 2px solid #c8ff3d;
}
#RibbonPage, #RibbonPageContent, #RibbonScrollArea {
    background: #0e1425;
}
QScrollArea#RibbonScrollArea {
    border: 0;
}
QScrollArea#RibbonScrollArea QScrollBar:horizontal {
    background: #0e1425;
    height: 7px;
    margin: 0 8px;
}
QScrollArea#RibbonScrollArea QScrollBar::handle:horizontal {
    background: #35415a;
    border-radius: 3px;
    min-width: 36px;
}
QScrollArea#RibbonScrollArea QScrollBar::handle:horizontal:hover {
    background: #c8ff3d;
}
QScrollArea#RibbonScrollArea QScrollBar::add-line:horizontal,
QScrollArea#RibbonScrollArea QScrollBar::sub-line:horizontal {
    width: 0;
}
#RibbonGroup {
    background: #12192a;
    border: 1px solid #242e44;
    border-radius: 6px;
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
QComboBox#RibbonCombo:disabled {
    background: #111725;
    color: #596477;
    border-color: #222b3d;
}
#RibbonSelector:disabled #RibbonSelectorTitle,
#RibbonSlider:disabled #RibbonSelectorTitle,
#RibbonSlider:disabled #RibbonSliderEnd,
#RibbonSlider:disabled #RibbonSliderReadout {
    color: #566176;
}
QSlider#RibbonDetailSlider:disabled::groove:horizontal {
    background: #1c2434;
}
QSlider#RibbonDetailSlider:disabled::sub-page:horizontal {
    background: #566176;
}
QSlider#RibbonDetailSlider:disabled::handle:horizontal {
    background: #697386;
    border-color: #525d71;
}
QComboBox#RibbonCombo::drop-down {
    border: 0;
    width: 18px;
}
#RibbonSlider {
    background: transparent;
}
#RibbonSliderEnd {
    color: #7f8aa0;
    font-size: 9px;
}
#RibbonSliderReadout {
    color: #d7dfeb;
    font-size: 9px;
}
QSlider#RibbonDetailSlider::groove:horizontal {
    height: 4px;
    background: #2b354b;
    border-radius: 2px;
}
QSlider#RibbonDetailSlider::sub-page:horizontal {
    background: #c8ff3d;
    border-radius: 2px;
}
QSlider#RibbonDetailSlider::handle:horizontal {
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
    background: #edf1f7;
    border: 1px solid #68748b;
}
QSlider#RibbonDetailSlider::handle:horizontal:hover {
    background: #c8ff3d;
    border-color: #c8ff3d;
}
QToolButton#RibbonButton, QToolButton#RibbonPrimary {
    background: transparent;
    color: #edf1f7;
    border: 1px solid transparent;
    border-radius: 5px;
    padding: 4px 6px;
    min-width: 40px;
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
QMenuBar#MainMenuBar {
    background: #111827;
    color: #e7ecf4;
    border-top: 1px solid #20283a;
    border-bottom: 1px solid #273149;
    spacing: 1px;
    padding: 1px 6px;
}
QMenuBar#MainMenuBar::item {
    background: transparent;
    padding: 4px 9px;
    border-radius: 4px;
}
QMenuBar#MainMenuBar::item:selected,
QMenuBar#MainMenuBar::item:pressed {
    background: #263149;
    color: #c8ff3d;
}
QMenuBar#MainMenuBar QMenu {
    background: #111827;
    color: #edf1f7;
    border: 1px solid #35415a;
    padding: 4px;
}
QMenuBar#MainMenuBar QMenu::item {
    padding: 6px 26px 6px 10px;
    border-radius: 4px;
}
QMenuBar#MainMenuBar QMenu::item:selected {
    background: #c8ff3d;
    color: #0b1020;
}
QMenuBar#MainMenuBar QMenu::separator {
    height: 1px;
    background: #2b354d;
    margin: 4px 7px;
}
#ToolRailMenuWidget {
    background: #111827;
}
#ToolRailMenuLabel {
    color: #9da8ba;
    font-size: 11px;
    font-weight: 700;
}
#ToolRail {
    background: #0e1425;
    border: 1px solid #232b3e;
    border-radius: 5px;
}
QScrollArea#ToolRailScroll, QWidget#ToolRailContent {
    background: #0e1425;
    border: 0;
}
QToolButton#ToolRailButton {
    background: transparent;
    color: #dbe3ef;
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 4px;
}
QToolButton#ToolRailButton:hover {
    background: #202a40;
    color: #c8ff3d;
    border-color: #35415a;
}
QToolButton#ToolRailButton:checked {
    background: #27324a;
    color: #c8ff3d;
    border-color: #c8ff3d;
}
QToolButton#ToolRailButton:pressed {
    background: #c8ff3d;
    color: #0b1020;
    border-color: #c8ff3d;
}
QToolButton#ToolRailButton::menu-indicator {
    image: none;
    width: 7px;
    height: 7px;
    subcontrol-origin: padding;
    subcontrol-position: bottom right;
    border-right: 1px solid #8f9aae;
    border-bottom: 1px solid #8f9aae;
}
#ToolRailSeparator {
    color: #273149;
    background: transparent;
    margin: 2px 4px;
}
QMenu#ToolRailMenu {
    background: #111827;
    color: #edf1f7;
    border: 1px solid #35415a;
    padding: 4px;
}
QMenu#ToolRailMenu::item {
    padding: 6px 24px 6px 8px;
    border-radius: 4px;
}
QMenu#ToolRailMenu::item:selected {
    background: #c8ff3d;
    color: #0b1020;
}
#WorkspacePanel, #InspectorPanel {
    background: #0e1425;
    border: 1px solid #232b3e;
    border-radius: 6px;
}
#InspectorSummary {
    background: #0f1626;
    color: #b9c4d6;
    border: 1px solid #242e44;
    border-radius: 8px;
    padding: 8px;
}
#ActivitySummary {
    background: #111827;
    color: #aeb8ca;
    border-left: 3px solid #35415a;
    border-radius: 4px;
    padding: 7px 8px;
}
#TextSubheading {
    color: #c8ff3d;
    font-size: 11px;
    font-weight: 800;
    padding-top: 6px;
    border-bottom: 1px solid #273149;
}
#TextFontWarning {
    background: #2a2112;
    color: #ffd166;
    border: 1px solid #8a6726;
    border-radius: 6px;
    padding: 6px 7px;
}
#TextCncHint {
    background: #101827;
    color: #9fb0c8;
    border-left: 3px solid #35415a;
    border-radius: 4px;
    padding: 6px 7px;
}
QScrollArea#InspectorScrollArea,
#InspectorBody {
    background: transparent;
    border: 0;
}
QScrollArea#InspectorScrollArea QScrollBar:vertical {
    background: #0e1425;
    width: 7px;
    margin: 8px 0;
}
QScrollArea#InspectorScrollArea QScrollBar::handle:vertical {
    background: #35415a;
    border-radius: 3px;
    min-height: 36px;
}
QScrollArea#InspectorScrollArea QScrollBar::handle:vertical:hover {
    background: #c8ff3d;
}
QScrollArea#InspectorScrollArea QScrollBar::add-line:vertical,
QScrollArea#InspectorScrollArea QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollArea#InspectorScrollArea QScrollBar::add-page:vertical,
QScrollArea#InspectorScrollArea QScrollBar::sub-page:vertical {
    background: transparent;
}
#LayersPopup {
    background: #0e1425;
    border: 1px solid #3a465f;
    border-radius: 10px;
}
#LayersPopupTitle {
    color: #ffffff;
    font-size: 14px;
    font-weight: 800;
}
QListWidget#LayersList {
    background: #0b1120;
    border: 1px solid #242e44;
    border-radius: 8px;
}
QComboBox#ObjectSelector {
    background: #0b1120;
    border-color: #35415a;
    padding-left: 9px;
}
QComboBox#ObjectSelector:hover {
    border-color: #c8ff3d;
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
#ViewportBar QLabel {
    background: transparent;
}
#ViewportBar QPushButton:checked {
    background: #202a40;
    color: #c8ff3d;
    border-color: #3a465f;
}
#ToolOptionsBar {
    background: #0f1626;
    border-bottom: 1px solid #2a3550;
}
#ToolOptionsBar QLabel {
    background: transparent;
}
#ToolOptionsTitle {
    color: #c8ff3d;
    font-weight: 800;
    padding-right: 8px;
}
#ToolMeasureResult {
    color: #c8ff3d;
    font-weight: 700;
}
#ToolFixtureSize {
    color: #c9d4e4;
}
#ToolOptionsValue {
    color: #dce4f0;
    padding: 4px 7px;
    border: 1px solid #2a3550;
    border-radius: 6px;
    background: #12192a;
}
QPushButton#ToolApplyButton {
    color: #c8ff3d;
    font-size: 16px;
    font-weight: 900;
    padding: 3px;
}
QPushButton#ToolCancelButton {
    color: #ff9b9b;
    font-size: 15px;
    font-weight: 900;
    padding: 3px;
}
QPushButton#ToolApplyButton:hover,
QPushButton#ToolCancelButton:hover {
    background: #c8ff3d;
    color: #0b1020;
    border-color: #c8ff3d;
}
#CamStatus {
    background: #151b2a;
    color: #8f9aae;
    border: 1px solid #303a50;
    border-radius: 8px;
    padding: 4px 8px;
    font-size: 10px;
    font-weight: 800;
}
#CamStatus[state="ready"] {
    background: #152516;
    color: #c8ff3d;
    border-color: #5b7a2a;
}
#CamStatus[state="stale"] {
    background: #2a2112;
    color: #ffd166;
    border-color: #8a6726;
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
