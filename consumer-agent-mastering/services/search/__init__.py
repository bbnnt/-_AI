"""
联网搜索门面（Provider 降级链）

    auto: amap -> ddg -> mock     （有坐标时高德最准，无坐标时直接 DDG）
    amap / ddg / mock: 强制单通道

对外只暴露一个函数 search_places()，返回 (places, provider_name, errors)，
errors 会回传给前端做"数据来源透明化"展示（答辩加分项）。
"""
from typing import List, Optional, Tuple

from config import Config
from .base import Place, SearchUnavailable, dedupe
from . import amap as amap_provider
from . import duckduckgo as ddg_provider
from . import mock as mock_provider

_PROVIDER_LABELS = {
    "amap": "高德地图 POI（实时）",
    "ddg": "DuckDuckGo 联网搜索",
    "mock": "离线演示数据",
}


def _has_signal(place: Place) -> bool:
    """是否含可用的结构化字段（评分/人均/距离），没有的条目对「性价比」计算无价值。"""
    return place.rating is not None or place.avg_cost is not None or place.distance_m is not None


def _build_chain(lat: Optional[float], lng: Optional[float]) -> List[str]:
    forced = (Config.SEARCH_PROVIDER or "auto").lower()
    if forced in ("amap", "ddg", "mock"):
        return [forced]
    chain = []
    if Config.AMAP_KEY and lat is not None and lng is not None:
        chain.append("amap")
    chain.append("ddg")
    chain.append("mock")
    return chain


def search_places(
    query: str,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    address: str = "",
    limit: Optional[int] = None,
) -> Tuple[List[Place], str, List[str]]:
    limit = limit or Config.SEARCH_LIMIT
    errors: List[str] = []
    collected: List[Place] = []

    for name in _build_chain(lat, lng):
        try:
            if name == "amap":
                found = amap_provider.search(
                    keywords=query, lat=lat, lng=lng, address=address,
                    limit=limit, radius_m=Config.SEARCH_RADIUS_M,
                )
            elif name == "ddg":
                base = f"{address} {query}".strip() if address else query
                # 追加召回提示，提升大众点评/美团等含「人均/评分」页面的命中率
                full_query = f"{base} 大众点评 人均 评分".strip()
                found = ddg_provider.search(full_query, limit=limit)
            else:
                found = mock_provider.search(query, limit=limit)
        except SearchUnavailable as exc:
            errors.append(f"[{name}] {exc}")
            continue
        except Exception as exc:                     # 任何意外都不该拖垮整个请求
            errors.append(f"[{name}] 未预期错误：{exc}")
            continue

        # 质量闸门：DDG 是通用网页搜索，资讯/攻略页常无评分/人均/距离，
        # 留着会让性价比打分失去区分度，只保留含结构化字段的真实商家信息
        if name == "ddg" and found:
            # DDG 从网页摘要抽取字段，误解析常见（如「0.8折」→0.8分、「35家」→35元），
            # 不合理值直接置空，避免假数据污染推荐表
            for p in found:
                if p.rating is not None and p.rating < 3.0:
                    p.rating = None
                if p.avg_cost is not None and p.avg_cost < 10:
                    p.avg_cost = None
            structured = [p for p in found if _has_signal(p)]
            dropped = len(found) - len(structured)
            if dropped:
                errors.append(f"[ddg] 过滤 {dropped} 条无评分/人均/距离的资讯页")
            if not structured:
                errors.append("[ddg] 无含结构化字段的结果，降级到下一渠道")
                continue
            found = structured

        collected.extend(found or [])
        merged = dedupe(collected)
        # 高德+DDG 混合时：凑够 3 条就停；只剩 mock 时也照常返回
        if len(merged) >= min(3, limit) or name == "mock":
            return merged[:limit], _PROVIDER_LABELS.get(name, name), errors

    merged = dedupe(collected)
    return merged[:limit], _PROVIDER_LABELS.get("mock", "mock"), errors
