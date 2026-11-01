"""
离线演示数据（最后一道兜底）

作用：比赛现场断网 / 无 Key / 搜索被限流时，保证 Demo 仍然跑通，
不会出现"点了按钮白屏"。数据按关键词粗匹配，全部带 source 标记，
前端会明确显示「离线演示数据」，不冒充真实搜索结果。
"""
import re
from typing import List

from .base import Place

_DATASET = [
    {
        "keywords": ["川菜", "川味", "辣", "火锅", "中餐"],
        "items": [
            ("蜀香居·老成都川菜馆", "武侯区科华北路 12 号", 4.7, 88, 860, ["招牌水煮鱼", "分量足", "免费米饭"]),
            ("巷子口冒菜（玉林店）", "武侯区玉林横街 5 号附 3", 4.5, 42, 1250, ["一人食友好", "上菜快", "老店"]),
            ("蓉城小馆·家常川菜", "青羊区光华村街 66 号", 4.3, 65, 2400, ["有包间", "适合聚餐"]),
            ("陈麻婆豆腐（总店）", "青羊区西玉龙街 197 号", 4.6, 78, 3100, ["老字号", "环境一般", "味道正宗"]),
        ],
    },
    {
        "keywords": ["咖啡", "下午茶", "甜品", "奶茶"],
        "items": [
            ("拾光咖啡（社区店）", "武侯区一环路南一段 3 号", 4.6, 32, 540, ["安静", "有插座", "手冲"]),
            ("Manner Coffee（来福士店）", "武侯区人民南路四段 3 号", 4.4, 25, 980, ["性价比高", "出餐快"]),
            ("芝士青年·甜品铺", "锦江区春熙路 8 号", 4.2, 45, 2100, ["适合拍照", "偏甜"]),
        ],
    },
    {
        "keywords": ["烧烤", "夜宵", "串", "小吃"],
        "items": [
            ("老铁烧烤（建设路店）", "成华区建设路 33 号", 4.5, 68, 1800, ["分量大", "夜宵营业到凌晨"]),
            ("巷子口把把烧", "青羊区宽窄巷子东侧", 4.1, 95, 2600, ["游客多", "略贵"]),
        ],
    },
]

_DEFAULT = {
    "items": [
        ("本地人气家常菜馆", "附近商圈", 4.5, 75, 1100, ["本地人常去", "口味家常"]),
        ("社区食堂（平价档）", "附近社区", 4.2, 35, 600, ["便宜", "干净"]),
        ("连锁餐厅（商场店）", "附近商场 3F", 4.3, 88, 1500, ["环境好", "排队少"]),
    ]
}


def search(query: str, limit: int = 5, **_ignored) -> List[Place]:
    text = query or ""
    bucket = _DEFAULT
    for entry in _DATASET:
        if any(kw in text for kw in entry["keywords"]):
            bucket = entry
            break

    places: List[Place] = []
    for name, address, rating, cost, distance, tags in bucket["items"]:
        places.append(Place(
            name=name,
            address=address,
            rating=rating,
            avg_cost=float(cost),
            distance_m=int(distance),
            category="餐饮",
            tags=list(tags),
            url="",
            snippet=f"{address}｜人均约{cost}元｜评分{rating}｜" + "、".join(tags),
            source="离线演示数据",
        ))
    return places[:limit]
