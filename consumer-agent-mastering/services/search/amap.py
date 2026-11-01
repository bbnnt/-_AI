"""
高德开放平台 POI 搜索（国内本地生活数据最准，个人开发者免费额度充足）

- 有经纬度：走「周边搜索」place/around，能拿到 distance / rating / cost
- 只有文字地址：走「关键字搜索」place/text
文档：https://lbs.amap.com/api/webservice/guide/api/search
"""
from typing import List, Optional

import requests

from config import Config
from .base import Place, SearchUnavailable

_AROUND_URL = "https://restapi.amap.com/v3/place/around"
_TEXT_URL = "https://restapi.amap.com/v3/place/text"


def _num(value) -> Optional[float]:
    """高德空字段会返回 [] 或 ''，统一转成 float/None。"""
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    if value in ("", [], "[]"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def search(
    keywords: str,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    address: str = "",
    limit: int = 5,
    radius_m: int = 5000,
) -> List[Place]:
    if not Config.AMAP_KEY:
        raise SearchUnavailable("未配置 AMAP_KEY")

    params = {
        "key": Config.AMAP_KEY,
        "keywords": keywords,
        "offset": max(limit * 2, 10),
        "page": 1,
        "extensions": "all",
        "output": "JSON",
    }

    if lat is not None and lng is not None:
        url = _AROUND_URL
        params.update({
            "location": f"{lng:.6f},{lat:.6f}",
            "radius": radius_m,
            "sortrule": "distance",
        })
    else:
        url = _TEXT_URL
        params.update({"keywords": f"{address} {keywords}".strip(), "citylimit": "false"})

    try:
        resp = requests.get(url, params=params, timeout=Config.AMAP_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        raise SearchUnavailable(f"高德请求失败：{exc}") from exc
    except ValueError as exc:
        raise SearchUnavailable("高德返回非 JSON") from exc

    if str(data.get("status")) != "1":
        raise SearchUnavailable(f"高德返回错误：{data.get('info')}")

    places: List[Place] = []
    for poi in data.get("pois", []) or []:
        name = (poi.get("name") or "").strip()
        if not name:
            continue
        biz = poi.get("biz_ext") or {}
        rating = _num(biz.get("rating"))
        cost = _num(biz.get("cost"))
        distance = _num(poi.get("distance"))

        poi_type = poi.get("type") or ""
        category = poi_type.split(";")[-1] if poi_type else ""
        tags = [t for t in (poi.get("tag") or "").split(";") if t][:3]
        if cost:
            tags.append(f"人均{cost:.0f}元")
        if rating:
            tags.append(f"{rating:.1f}分")

        snippet_parts = [p for p in [poi.get("address"), poi_type.replace(";", " · ")] if p]
        places.append(Place(
            name=name,
            address=(poi.get("address") or "").strip(),
            rating=rating,
            avg_cost=cost,
            distance_m=int(distance) if distance is not None else None,
            category=category,
            tags=tags,
            url="",  # 高德 Web 服务不返回 C 端详情页链接
            snippet=" | ".join(snippet_parts),
            source="高德地图",
        ))

    if not places:
        raise SearchUnavailable("高德未返回有效 POI")
    return places[:limit]
