# config.py
# ========== 全局配置 ==========
API_RATE = 16000               # 百度强制采样率
CHUNK_MS = 100                 # 每次发送音频时长（毫秒）
SILENCE_THRESHOLD = 500        # 静音能量阈值（越小越敏感）
MAX_SILENCE_SEC = 10           # 最大静音持续秒数，超过后主动发送静音包

# ========== 断句配置 ==========
SENTENCE_SILENCE_SEC = 0.3     # 静音超过此秒数则断句
SENTENCE_MAX_DURATION = 5.0    # 句子最长持续时间（秒），超过后强制断句
# ==============================