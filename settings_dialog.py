# settings_dialog.py
import logging
import os
import sys

import pyaudiowpatch as pyaudio
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QComboBox, QPushButton, QGroupBox, QRadioButton,
                             QButtonGroup, QMessageBox, QLineEdit, QScrollArea,
                             QWidget, QFormLayout)
from PyQt5.QtCore import Qt, pyqtSignal

logger = logging.getLogger(__name__)

# API.py 路径
API_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "API.py")

# 默认占位文本，用于判断是否需要用户填写
PLACEHOLDER_PATTERNS = ["请放入你的api", "请放入你的", "your api", "your appid", "your key"]


def _is_placeholder(value):
    """判断 API 值是否为占位文本（需要用户填写）"""
    if not value or not isinstance(value, str):
        return True
    v = value.strip().lower()
    for p in PLACEHOLDER_PATTERNS:
        if p in v:
            return True
    return False


def load_api_values():
    """从 API.py 读取现有的 API 配置值，返回 dict"""
    values = {}
    try:
        import API
        # 尝试 reload 获取最新值
        import importlib
        importlib.reload(API)
        for key in ["APPID", "APIKEY", "DEV_PID", "URI", "TAPPID", "TSECRETKEY",
                     "DEEPSEEK_API_KEY", "DEEPSEEK_MODEL", "DEEPSEEK_BASE_URL"]:
            val = getattr(API, key, "")
            values[key] = str(val) if val else ""
    except ImportError:
        logger.info("未找到 API.py，API 配置为空")
    except Exception as e:
        logger.warning(f"读取 API.py 失败: {e}")
    return values


def save_api_values(values):
    """将 API 配置值写入 API.py 文件"""
    content = f'''# 百度语音识别（从 https://console.bce.baidu.com/ 获取）
APPID = "{values.get('APPID', '')}"      # 一串数字
APIKEY = "{values.get('APIKEY', '')}"    # 字母数字混合
DEV_PID = {values.get('DEV_PID', '1737')}               # 1737 为英语模型（根据需求修改）
URI = "{values.get('URI', 'wss://vop.baidu.com/realtime_asr')}"

# 百度翻译 API（从 https://fanyi-api.baidu.com/ 获取）
TSECRETKEY = "{values.get('TSECRETKEY', '')}"
TAPPID = "{values.get('TAPPID', '')}"

# DeepSeek AI 总结（从 https://platform.deepseek.com/api_keys 获取）
DEEPSEEK_API_KEY = "{values.get('DEEPSEEK_API_KEY', '')}"
DEEPSEEK_MODEL = "{values.get('DEEPSEEK_MODEL', 'deepseek-chat')}"
DEEPSEEK_BASE_URL = "{values.get('DEEPSEEK_BASE_URL', 'https://api.deepseek.com')}"
'''
    with open(API_FILE, "w", encoding="utf-8") as f:
        f.write(content)
    logger.info(f"API 配置已保存到 {API_FILE}")


