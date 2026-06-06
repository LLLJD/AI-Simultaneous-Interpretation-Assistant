# translation.py
import hashlib
import random
import logging
import requests

import API

logger = logging.getLogger(__name__)

# 百度翻译 API 配置
TRANSLATE_URL = "https://fanyi-api.baidu.com/api/trans/vip/translate"


def translate_text(text: str, from_lang: str = "en", to_lang: str = "zh") -> str:
    """调用百度翻译 API，将文本从 from_lang 翻译为 to_lang。

    Args:
        text: 待翻译文本
        from_lang: 源语言代码（默认 "en"）
        to_lang: 目标语言代码（默认 "zh"）

    Returns:
        翻译后的文本，失败时返回空字符串
    """
    if not text or not text.strip():
        return ""

    appid = API.TAPPID
    secret_key = API.TSECRETKEY
    salt = str(random.randint(32768, 65536))
    sign_input = appid + text + salt + secret_key
    sign = hashlib.md5(sign_input.encode("utf-8")).hexdigest()

    params = {
        "q": text,
        "from": from_lang,
        "to": to_lang,
        "appid": appid,
        "salt": salt,
        "sign": sign,
    }

    try:
        resp = requests.get(TRANSLATE_URL, params=params, timeout=5)
        result = resp.json()
        if "trans_result" in result and len(result["trans_result"]) > 0:
            translated = result["trans_result"][0]["dst"]
            logger.info(f"翻译成功: {text[:50]}... → {translated[:50]}...")
            return translated
        else:
            error_code = result.get("error_code", "unknown")
            error_msg = result.get("error_msg", "unknown")
            logger.error(f"翻译失败: code={error_code}, msg={error_msg}")
            return ""
    except requests.exceptions.Timeout:
        logger.error("翻译请求超时")
        return ""
    except Exception as e:
        logger.error(f"翻译异常: {e}")
        return ""
