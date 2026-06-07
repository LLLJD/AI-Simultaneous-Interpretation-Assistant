# 🎧 AI同声传译助手

实时捕获系统扬声器输出的音频，调用百度语音识别 API 和百度翻译 API，以悬浮字幕形式显示识别原文与实时翻译结果，支持历史记录查看。无需上传文件，即开即用。

## ✨ 功能特点

- 🎙️ **实时捕获音频**：自动录制系统播放的音频（如会议、视频、音乐），可自主选择具体的麦克风/扬声器等音频输出设备
- 🔄 **实时语音识别**：调用百度实时语音识别 API，逐句返回识别文本
- 🌐 **实时翻译**：边说话边翻译，中间结果灰色显示，最终结果金色确认，流畅自然
- 🪟 **悬浮字幕窗口**：置顶半透明窗口，支持拖拽、调整大小，实时显示当前识别内容和译文
- 📜 **历史记录窗口**：独立窗口保存所有识别句子及翻译，支持清空
- 🤖 **AI 对话总结**：基于 DeepSeek + LangChain Agent 智能总结对话内容，生成结构化 Markdown 报告
- 📁 **自动归档**：每次运行自动生成 `output/YYYYMMDD-HHMMSS.txt` 文件保存完整记录
- 🔌 **自动重连**：网络断开后自动重连，静音时发送保活包
- 🎨 **美观界面**：基于 PyQt5 的毛玻璃主题

## 📁 项目结构

```
AI-Simultaneous-Interpretation-Assistant/
├── app.py                # 程序入口
├── main_window.py        # 主悬浮窗口
├── history_window.py     # 历史记录窗口
├── settings_dialog.py    # 设置窗口
├── voice_recognition.py  # 语音识别与音频采集线程
├── translation.py        # 百度翻译 API 封装
├── summarization.py      # DeepSeek AI 对话总结（LangChain Agent）
├── audio_utils.py        # 音频能量计算等辅助函数
├── config.py             # 全局配置（采样率、静音阈值、断句参数等）
├── API.py                # API 密钥配置（需自行创建）
├── requirements.txt      # 依赖列表
├── output/               # 每次运行自动生成的识别结果文件
└── .gitignore            # Git 忽略文件
```

## 🚀 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/LLLJD/AI-Simultaneous-Interpretation-Assistant.git
cd AI-Simultaneous-Interpretation-Assistant
```

### 2. 创建虚拟环境

```bash
python -m venv .venv
.venv\Scripts\activate     # Windows
# 或
source .venv/bin/activate  # Linux/Mac
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 配置 API 密钥

在项目根目录创建 `API.py` 文件：

```python
# 百度语音识别（从 https://console.bce.baidu.com/ 获取）
APPID = "你的语音AppID"      # 一串数字
APIKEY = "你的语音API Key"    # 字母数字混合
DEV_PID = 1737               # 1737 为英语模型（根据需求修改）
URI = "wss://vop.baidu.com/realtime_asr"

# 百度翻译 API（从 https://fanyi-api.baidu.com/ 获取）
TAPPID = "你的翻译AppID"       # 一串数字
TSECRETKEY = "你的翻译密钥"     # 字母数字混合

# DeepSeek AI 总结（从 https://platform.deepseek.com/api_keys 获取）
DEEPSEEK_API_KEY = "sk-xxx"                     # 你的 DeepSeek API Key
DEEPSEEK_MODEL = "deepseek-chat"                # 模型名称
DEEPSEEK_BASE_URL = "https://api.deepseek.com"  # API 地址
```

### 5. 运行应用

```bash
python app.py
```

## 🛠️ 技术栈

| 技术 | 用途 |
|------|------|
| Python | 后端开发 |
| PyQt5 | 桌面图形界面（悬浮窗、历史窗口、系统托盘） |
| 百度实时语音 API | 实时语音识别（WebSocket） |
| 百度翻译 API | 实时文本翻译（HTTP） |
| DeepSeek + LangChain Agent | AI 对话内容智能总结 |
| pyaudiowpatch | Windows 扬声器捕获（WASAPI Loopback） |
| websocket-client | WebSocket 通信 |
| markdown | Markdown 转 HTML 渲染 |
| audioop / struct | 音频格式转换（重采样、声道合并） |

## 📖 使用说明

1. 运行 `python app.py` 后，桌面会出现一个半透明的悬浮窗口。
2. 悬浮窗默认置顶，显示当前识别的原文（白色）和实时翻译（金色）。你可以：
   - 拖拽标题栏移动窗口
   - 拖拽边缘调整窗口大小
   - 点击"📜 历史"按钮打开历史记录窗口
   - 点击"－"最小化到系统托盘
   - 点击"×"退出程序
3. 确保系统正在播放音频（如打开一个英文视频或会议），程序会自动捕获扬声器输出并进行实时识别和翻译。
4. **实时翻译**：说话过程中，中间识别结果会触发灰色临时翻译；句子结束后，最终翻译以金色显示。
5. 识别结果和译文会实时显示在主窗口中，完整记录自动保存到 `output/` 目录下以日期时间命名的文件，并追加到历史窗口。
6. 历史窗口支持清空所有记录。
7. 点击历史窗口的"🤖 总结"按钮，可使用 DeepSeek AI 对当前对话历史进行智能总结，生成结构化 Markdown 报告。

## ⚠️ 注意事项

- **仅支持 Windows**：依赖 `pyaudiowpatch` 的 WASAPI Loopback 功能，Linux/macOS 需要替换音频后端。
- **扬声器音量**：确保系统音量足够大，且没有静音。
- **网络要求**：需要稳定的互联网连接，用于调用百度实时识别 API 和翻译 API。
- **API 配额**：语音识别和翻译均使用百度 API，Agent总结需用到Deepseek API 请确保账户余额充足。
- **静音保持**：如果长时间没有音频输出，程序会自动发送静音包以保持连接不断开。
- **路径中不得有中文**：出现中文会导致QT找不到路径
- **Python版本需在3.13以下**：若版本在3.13以上，会出现audioop软件包找不到的错误 需要手动下载audioop(3.13 后被提出默认的软件库)

## 🐛 常见问题

**Q: 启动后没有识别结果？**  
A: 检查系统是否有音频正在播放；查看控制台日志是否有 "扬声器 Loopback 设备" 信息；确认 `API.py` 中的凭证正确且余额充足。

**Q: 没有翻译结果显示？**  
A: 确认 `API.py` 中已配置 `TAPPID` 和 `TSECRETKEY`；由于依赖百度翻译API 非中国大陆可能会访问失败 检查控制台是否有翻译失败的错误日志。

**Q: 历史窗口不显示？**  
A: 确保 `history_window.py` 存在，且点击"历史"按钮后窗口弹出。如果窗口位置异常，可以手动调整或重置。

**Q: WebSocket 频繁断开？**  
A: 可能是网络不稳定或长时间静音。代码已包含自动重连和静音保活包，一般可自动恢复。

**Q: AI 总结功能不可用？**  
A: 确保 `API.py` 中已正确配置 `DEEPSEEK_API_KEY`（从 [DeepSeek 开放平台](https://platform.deepseek.com/api_keys) 获取），且账户余额充足。也可在设置界面中配置。

## 📜 许可证

MIT License
