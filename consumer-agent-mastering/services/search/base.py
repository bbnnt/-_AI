"""
搜索结果统一数据模型 + 从网页文本里抽取结构化字段的解析器。

设计原则：所有 Provider 必须产出同一种 Place，下游（Prompt / 兜底打分 / 前端）
只认这一种结构，新增渠道时无需改任何业务代码。
"""
import re
from dataclasses import dataclass, field, asdict
from typing import List, Optional


@dataclass
class Place:
    name: str
    address: str = ""
    rating: Optional[float] = None      # 评分，满分 5
    avg_cost: Optional[float] = None    # 人均消费（元）
    distance_m: Optional[int] = None    # 距用户距离（米）
    category: str = ""
    tags: List[str] = field(default_factory=list)
    url: str = ""
    snippet: str = ""                   # 原始摘要，作为"真实依据"展示
    source: str = ""                    # 数据来源渠道

    def to_dict(self) -> dict:
        data = asdict(self)
        data["distance_text"] = format_distance(self.distance_m)
        data["cost_text"] = f"{self.avg_cost:.0f}元/人" if self.avg_cost else "未标注"
        data["rating_text"] = f"{self.rating:.1f}分" if self.rating else "未标注"
        return data


def format_distance(meters: Optional[int]) -> str:
    if meters is None:
        return "未知"
    if meters < 1000:
        return f"{int(meters)}m"
    return f"{meters / 1000:.1f}km"


# ---------------- 文本字段抽取 ----------------

_RE_RATING = re.compile(r"(\d(?:\.\d)?)\s*(?:分|星|/5|／5)")
_RE_COST = re.compile(
    r"(?:人均|均价|客单价|人均消费|大约|约)\s*[¥￥]?\s*(\d{1,4}(?:\.\d)?)"
)
_RE_COST_SYMBOL = re.compile(r"[¥￥]\s*(\d{1,4}(?:\.\d)?)")
_RE_DIST = re.compile(r"(\d+(?:\.\d+)?)\s*(公里|千米|km|KM|米|m)")


def parse_rating(text: str) -> Optional[float]:
    if not text:
        return None
    match = _RE_RATING.search(text)
    if not match:
        return None
    try:
        value = float(match.group(1))
    except ValueError:
        return None
    if 0 <= value <= 5:
        return value
    if 0 <= value <= 50:          # "45分" 这种百分制，折算回 5 分制
        return round(value / 10.0, 1)
    return None


def parse_cost(text: str) -> Optional[float]:
    if not text:
        return None
    match = _RE_COST.search(text) or _RE_COST_SYMBOL.search(text)
    if not match:
        return None
    try:
        value = float(match.group(1))
    except ValueError:
        return None
    # 排除明显不像人均的数值（如年份、电话号）
    if value <= 0 or value > 5000:
        return None
    return value


def parse_distance(text: str) -> Optional[int]:
    if not text:
        return None
    match = _RE_DIST.search(text)
    if not match:
        return None
    try:
        value = float(match.group(1))
    except ValueError:
        return None
    unit = match.group(2).lower()
    meters = value * 1000 if unit in ("公里", "千米", "km") else value
    return int(meters)


def dedupe(places: List[Place]) -> List[Place]:
    """按名称去重，保留字段更完整的那个。"""
    merged = {}
    for place in places:
        if not place.name:
            continue
        key = re.sub(r"[\s\-—_（）()·,，.。]", "", place.name).lower()[:24]
        if key not in merged:
            merged[key] = place
            continue
        kept = merged[key]
        for attr in ("rating", "avg_cost", "distance_m", "address", "snippet", "url"):
            if getattr(kept, attr) in (None, "", 0) and getattr(place, attr) not in (None, "", 0):
                setattr(kept, attr, getattr(place, attr))
        for tag in place.tags:
            if tag not in kept.tags:
                kept.tags.append(tag)
    return list(merged.values())


class SearchUnavailable(RuntimeError):
    """该渠道当前不可用（未配置 Key / 网络失败），调用方应降级到下一渠道。"""
