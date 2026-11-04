"""
集中配置：所有可变项都走环境变量，方便比赛现场一键切换（云端 / 本地模型 / 离线）。
优先级：系统环境变量 > .env 文件 > 代码默认值
"""
import os

from dotenv import load_dotenv

load_dotenv()


def _env(key: str, default: str = "") -> str:
    value = os.getenv(key)
    if value is None:
        return default
    return value.strip()


def _env_int(key: str, default: int) -> int:
    try:
        return int(_env(key, str(default)))
    except (TypeError, ValueError):
        return default


def _env_float(key: str, default: float) -> float:
    try:
        return float(_env(key, str(default)))
    except (TypeError, ValueError):
        return default


class Config:
    # ---------------- Flask ----------------
    SECRET_KEY = _env("SECRET_KEY", "dev-only-change-me")
    HOST = _env("HOST", "127.0.0.1")
    PORT = _env_int("PORT", 5000)
    DEBUG = _env("DEBUG", "1") == "1"

    # ---------------- 大模型 ----------------
    # deepseek => 云端 API；ollama => 本地模型（OpenAI 兼容协议）
    LLM_PROVIDER = _env("LLM_PROVIDER", "deepseek").lower()
    LLM_TIMEOUT = _env_int("LLM_TIMEOUT", 60)
    LLM_TEMPERATURE = _env_float("LLM_TEMPERATURE", 0.3)
    LLM_MAX_TOKENS = _env_int("LLM_MAX_TOKENS", 1600)

    DEEPSEEK_API_KEY = _env("DEEPSEEK_API_KEY")
    DEEPSEEK_BASE_URL = _env("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    DEEPSEEK_MODEL = _env("DEEPSEEK_MODEL", "deepseek-chat")

    OLLAMA_BASE_URL = _env("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL = _env("OLLAMA_MODEL", "qwen2.5:7b")

    # ---------------- 联网搜索 ----------------
    # auto | amap | ddg | mock
    SEARCH_PROVIDER = _env("SEARCH_PROVIDER", "auto").lower()
    # OSM Overpass 真实周边搜索开关：演示现场网络不通时可设 OSM_SEARCH_ENABLED=0 跳过
    OSM_SEARCH_ENABLED = _env("OSM_SEARCH_ENABLED", "1") == "1"
    SEARCH_TIMEOUT = _env_int("SEARCH_TIMEOUT", 4)
    SEARCH_LIMIT = _env_int("SEARCH_LIMIT", 5)
    SEARCH_RADIUS_M = _env_int("SEARCH_RADIUS_M", 5000)

    # 高德开放平台 Web 服务 Key（个人开发者免费额度充足，https://lbs.amap.com）
    AMAP_KEY = _env("AMAP_KEY")
    AMAP_TIMEOUT = _env_int("AMAP_TIMEOUT", 8)

    # DuckDuckGo 区域，中文用 cn-zh
    DDG_REGION = _env("DDG_REGION", "cn-zh")

    # 逆地理编码兜底（高德不可用时走 OSM，免费无 Key）
    NOMINATIM_URL = _env("NOMINATIM_URL", "https://nominatim.openstreetmap.org")

    # ---------------- 业务参数 ----------------
    # 性价比打分权重（规则兜底 & 提示词里都引用，保证口径一致）
    WEIGHT_RATING = _env_float("WEIGHT_RATING", 0.5)
    WEIGHT_PRICE = _env_float("WEIGHT_PRICE", 0.35)
    WEIGHT_DISTANCE = _env_float("WEIGHT_DISTANCE", 0.15)
    # 用户没提预算时，用它做“人均参考线”
    DEFAULT_BUDGET = _env_float("DEFAULT_BUDGET", 150.0)

    @classmethod
    def llm_ready(cls) -> bool:
        if cls.LLM_PROVIDER == "ollama":
            return True  # 本地模型，是否在线由调用时探测
        return bool(cls.DEEPSEEK_API_KEY)

    @classmethod
    def search_ready(cls) -> dict:
        return {"amap": bool(cls.AMAP_KEY), "ddg": True, "mock": True}
