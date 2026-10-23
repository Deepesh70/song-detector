"""UI styling and design tokens for Song Detector desktop application."""

DARK_THEME_QSS = """
QMainWindow {
    background-color: #111114;
}
QWidget {
    color: #f3f4f6;
    font-family: 'Segoe UI', 'SF Pro Display', -apple-system, sans-serif;
    font-size: 13px;
}
QLabel {
    background: transparent;
    border: none;
    padding: 0px;
    margin: 0px;
}
QFrame#Sidebar {
    background-color: #16161a;
    border-right: 1px solid #24242c;
}
QPushButton {
    background-color: #202028;
    color: #f3f4f6;
    border: 1px solid #2e2e38;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 500;
}
QPushButton:hover {
    background-color: #282832;
    border-color: #3b3b48;
}
QPushButton:pressed {
    background-color: #1a1a22;
}
QPushButton:focus {
    border-color: #10b981;
    outline: none;
}
QPushButton#PrimaryButton {
    background-color: #10b981;
    color: #ffffff;
    border: 1px solid #059669;
    font-weight: 600;
}
QPushButton#PrimaryButton:hover {
    background-color: #059669;
}
QPushButton#NavButton {
    background-color: transparent;
    border: none;
    border-radius: 6px;
    text-align: left;
    padding: 10px 14px;
    font-size: 13px;
    color: #9ca3af;
}
QPushButton#NavButton:hover {
    background-color: #202028;
    color: #f3f4f6;
}
QPushButton#NavButton:checked {
    background-color: #242430;
    color: #10b981;
    font-weight: 600;
}
QLineEdit, QComboBox {
    background-color: #18181e;
    border: 1px solid #2e2e38;
    border-radius: 6px;
    padding: 6px 12px;
    min-height: 26px;
    color: #f3f4f6;
    selection-background-color: #10b981;
}
QLineEdit:focus, QComboBox:focus {
    border-color: #10b981;
}
QTableWidget {
    background-color: #16161a;
    alternate-background-color: #1a1a20;
    border: 1px solid #24242c;
    border-radius: 6px;
    gridline-color: transparent;
    color: #f3f4f6;
    outline: none;
}
QTableWidget::item {
    padding: 10px 12px;
    border-bottom: 1px solid #1f1f26;
}
QTableWidget::item:selected {
    background-color: #142a22;
    color: #10b981;
    font-weight: 500;
}
QTableWidget::item:hover {
    background-color: #1e1e26;
}
QHeaderView::section {
    background-color: #18181e;
    color: #9ca3af;
    padding: 10px 12px;
    border: none;
    border-bottom: 1px solid #24242c;
    font-weight: 600;
    font-size: 12px;
}
"""
