# 🎧 AI同声传译助手(DAY1 跑通逻辑流程)

上传英文音频文件，自动识别并翻译成中文，以字幕形式呈现。支持 WAV、M4A、AMR 格式。

## ✨ 功能特点

- 🎙️ **语音识别**：调用百度语音API，精准识别英文语音
- 🌐 **文本翻译**：集成百度翻译API，实时转换为中文
- 📝 **字幕展示**：识别结果和翻译结果分栏对比显示
- ⚡ **实时反馈**：处理过程实时显示进度和状态
 
## 📁 项目结构
├── app.py # 主程序 \
├── API.py # API密钥配置（需自行创建）\
├── requirements.txt # 依赖列表 \
└── .gitignore # Git忽略文件


## 🚀 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/LLLJD/AI-Simultaneous-Interpretation-Assistant.git
cd AI-Simultaneous-Interpretation-Assistant
```
### 2. 创建虚拟环境
```bash
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# 或
.venv\Scripts\activate     # Windows
```
### 3. 安装依赖
```bash
pip install -r requirements.txt
```
### 4. 配置API密钥
在项目根目录创建 API.py 文件：

```python
# 百度语音识别（从 https://console.bce.baidu.com/ 获取）
APPID = "你的语音AppID"      # 一串数字
APIKEY = "你的语音API Key"    # 字母数字混合
SECRETKEY = "你的语音Secret Key"

# 百度翻译（从 https://fanyi-api.baidu.com/ 获取）
TSECRETKEY = "你的百度翻译Secret Key"
TAPPID = "你的百度翻译AppID"
```

### 5. 运行应用
```bash
streamlit run app.py
```
## 🛠️ 技术栈

| 技术 | 用途 |
|------|------|
| Python | 后端开发 |
| Streamlit | Web界面 |
| 百度语音API | 语音识别 |
| 百度翻译API | 文本翻译 |

### 📖 使用说明
打开浏览器访问 http://localhost:8501

上传英文音频文件（WAV/M4A/AMR格式）

点击"开始识别"按钮

等待处理完成，查看英文原文和中文翻译