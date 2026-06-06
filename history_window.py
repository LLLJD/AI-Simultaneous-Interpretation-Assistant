# history_window.py
import logging

from PyQt5.QtWidgets import (QWidget, QLabel, QVBoxLayout, QHBoxLayout,
                             QPushButton, QTextEdit)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

logger = logging.getLogger(__name__)

class HistoryWindow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.setGeometry(300, 400, 800, 300)
        self.setMinimumSize(400, 150)

        # 调整大小相关
        self.resize_edge = None
        self.resize_start_pos = None
        self.resize_start_geometry = None
        self.edge_threshold = 8

        self.container = QWidget()
        self.container.setStyleSheet("""
            QWidget {
                background-color: rgba(0, 0, 0, 200);
                border-radius: 15px;
            }
        """)

        # 标题栏
        title_bar = QWidget()
        title_bar_layout = QHBoxLayout()
        title_bar_layout.setContentsMargins(10, 5, 10, 5)

        title_label = QLabel("历史记录")
        title_label.setStyleSheet("color: white; font-size: 14px; background: transparent;")
        title_bar_layout.addWidget(title_label)
        title_bar_layout.addStretch()

        self.clear_btn = QPushButton("清空")
        self.clear_btn.setFixedSize(40, 25)
        self.clear_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 50);
                color: white;
                border: none;
                border-radius: 5px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: rgba(255, 100, 100, 150);
            }
        """)
        self.clear_btn.clicked.connect(self.clear_history)

        self.close_btn = QPushButton("×")
        self.close_btn.setFixedSize(30, 25)
        self.close_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 80, 80, 150);
                color: white;
                border: none;
                border-radius: 5px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(255, 0, 0, 200);
            }
        """)
        self.close_btn.clicked.connect(self.hide)

        title_bar_layout.addWidget(self.clear_btn)
        title_bar_layout.addWidget(self.close_btn)
        title_bar.setLayout(title_bar_layout)
        title_bar.setStyleSheet("background: transparent;")

        # 文本区域
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setStyleSheet("""
            QTextEdit {
                background-color: transparent;
                color: white;
                font-size: 16px;
                border: none;
                padding: 15px;
            }
        """)
        self.text_edit.setFont(QFont("Microsoft YaHei", 14))
        self.text_edit.setWordWrapMode(True)
        self.text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.text_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(title_bar)
        main_layout.addWidget(self.text_edit)
        self.container.setLayout(main_layout)

        outer_layout = QVBoxLayout()
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(self.container)
        self.setLayout(outer_layout)

        # 拖拽移动
        self.dragging = False
        self.drag_position = None
        title_bar.mousePressEvent = self.title_mousePressEvent
        title_bar.mouseMoveEvent = self.title_mouseMoveEvent
        title_bar.mouseReleaseEvent = self.title_mouseReleaseEvent

        self.hide()

    # ---------- 窗口调整大小 ----------
    def get_resize_edge(self, pos):
        x, y = pos.x(), pos.y()
        w, h = self.width(), self.height()
        left = x <= self.edge_threshold
        right = x >= w - self.edge_threshold
        top = y <= self.edge_threshold
        bottom = y >= h - self.edge_threshold
        if left and top:
            return "top-left"
        if right and top:
            return "top-right"
        if left and bottom:
            return "bottom-left"
        if right and bottom:
            return "bottom-right"
        if left:
            return "left"
        if right:
            return "right"
        if top:
            return "top"
        if bottom:
            return "bottom"
        return None

    def set_cursor_shape(self, edge):
        if edge in ("top-left", "bottom-right"):
            self.setCursor(Qt.SizeFDiagCursor)
        elif edge in ("top-right", "bottom-left"):
            self.setCursor(Qt.SizeBDiagCursor)
        elif edge in ("left", "right"):
            self.setCursor(Qt.SizeHorCursor)
        elif edge in ("top", "bottom"):
            self.setCursor(Qt.SizeVerCursor)
        else:
            self.setCursor(Qt.ArrowCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            edge = self.get_resize_edge(event.pos())
            if edge:
                self.resize_edge = edge
                self.resize_start_pos = event.globalPos()
                self.resize_start_geometry = self.geometry()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.resize_edge and event.buttons() == Qt.LeftButton:
            self.perform_resize(event.globalPos())
            event.accept()
            return
        if not self.resize_edge:
            edge = self.get_resize_edge(event.pos())
            self.set_cursor_shape(edge)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.resize_edge = None
            event.accept()
        super().mouseReleaseEvent(event)

    def perform_resize(self, global_pos):
        if not self.resize_edge or not self.resize_start_geometry or not self.resize_start_pos:
            return
        delta = global_pos - self.resize_start_pos
        x, y, w, h = self.resize_start_geometry.getRect()
        min_w, min_h = self.minimumWidth(), self.minimumHeight()
        if self.resize_edge == "right":
            new_w = max(min_w, w + delta.x())
            self.setGeometry(x, y, new_w, h)
        elif self.resize_edge == "bottom":
            new_h = max(min_h, h + delta.y())
            self.setGeometry(x, y, w, new_h)
        elif self.resize_edge == "left":
            new_w = max(min_w, w - delta.x())
            new_x = x + (w - new_w)
            self.setGeometry(new_x, y, new_w, h)
        elif self.resize_edge == "top":
            new_h = max(min_h, h - delta.y())
            new_y = y + (h - new_h)
            self.setGeometry(x, new_y, w, new_h)
        elif self.resize_edge == "bottom-right":
            new_w = max(min_w, w + delta.x())
            new_h = max(min_h, h + delta.y())
            self.setGeometry(x, y, new_w, new_h)
        elif self.resize_edge == "bottom-left":
            new_w = max(min_w, w - delta.x())
            new_h = max(min_h, h + delta.y())
            new_x = x + (w - new_w)
            self.setGeometry(new_x, y, new_w, new_h)
        elif self.resize_edge == "top-right":
            new_w = max(min_w, w + delta.x())
            new_h = max(min_h, h - delta.y())
            new_y = y + (h - new_h)
            self.setGeometry(x, new_y, new_w, new_h)
        elif self.resize_edge == "top-left":
            new_w = max(min_w, w - delta.x())
            new_h = max(min_h, h - delta.y())
            new_x = x + (w - new_w)
            new_y = y + (h - new_h)
            self.setGeometry(new_x, new_y, new_w, new_h)

    def title_mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def title_mouseMoveEvent(self, event):
        if self.dragging and event.buttons() == Qt.LeftButton:
            self.move(event.globalPos() - self.drag_position)
            event.accept()

    def title_mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = False
            event.accept()

    def append_text(self, text):
        if not text.strip():
            return
        self.text_edit.append(text)
        cursor = self.text_edit.textCursor()
        cursor.movePosition(cursor.End)
        self.text_edit.setTextCursor(cursor)

    def clear_history(self):
        self.text_edit.clear()
        logger.info("历史记录已清空")

    def closeEvent(self, event):
        self.hide()
        event.ignore()