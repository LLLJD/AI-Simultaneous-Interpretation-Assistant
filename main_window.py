# main_window.py
import logging
import os
from datetime import datetime

from PyQt5.QtWidgets import (QWidget, QLabel, QVBoxLayout, QHBoxLayout,
                             QPushButton, QTextEdit, QMenu, QSystemTrayIcon,
                             QAction)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QCursor

from voice_recognition import SpeechRecognitionThread
from history_window import HistoryWindow
from settings_dialog import AudioSettingsDialog

logger = logging.getLogger(__name__)

# 输出目录
OUTPUT_DIR = "output"

class FloatingCaption(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.setGeometry(300, 300, 900, 400)
        self.setMinimumSize(300, 120)

        # 调整大小相关
        self.resize_edge = None
        self.resize_start_pos = None
        self.resize_start_geometry = None
        self.edge_threshold = 8

        # 主容器
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

        title_label = QLabel("AI同声传译助手")
        title_label.setStyleSheet("color: white; font-size: 14px; background: transparent;")

        self.settings_btn = QPushButton("⚙ 设置")
        self.settings_btn.setFixedSize(60, 25)
        self.settings_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(100, 200, 100, 100);
                color: white;
                border: none;
                border-radius: 5px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: rgba(100, 200, 100, 200);
            }
        """)
        self.settings_btn.clicked.connect(self.open_settings_dialog)

        self.history_btn = QPushButton("📜 历史")
        self.history_btn.setFixedSize(60, 25)
        self.history_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(100, 100, 255, 100);
                color: white;
                border: none;
                border-radius: 5px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: rgba(100, 100, 255, 200);
            }
        """)
        self.history_btn.clicked.connect(self.toggle_history_window)

        title_bar_layout.addWidget(title_label)
        title_bar_layout.addStretch()
        title_bar_layout.addWidget(self.settings_btn)
        title_bar_layout.addWidget(self.history_btn)

        self.min_btn = QPushButton("－")
        self.min_btn.setFixedSize(30, 25)
        self.min_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 50);
                color: white;
                border: none;
                border-radius: 5px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 100);
            }
        """)
        self.min_btn.clicked.connect(self.showMinimized)

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
        self.close_btn.clicked.connect(self.quit_app)

        title_bar_layout.addWidget(self.min_btn)
        title_bar_layout.addWidget(self.close_btn)
        title_bar.setLayout(title_bar_layout)
        title_bar.setStyleSheet("background: transparent;")

        # 内容区域 - 原文显示
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setStyleSheet("""
            QTextEdit {
                background-color: transparent;
                color: white;
                font-size: 20px;
                font-weight: bold;
                border: none;
                padding: 15px 15px 5px 15px;
            }
        """)
        self.text_edit.setFont(QFont("Microsoft YaHei", 16, QFont.Bold))
        self.text_edit.setWordWrapMode(True)
        self.text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.text_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # 翻译结果显示区域（支持 HTML 渲染，显示多行翻译历史）
        self.translation_edit = QTextEdit()
        self.translation_edit.setReadOnly(True)
        self.translation_edit.setStyleSheet("""
            QTextEdit {
                background-color: transparent;
                color: #FFD700;
                font-size: 18px;
                font-weight: bold;
                border: none;
                padding: 5px 15px 15px 15px;
            }
        """)
        self.translation_edit.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        self.translation_edit.setWordWrapMode(True)
        self.translation_edit.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.translation_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.translation_edit.setMaximumHeight(80)
        self.translation_edit.setPlaceholderText("等待翻译结果...")

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(title_bar)
        main_layout.addWidget(self.text_edit)
        main_layout.addWidget(self.translation_edit)
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

        # 系统托盘
        self.create_tray_icon()

        # 创建本次运行的结果输出文件（日期-时间命名，精确到秒）
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        self._output_filename = os.path.join(
            OUTPUT_DIR,
            f"{datetime.now().strftime('%Y%m%d-%H%M%S')}.txt"
        )
        logger.info(f"本次识别结果将保存至: {self._output_filename}")

        # 历史窗口
        self.history_window = HistoryWindow(self)

        # 启动语音识别线程
        self.recognition_thread = SpeechRecognitionThread()
        self.recognition_thread.text_updated.connect(self.update_caption)
        self.recognition_thread.final_text.connect(self.on_final_text)
        self.recognition_thread.translation_ready.connect(self.on_translation_ready)
        self.recognition_thread.start()

        self.show()

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

    # ---------- 系统托盘 ----------
    def create_tray_icon(self):
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(self.style().standardIcon(0))
        tray_menu = QMenu()
        show_action = QAction("显示窗口", self)
        show_action.triggered.connect(self.show_window)
        quit_action = QAction("退出程序", self)
        quit_action.triggered.connect(self.quit_app)
        tray_menu.addAction(show_action)
        tray_menu.addSeparator()
        tray_menu.addAction(quit_action)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.on_tray_activated)
        self.tray_icon.show()

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_window()

    def show_window(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def quit_app(self):
        if hasattr(self, 'recognition_thread'):
            self.recognition_thread.stop()
        if hasattr(self, 'tray_icon'):
            self.tray_icon.hide()
        if hasattr(self, 'history_window'):
            self.history_window.close()
        from PyQt5.QtWidgets import QApplication
        QApplication.quit()

    # ---------- 字幕更新 ----------
    def update_caption(self, text):
        """更新原文显示"""
        self.text_edit.setPlainText(text)
        cursor = self.text_edit.textCursor()
        cursor.movePosition(cursor.End)
        self.text_edit.setTextCursor(cursor)

    def on_final_text(self, sentence):
        """保存最终识别结果到文件"""
        with open(self._output_filename, "a", encoding="utf-8") as f:
            f.write(f"{sentence}\n")
        logger.info(f"保存最终句子: {sentence}")

    def on_translation_ready(self, sentence_id, original, translated, is_final):
        """翻译完成，只显示当前最新译文，历史记录留在历史窗口中。
        - 中间译文（is_final=False）：灰色显示
        - 最终译文（is_final=True）：金色显示
        """
        if is_final:
            # 最终译文：金色
            self.translation_edit.setHtml(
                f'<span style="color: #FFD700; font-size: 18px; font-weight: bold;">📝 {translated}</span>'
            )
            # 保存到本次运行的文件
            with open(self._output_filename, "a", encoding="utf-8") as f:
                f.write(f"  → {translated}\n")
            logger.info(f"译文: {translated}")
            # 追加到历史窗口
            if hasattr(self, 'history_window'):
                self.history_window.append_text(
                    f"🔊 {original}\n📝 {translated}"
                )
        else:
            # 中间译文：灰色显示
            self.translation_edit.setHtml(
                f'<span style="color: #888888; font-size: 18px;">📝 {translated}</span>'
            )

    def open_settings_dialog(self):
        """打开音频来源设置对话框"""
        dialog = AudioSettingsDialog(self)
        dialog.audio_source_changed.connect(self.on_audio_source_changed)
        dialog.exec_()

    def on_audio_source_changed(self, selection):
        """音频来源切换回调"""
        if selection is None:
            return
        logger.info(f"音频来源切换: {selection}")
        # 通知语音识别线程切换设备
        if hasattr(self, 'recognition_thread'):
            self.recognition_thread.switch_audio_source(selection)

    def toggle_history_window(self):
        if self.history_window.isVisible():
            self.history_window.hide()
        else:
            self.history_window.show()
            self.history_window.raise_()
            self.history_window.activateWindow()

    def closeEvent(self, event):
        self.quit_app()