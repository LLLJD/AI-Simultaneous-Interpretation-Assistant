# history_window.py
import logging
import markdown

from PyQt5.QtWidgets import (QWidget, QLabel, QVBoxLayout, QHBoxLayout,
                             QPushButton, QTextEdit)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont

logger = logging.getLogger(__name__)

class HistoryWindow(QWidget):
    # 信号：请求 AI 总结
    summarize_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.setGeometry(300, 400, 800, 300)
        self.setMinimumSize(400, 150)

        # 临时翻译追踪：{sentence_id: (original, translated)}
        self._temp_translations = {}

        # 总结进行中标记
        self._summarizing = False

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

        # 总结按钮
        self.summarize_btn = QPushButton("🤖 总结")
        self.summarize_btn.setFixedSize(70, 25)
        self.summarize_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(156, 39, 176, 150);
                color: white;
                border: none;
                border-radius: 5px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: rgba(156, 39, 176, 220);
            }
            QPushButton:disabled {
                background-color: rgba(128, 128, 128, 80);
            }
        """)
        self.summarize_btn.clicked.connect(self._on_summarize_clicked)

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

        title_bar_layout.addWidget(self.summarize_btn)
        title_bar_layout.addWidget(self.clear_btn)
        title_bar_layout.addWidget(self.close_btn)
        title_bar.setLayout(title_bar_layout)
        title_bar.setStyleSheet("background: transparent;")

        # 文本区域 - 使用 QTextEdit 的 HTML 模式支持颜色
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

        # 支持原文和译文的颜色区分
        if "🔊" in text and "📝" in text:
            # 分离原文和译文
            parts = text.split("\n")
            for part in parts:
                if part.startswith("🔊"):
                    self.text_edit.append(
                        f'<span style="color: white; font-weight: bold;">{part}</span>'
                    )
                elif part.startswith("📝"):
                    self.text_edit.append(f'<span style="color: #FFD700;">{part}</span><br>')
        else:
            self.text_edit.append(text)
        cursor = self.text_edit.textCursor()
        cursor.movePosition(cursor.End)
        self.text_edit.setTextCursor(cursor)

    def update_temp_translation(self, sentence_id, original, translated):
        """更新或添加临时翻译条目（灰色显示）。
        当最终译文到达时，append_text 会追加最终版本，
        临时版本保留在历史中作为参考。
        """
        self._temp_translations[sentence_id] = (original, translated)

    def clear_history(self):
        self.text_edit.clear()
        self._temp_translations.clear()
        logger.info("历史记录已清空")

    def _on_summarize_clicked(self):
        """用户点击总结按钮"""
        if self._summarizing:
            return
        # 检查是否有历史内容
        if not self.text_edit.toPlainText().strip():
            return
        self._summarizing = True
        self.summarize_btn.setEnabled(False)
        self.summarize_btn.setText("⏳ 总结中...")
        self.summarize_requested.emit()

    def set_summarize_enabled(self, enabled: bool):
        """外部控制总结按钮是否可用"""
        self._summarizing = not enabled
        self.summarize_btn.setEnabled(enabled)
        if enabled:
            self.summarize_btn.setText("🤖 总结")
        else:
            self.summarize_btn.setText("⏳ 总结中...")

    def get_history_texts(self):
        """获取历史记录中的原文和译文（分开返回，用于 AI 总结）"""
        plain_text = self.text_edit.toPlainText()
        original_lines = []
        translated_lines = []

        for line in plain_text.split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.startswith("🔊"):
                original_lines.append(line[1:].strip())
            elif line.startswith("📝"):
                translated_lines.append(line[1:].strip())

        return "\n".join(original_lines), "\n".join(translated_lines)

    def display_summary(self, markdown_text: str):
        """在历史窗口中显示 Markdown 格式的总结报告"""
        try:
            # 将 Markdown 转换为 HTML
            html_body = markdown.markdown(
                markdown_text,
                extensions=["extra", "codehilite", "tables", "fenced_code"]
            )
        except Exception:
            # 如果 markdown 转换失败，使用纯文本
            html_body = markdown_text.replace("\n", "<br>")

        # 构建完整的 HTML，带样式
        styled_html = f"""
        <div style="
            background-color: rgba(156, 39, 176, 30);
            border: 1px solid rgba(156, 39, 176, 100);
            border-radius: 10px;
            padding: 15px;
            margin: 10px 0;
        ">
            <h2 style="color: #CE93D8; margin-top: 0; font-size: 18px;">
                🤖 AI 总结报告
            </h2>
            <div style="color: #E1BEE7; font-size: 14px; line-height: 1.6;">
                {html_body}
            </div>
        </div>
        """

        # 追加到历史窗口
        self.text_edit.append(styled_html)
        cursor = self.text_edit.textCursor()
        cursor.movePosition(cursor.End)
        self.text_edit.setTextCursor(cursor)

        self._summarizing = False
        self.summarize_btn.setEnabled(True)
        self.summarize_btn.setText("🤖 总结")
        logger.info("AI 总结已显示在历史窗口")

    def closeEvent(self, event):
        self.hide()
        event.ignore()