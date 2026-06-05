import streamlit as st
from aip import AipSpeech
import os
import tempfile
import requests
import hashlib
import random

from API import APPID, SECRETKEY, APIKEY, TAPPID, TSECRETKEY

# 运行 streamlit run E:\python\AI-Simultaneous-Interpretation-Assistant\app.py
# ==================== 配置区域 ====================
APP_ID = APPID
API_KEY = APIKEY
SECRET_KEY = SECRETKEY
# =================================================

# 初始化百度语音客户端
client = AipSpeech(APP_ID, API_KEY, SECRET_KEY)

st.set_page_config(page_title="AI同声传译助手", page_icon="🎧")
st.title("🎧 AI同声传译助手")
st.markdown("上传英文音频文件，自动识别并翻译成中文")


def baidu_asr_sdk(audio_bytes, file_format):
    """
    使用百度SDK识别语音
    file_format: wav/mp3/m4a等
    """
    # 创建临时文件（避免文件名冲突）
    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_format}") as tmp_file:
        tmp_file.write(audio_bytes)
        tmp_path = tmp_file.name

    try:
        # 读取音频文件
        with open(tmp_path, "rb") as f:
            audio_data = f.read()

        # 调用百度语音识别
        # dev_pid: 1737 = 英语识别模型
        result = client.asr(audio_data, file_format, 16000, {'dev_pid': 1737})

        return result
    finally:
        # 删除临时文件
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def translate_text(text):
    """翻译英文到中文"""
    try:
        # 使用百度翻译API
        appid = TAPPID
        secret_key = TSECRETKEY
        salt = str(random.randint(32768, 65536))
        sign = hashlib.md5(f"{appid}{text}{salt}{secret_key}".encode('utf-8')).hexdigest()

        url = "https://fanyi-api.baidu.com/api/trans/vip/translate"
        params = {
            "q": text,
            "from": "en",
            "to": "zh",
            "appid": appid,
            "salt": salt,
            "sign": sign
        }

        response = requests.get(url, params=params)
        result = response.json()

        if "trans_result" in result:
            return result["trans_result"][0]["dst"]
        else:
            return f"[翻译失败] {text}"
    except Exception as e:
        # 如果翻译服务出错，显示原文并提示
        return f"[翻译服务暂不可用] {text}"


# 文件上传
uploaded_file = st.file_uploader(
    "选择英文音频文件",
    type=["wav", "m4a", "amr"],
    help="支持WAV、M4A、AMR格式，建议时长60秒以内"
)

if uploaded_file is not None:
    # 显示文件信息
    file_ext = uploaded_file.name.split('.')[-1].lower()
    file_size = len(uploaded_file.getvalue()) / 1024 / 1024  # MB

    col1, col2 = st.columns(2)
    with col1:
        st.info(f"📁 文件名: {uploaded_file.name}")
    with col2:
        st.info(f"📊 文件大小: {file_size:.2f} MB")

    # 识别按钮
    if st.button("🎙️ 开始识别", type="primary"):
        with st.spinner("正在识别音频，请稍候..."):
            audio_bytes = uploaded_file.read()
            result = baidu_asr_sdk(audio_bytes, file_ext)

        # 处理识别结果
        if result.get('err_no') == 0:
            english_text = result['result'][0]
            st.success("✅ 识别成功！")

            # 显示英文结果
            with st.expander("📝 英文原文", expanded=True):
                st.write(english_text)

            # 翻译
            with st.spinner("正在翻译..."):
                chinese_text = translate_text(english_text)

            # 显示中文结果
            with st.expander("🇨🇳 中文翻译", expanded=True):
                st.write(chinese_text)

        else:
            # 识别失败，显示错误信息
            error_code = result.get('err_no')
            error_msg = result.get('err_msg', '未知错误')

            st.error(f"❌ 识别失败: {error_msg} (错误码: {error_code})")

            # 常见错误提示
            if error_code == 3301:
                st.warning(
                    "💡 音频质量不佳或格式不支持，建议：\n- 使用WAV格式\n- 确保采样率16000Hz\n- 音频时长不超过60秒\n- 说话清晰无杂音")
            elif error_code == 3309:
                st.warning("💡 音频太长，请使用60秒以内的音频")
            elif error_code == 3300:
                st.warning("💡 输入参数错误，请确保音频是单声道、16kHz采样率")
            else:
                st.warning("💡 建议尝试：\n- 换一个更短的音频（10秒内）测试\n- 确保音频是英文内容\n- 检查API密钥是否正确")

# 使用说明
with st.sidebar:
    st.markdown("## 📖 使用说明")
    st.markdown("""
    1. **上传音频**：点击上方上传按钮，选择英文音频文件
    2. **开始识别**：点击"开始识别"按钮
    3. **查看结果**：系统会显示英文原文和中文翻译

    ### 支持格式
    - WAV、MP3、M4A、AMR

    ### 建议
    - 音频时长不超过60秒
    - 采样率16000Hz最佳
    - 说话清晰，背景安静

    ### 常见问题
    - 如果识别失败，请尝试10秒内的短音频
    - 确保音频内容是英文
    """)