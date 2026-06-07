# summarization.py
"""对话历史总结模块 - 使用 DeepSeek ChatModel 进行智能总结。

直接调用 DeepSeek LLM，通过系统提示词指导模型将对话历史总结为结构化 Markdown 报告。
"""

import logging

from langchain_deepseek import ChatDeepSeek
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

# DeepSeek API 默认值（将被 API.py 中的配置覆盖）
_deepseek_api_key = ""
_deepseek_model = "deepseek-chat"
_deepseek_base_url = "https://api.deepseek.com"


def _load_deepseek_config():
    """从 API.py 加载 DeepSeek 配置"""
    global _deepseek_api_key, _deepseek_model, _deepseek_base_url
    try:
        import API
        import importlib
        importlib.reload(API)
        _deepseek_api_key = getattr(API, "DEEPSEEK_API_KEY", "")
        _deepseek_model = getattr(API, "DEEPSEEK_MODEL", "deepseek-chat")
        _deepseek_base_url = getattr(API, "DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    except ImportError:
        logger.info("未找到 API.py，DeepSeek 配置为空")
    except Exception as e:
        logger.warning(f"加载 DeepSeek 配置失败: {e}")


def _is_placeholder(value: str) -> bool:
    """判断 API 值是否为占位文本"""
    if not value:
        return True
    v = value.strip().lower()
    placeholders = ["请放入", "your key", "your api", "sk-xxx"]
    for p in placeholders:
        if p in v:
            return True
    return False


# ========== 系统提示词 ==========

SYSTEM_PROMPT = """你是一个专业的对话内容总结助手。用户会提供一段中英双语的对话历史记录。

请按照以下结构生成 Markdown 格式的总结报告：

## 📋 对话总结报告

### 🎯 核心主题
（1-2 句话概括对话的核心主题和目的）

### 📝 关键要点
（列出 3-5 个最重要的讨论点或信息点，使用编号列表）

### 🗣️ 讨论要点
（按时间顺序或逻辑顺序，列出对话中的主要讨论内容，每个要点包含原文关键信息和对应翻译理解）

### 📊 总结
（2-3 句话的总结，提炼对话的核心结论或后续行动项）

### 🏷️ 关键词
（提取 5-8 个关键词，用逗号分隔）

请确保总结内容：
1. 全面覆盖对话中的重要信息
2. 中英文关键信息都保留
3. 使用清晰的 Markdown 格式
4. 内容简洁但信息完整
5. 不要遗漏任何重要讨论点"""


# ========== 核心函数 ==========

def summarize_history(original_texts: str, translated_texts: str) -> str | None:
    """对对话历史进行 AI 总结。

    Args:
        original_texts: 原文对话历史（英文）
        translated_texts: 对应的翻译文本（中文）

    Returns:
        Markdown 格式的总结报告，失败时返回 None
    """
    _load_deepseek_config()

    if not _deepseek_api_key or _is_placeholder(_deepseek_api_key):
        logger.warning("DeepSeek API Key 未配置或为占位文本，无法进行总结")
        return None

    # 构建输入
    input_text = f"""请对以下对话历史进行总结：

=== 原文（英文） ===
{original_texts}

=== 翻译（中文） ===
{translated_texts}"""

    try:
        llm = ChatDeepSeek(
            model=_deepseek_model,
            api_key=_deepseek_api_key,
            base_url=_deepseek_base_url,
            temperature=0.3,
            max_tokens=4096,
        )

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=input_text),
        ]

        response = llm.invoke(messages)
        output: str = str(response.content)

        if output:
            logger.info("AI 总结生成成功")
            return output
        else:
            logger.warning("AI 总结返回空结果")
            return None

    except Exception as e:
        logger.error(f"AI 总结失败: {e}")
        return None
