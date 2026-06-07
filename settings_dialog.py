# settings_dialog.py
import logging

import pyaudiowpatch as pyaudio
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QComboBox, QPushButton, QGroupBox, QRadioButton,
                             QButtonGroup, QMessageBox)
from PyQt5.QtCore import Qt, pyqtSignal

logger = logging.getLogger(__name__)


class AudioSettingsDialog(QDialog):
    """音频来源设置对话框"""

    # 信号：发射选中的设备信息 dict 或 None（使用默认 Loopback）
    audio_source_changed = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("音频来源设置")
        self.setFixedSize(500, 380)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        self.pyaudio_instance = None
        self.loopback_device = None
        self.input_devices = []
        self.current_selection = None  # None 表示使用默认 Loopback

        self._init_ui()
        self._load_devices()

    def _init_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setSpacing(12)

        # ========== 来源类型选择 ==========
        source_group = QGroupBox("音频来源")
        source_layout = QVBoxLayout()

        self.source_btn_group = QButtonGroup(self)

        self.radio_loopback = QRadioButton("系统扬声器 Loopback（捕获电脑播放的声音）")
        self.radio_loopback.setChecked(True)
        self.radio_input = QRadioButton("麦克风输入设备")

        self.source_btn_group.addButton(self.radio_loopback, 0)
        self.source_btn_group.addButton(self.radio_input, 1)

        source_layout.addWidget(self.radio_loopback)
        source_layout.addWidget(self.radio_input)
        source_group.setLayout(source_layout)

        # ========== Loopback 设备选择 ==========
        loopback_group = QGroupBox("扬声器 Loopback 设备")
        loopback_layout = QVBoxLayout()

        self.loopback_combo = QComboBox()
        self.loopback_combo.setEnabled(True)
        self.refresh_loopback_btn = QPushButton("🔄 刷新设备列表")
        self.refresh_loopback_btn.clicked.connect(self._load_devices)

        loopback_layout.addWidget(self.loopback_combo)
        loopback_layout.addWidget(self.refresh_loopback_btn)
        loopback_group.setLayout(loopback_layout)

        # ========== 麦克风设备选择 ==========
        input_group = QGroupBox("麦克风输入设备")
        input_layout = QVBoxLayout()

        self.input_combo = QComboBox()
        self.input_combo.setEnabled(False)
        self.refresh_input_btn = QPushButton("🔄 刷新设备列表")
        self.refresh_input_btn.clicked.connect(self._load_devices)

        input_layout.addWidget(self.input_combo)
        input_layout.addWidget(self.refresh_input_btn)
        input_group.setLayout(input_layout)

        # ========== 状态提示 ==========
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #888; font-size: 12px;")

        # ========== 按钮区域 ==========
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        self.cancel_btn.setFixedSize(80, 30)

        self.apply_btn = QPushButton("应用")
        self.apply_btn.clicked.connect(self._apply_settings)
        self.apply_btn.setFixedSize(80, 30)
        self.apply_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 5px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)

        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.apply_btn)

        # 组装布局
        main_layout.addWidget(source_group)
        main_layout.addWidget(loopback_group)
        main_layout.addWidget(input_group)
        main_layout.addWidget(self.status_label)
        main_layout.addStretch()
        main_layout.addLayout(btn_layout)

        self.setLayout(main_layout)

        # 信号连接
        self.radio_loopback.toggled.connect(self._on_source_toggled)

    def _on_source_toggled(self):
        is_loopback = self.radio_loopback.isChecked()
        self.loopback_combo.setEnabled(is_loopback)
        self.input_combo.setEnabled(not is_loopback)

    @staticmethod
    def _is_loopback_device(dev_info):
        """判断设备是否为 WASAPI Loopback 设备
        pyaudiowpatch 中 Loopback 设备名称通常包含 'Loopback'，
        或者可以通过 hostApi 为 WASAPI 且是输入设备但非物理设备来判断。
        """
        name = dev_info.get('name', '')
        # pyaudiowpatch 的 Loopback 设备名称包含 "Loopback"
        if 'loopback' in name.lower():
            return True
        # 备选：检查 hostApi 名称
        try:
            host_api_idx = dev_info.get('hostApi', -1)
            if host_api_idx >= 0:
                # 无法在静态上下文中获取 host api info，跳过
                pass
        except Exception:
            pass
        return False

    def _load_devices(self):
        """加载所有音频设备"""
        try:
            if self.pyaudio_instance:
                self.pyaudio_instance.terminate()
            self.pyaudio_instance = pyaudio.PyAudio()

            # 加载 Loopback 设备
            self.loopback_combo.clear()
            self.loopback_device = None

            try:
                default_loopback = self.pyaudio_instance.get_default_wasapi_loopback()
                self.loopback_device = default_loopback
                self.loopback_combo.addItem(
                    f"默认 - {default_loopback['name']}",
                    default_loopback['index']
                )
            except Exception as e:
                logger.warning(f"未找到默认 Loopback 设备: {e}")

            # 遍历所有设备，找到所有 Loopback 设备
            try:
                for i in range(self.pyaudio_instance.get_device_count()):
                    dev_info = self.pyaudio_instance.get_device_info_by_index(i)
                    if self._is_loopback_device(dev_info) and dev_info.get('maxInputChannels', 0) > 0:
                        # 避免重复添加默认设备
                        if self.loopback_device and dev_info['index'] == self.loopback_device['index']:
                            continue
                        label = f"{dev_info['name']} (ID={dev_info['index']})"
                        self.loopback_combo.addItem(label, dev_info['index'])
            except Exception as e:
                logger.warning(f"无法枚举所有 Loopback 设备: {e}")

            if self.loopback_combo.count() == 0:
                self.loopback_combo.addItem("未检测到 Loopback 设备", -1)

            # 加载麦克风设备（排除 Loopback 设备）
            self.input_combo.clear()
            self.input_devices.clear()
            for i in range(self.pyaudio_instance.get_device_count()):
                dev_info = self.pyaudio_instance.get_device_info_by_index(i)
                if dev_info.get('maxInputChannels', 0) > 0 and not self._is_loopback_device(dev_info):
                    name = dev_info['name']
                    self.input_devices.append(dev_info)
                    channels = dev_info['maxInputChannels']
                    rate = int(dev_info['defaultSampleRate'])
                    label = f"{name} ({channels}ch, {rate}Hz)"
                    self.input_combo.addItem(label, dev_info['index'])

            if self.input_combo.count() == 0:
                self.input_combo.addItem("未检测到麦克风设备", -1)

            self.status_label.setText(f"✅ 设备列表已刷新（Loopback: {self.loopback_combo.count()} 个, 麦克风: {self.input_combo.count()} 个）")

        except Exception as e:
            logger.error(f"加载音频设备失败: {e}")
            self.status_label.setText(f"❌ 加载设备失败: {str(e)[:60]}")
            QMessageBox.warning(self, "错误", f"加载音频设备失败:\n{e}")

    def _apply_settings(self):
        """应用设置"""
        if self.radio_loopback.isChecked():
            # Loopback 模式
            idx = self.loopback_combo.currentData()
            if idx is None or idx == -1:
                QMessageBox.warning(self, "提示", "未检测到可用的 Loopback 设备。")
                return
            self.current_selection = {
                "type": "loopback",
                "device_index": idx
            }
        else:
            # 麦克风模式
            idx = self.input_combo.currentData()
            if idx is None or idx == -1:
                QMessageBox.warning(self, "提示", "未检测到可用的麦克风设备。")
                return
            self.current_selection = {
                "type": "microphone",
                "device_index": idx
            }

        self.audio_source_changed.emit(self.current_selection)
        self.status_label.setText("✅ 设置已应用")
        self.accept()

    def get_selection(self):
        """返回当前选择（供外部调用）"""
        return self.current_selection

    def closeEvent(self, event):
        if self.pyaudio_instance:
            self.pyaudio_instance.terminate()
            self.pyaudio_instance = None
        super().closeEvent(event)