class AudioSettingsDialog(QDialog):
    """音频来源 & API 设置对话框"""

    # 信号：发射选中的设备信息 dict 或 None（使用默认 Loopback）
    audio_source_changed = pyqtSignal(object)
    # API 保存后通知主窗口重载
    api_saved = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setMinimumSize(520, 750)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        self.pyaudio_instance = None
        self.loopback_device = None
        self.input_devices = []
        self.current_selection = None  # None 表示使用默认 Loopback

        self._init_ui()
        self._load_devices()
        self._load_api_values()

    def _init_ui(self):
        # 外层用滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        content_widget = QWidget()
        main_layout = QVBoxLayout(content_widget)
        main_layout.setSpacing(10)

        # ========== 音频来源类型选择 ==========
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

        # ========== API 配置 ==========
        api_group = QGroupBox("百度 API 配置")
        api_layout = QVBoxLayout()

        # 语音识别 API
        asr_label = QLabel("语音识别 API")
        asr_label.setStyleSheet("font-weight: bold; color: #4CAF50; font-size: 13px;")

        asr_form = QFormLayout()
        asr_form.setSpacing(6)

        self.appid_edit = QLineEdit()
        self.appid_edit.setPlaceholderText("请输入语音识别 AppID（一串数字）")
        self.apikey_edit = QLineEdit()
        self.apikey_edit.setPlaceholderText("请输入语音识别 API Key")
        self.devpid_edit = QLineEdit()
        self.devpid_edit.setPlaceholderText("DEV_PID（1737=英语, 1537=普通话）")
        self.uri_edit = QLineEdit()
        self.uri_edit.setPlaceholderText("wss://vop.baidu.com/realtime_asr")

        asr_form.addRow("APPID:", self.appid_edit)
        asr_form.addRow("APIKEY:", self.apikey_edit)
        asr_form.addRow("DEV_PID:", self.devpid_edit)
        asr_form.addRow("URI:", self.uri_edit)

        # 翻译 API
        trans_label = QLabel("翻译 API")
        trans_label.setStyleSheet("font-weight: bold; color: #2196F3; font-size: 13px;")

        trans_form = QFormLayout()
        trans_form.setSpacing(6)

        self.tappid_edit = QLineEdit()
        self.tappid_edit.setPlaceholderText("请输入翻译 AppID（一串数字）")
        self.tsecretkey_edit = QLineEdit()
        self.tsecretkey_edit.setPlaceholderText("请输入翻译密钥")

        trans_form.addRow("TAPPID:", self.tappid_edit)
        trans_form.addRow("TSECRETKEY:", self.tsecretkey_edit)

        # DeepSeek AI 总结 API
        deepseek_label = QLabel("DeepSeek AI 总结")
        deepseek_label.setStyleSheet("font-weight: bold; color: #9C27B0; font-size: 13px;")

        deepseek_form = QFormLayout()
        deepseek_form.setSpacing(6)

        self.deepseek_apikey_edit = QLineEdit()
        self.deepseek_apikey_edit.setPlaceholderText("请输入 DeepSeek API Key（sk-xxx...）")
        self.deepseek_apikey_edit.setEchoMode(QLineEdit.Password)
        self.deepseek_model_edit = QLineEdit()
        self.deepseek_model_edit.setPlaceholderText("deepseek-chat（默认模型）")
        self.deepseek_baseurl_edit = QLineEdit()
        self.deepseek_baseurl_edit.setPlaceholderText("https://api.deepseek.com")

        deepseek_form.addRow("API Key:", self.deepseek_apikey_edit)
        deepseek_form.addRow("Model:", self.deepseek_model_edit)
        deepseek_form.addRow("Base URL:", self.deepseek_baseurl_edit)

        api_layout.addWidget(asr_label)
        api_layout.addLayout(asr_form)
        api_layout.addSpacing(8)
        api_layout.addWidget(trans_label)
        api_layout.addLayout(trans_form)
        api_layout.addSpacing(8)
        api_layout.addWidget(deepseek_label)
        api_layout.addLayout(deepseek_form)
        api_group.setLayout(api_layout)

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
        main_layout.addWidget(api_group)
        main_layout.addWidget(self.status_label)
        main_layout.addStretch()
        main_layout.addLayout(btn_layout)

        scroll.setWidget(content_widget)

        # 顶层布局
        top_layout = QVBoxLayout()
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.addWidget(scroll)
        self.setLayout(top_layout)

        # 信号连接
        self.radio_loopback.toggled.connect(self._on_source_toggled)

    def _on_source_toggled(self):
        is_loopback = self.radio_loopback.isChecked()
        self.loopback_combo.setEnabled(is_loopback)
        self.input_combo.setEnabled(not is_loopback)

    def _load_api_values(self):
        """从 API.py 加载现有值到输入框，如果是占位文本则清空"""
        values = load_api_values()
        for key, edit, default in [
            ("APPID", self.appid_edit, ""),
            ("APIKEY", self.apikey_edit, ""),
            ("DEV_PID", self.devpid_edit, "1737"),
            ("URI", self.uri_edit, "wss://vop.baidu.com/realtime_asr"),
            ("TAPPID", self.tappid_edit, ""),
            ("TSECRETKEY", self.tsecretkey_edit, ""),
            ("DEEPSEEK_API_KEY", self.deepseek_apikey_edit, ""),
            ("DEEPSEEK_MODEL", self.deepseek_model_edit, "deepseek-chat"),
            ("DEEPSEEK_BASE_URL", self.deepseek_baseurl_edit, "https://api.deepseek.com"),
        ]:
            val = values.get(key, "")
            if val and not _is_placeholder(val):
                edit.setText(val)
            elif default:
                edit.setText(default)
            else:
                edit.clear()

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
        """应用设置（音频来源 + API 配置）"""
        # ---- 音频来源 ----
        if self.radio_loopback.isChecked():
            idx = self.loopback_combo.currentData()
            if idx is None or idx == -1:
                QMessageBox.warning(self, "提示", "未检测到可用的 Loopback 设备。")
                return
            self.current_selection = {
                "type": "loopback",
                "device_index": idx
            }
        else:
            idx = self.input_combo.currentData()
            if idx is None or idx == -1:
                QMessageBox.warning(self, "提示", "未检测到可用的麦克风设备。")
                return
            self.current_selection = {
                "type": "microphone",
                "device_index": idx
            }

        # ---- API 配置验证与保存 ----
        api_values = {
            "APPID": self.appid_edit.text().strip(),
            "APIKEY": self.apikey_edit.text().strip(),
            "DEV_PID": self.devpid_edit.text().strip(),
            "URI": self.uri_edit.text().strip(),
            "TAPPID": self.tappid_edit.text().strip(),
            "TSECRETKEY": self.tsecretkey_edit.text().strip(),
            "DEEPSEEK_API_KEY": self.deepseek_apikey_edit.text().strip(),
            "DEEPSEEK_MODEL": self.deepseek_model_edit.text().strip() or "deepseek-chat",
            "DEEPSEEK_BASE_URL": self.deepseek_baseurl_edit.text().strip() or "https://api.deepseek.com",
        }

        # 检查是否有占位文本或空值
        missing = []
        for key, val in api_values.items():
            if not val or _is_placeholder(val):
                missing.append(key)
        if missing:
            result = QMessageBox.question(
                self,
                "API 配置不完整",
                f"以下 API 字段为空或无效:\n{', '.join(missing)}\n\n是否仍要保存？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if result == QMessageBox.No:
                return

        # 保存 API.py
        try:
            save_api_values(api_values)
            # 热重载 API 模块
            import API
            import importlib
            importlib.reload(API)
            logger.info("API 模块已热重载")
            self.api_saved.emit()
        except Exception as e:
            logger.error(f"保存 API 配置失败: {e}")
            QMessageBox.warning(self, "错误", f"保存 API 配置失败:\n{e}")
            return

        self.audio_source_changed.emit(self.current_selection)
        self.status_label.setText("✅ 设置已应用（含 API 配置）")
        self.accept()

    def get_selection(self):
        """返回当前选择（供外部调用）"""
        return self.current_selection

    def closeEvent(self, event):
        if self.pyaudio_instance:
            self.pyaudio_instance.terminate()
            self.pyaudio_instance = None
        super().closeEvent(event)
