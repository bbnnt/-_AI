"""
大模型统一客户端：DeepSeek 云端 与 本地 Ollama 共用 OpenAI 兼容协议。

支持两种配置方式（优先级：运行时传入 > .env 配置）：
1. 前端网页动态传入 api_key / provider / base_url / model（存 localStorage，随请求传后端）
2. .env 静态配置 LLM_PROVIDER / DEEPSEEK_API_KEY 等

任何失败都抛 LLMError，由 routes.py 兜底成规则推荐，绝不 500 白屏。
"""
from typing import Dict, List, Optional

import requests

from config import Config


class LLMError(RuntimeError):
    pass


class LLMNotConfigured(LLMError):
    pass


def _endpoint(runtime: dict = None) -> Dict[str, Optional[str]]:
    """
    解析大模型端点配置。
    :param runtime: 前端运行时传入的 {api_key, provider, base_url, model}，优先级最高
    """
    runtime = runtime or {}
    provider = (runtime.get("provider") or Config.LLM_PROVIDER).lower()

    if provider == "ollama":
        return {
            "url": f"{(runtime.get('base_url') or Config.OLLAMA_BASE_URL).rstrip('/')}/v1/chat/completions",
            "model": runtime.get("model") or Config.OLLAMA_MODEL,
            "key": runtime.get("api_key") or None,
            "label": f"Ollama·{runtime.get('model') or Config.OLLAMA_MODEL}",
        }

    # deepseek / openai 兼容协议
    key = runtime.get("api_key") or Config.DEEPSEEK_API_KEY
    if not key:
        raise LLMNotConfigured("未配置 API Key（可在网页设置面板中填入）")
    try:
        key.encode("ascii")
    except UnicodeEncodeError:
        raise LLMNotConfigured(
            "API Key 含非 ASCII 字符（疑似未替换的占位符），请填入真实 Key"
        )
    base_url = runtime.get("base_url") or Config.DEEPSEEK_BASE_URL
    model = runtime.get("model") or Config.DEEPSEEK_MODEL
    return {
        "url": f"{base_url.rstrip('/')}/chat/completions",
        "model": model,
        "key": key,
        "label": f"{model}",
    }


def chat(messages: List[Dict[str, str]], runtime: dict = None) -> Dict[str, str]:
    """
    调用大模型。
    :param runtime: 前端运行时配置 {api_key, provider, base_url, model}
    :return: {content, model_label}
    """
    conf = _endpoint(runtime)
    headers = {"Content-Type": "application/json"}
    if conf["key"]:
        headers["Authorization"] = f"Bearer {conf['key']}"

    payload = {
        "model": conf["model"],
        "messages": messages,
        "temperature": Config.LLM_TEMPERATURE,
        "max_tokens": Config.LLM_MAX_TOKENS,
        "stream": False,
    }

    try:
        resp = requests.post(conf["url"], headers=headers, json=payload, timeout=Config.LLM_TIMEOUT)
    except requests.RequestException as exc:
        raise LLMError(f"无法连接大模型服务（{conf['label']}）：{exc}") from exc
    except UnicodeEncodeError as exc:
        raise LLMError(f"请求头编码失败（{conf['label']}），请检查 API Key 是否含非法字符：{exc}") from exc

    if resp.status_code >= 400:
        raise LLMError(f"大模型返回 HTTP {resp.status_code}：{resp.text[:300]}")

    try:
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"大模型响应格式异常：{resp.text[:300]}") from exc

    content = (content or "").strip()
    if not content:
        raise LLMError("大模型返回空内容")
    return {"content": content, "model_label": conf["label"]}


def health() -> Dict[str, object]:
    """给 /api/agent/status 用的轻量自检，不消耗 token。"""
    try:
        conf = _endpoint()
        return {"configured": True, "provider": Config.LLM_PROVIDER, "model": conf["label"]}
    except LLMNotConfigured as exc:
        return {"configured": False, "provider": Config.LLM_PROVIDER, "error": str(exc)}