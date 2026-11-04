"""
# ============================================================
#  知途 · 用户消费记录库（我的消费记录）
# ============================================================
#
#  功能定位：
#    用户可以把自己真实消费过的餐厅录入进来（地址 / 店名 / 人数 /
#    人均 / 总价 / 评价），搜索推荐时这些"亲测数据"作为第一优先
#    数据源注入候选列表——真实体验 > 联网搜索 > 大模型推理。
#
#  存储方案：
#    JSON 文件持久化（data/user_records.json），演示阶段零依赖、
#    重启不丢数据；上线阶段可平滑替换为数据库（接口不变）。
#
#  与 Place 模型的关系：
#    to_place() 把一条用户记录转成统一的 Place，下游 Prompt 构造、
#    规则兜底打分、前端展示无需任何改动即可消费"亲测数据"。
# ============================================================
"""
import json
import os
import re
import threading
import time
import uuid
from typing import Dict, List, Optional

from services.search.base import Place, parse_distance

# 存储文件：项目根目录 data/user_records.json
_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
_DATA_FILE = os.path.join(_DATA_DIR, "user_records.json")

# 线程锁：Flask 多线程下保证 JSON 读写安全
_LOCK = threading.Lock()

# 评价里的数字评分识别：纯数字或 X.X 分
_RE_RATING_TEXT = re.compile(r"^([0-5](?:\.\d)?)\s*分?$")


def _ensure_store() -> None:
    """确保数据目录和文件存在（首次写入前调用）。"""
    if not os.path.isdir(_DATA_DIR):
        os.makedirs(_DATA_DIR, exist_ok=True)
    if not os.path.isfile(_DATA_FILE):
        with open(_DATA_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False)


def _load_all() -> List[dict]:
    """读取全部记录（内部函数，调用方需持锁）。"""
    _ensure_store()
    try:
        with open(_DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_all(records: List[dict]) -> None:
    """写入全部记录（内部函数，调用方需持锁）。"""
    _ensure_store()
    with open(_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


def _parse_rating(comment: str) -> Optional[float]:
    """评价是纯数字（如 4.5 / 4.5分）时解析为评分，否则返回 None。"""
    if not comment:
        return None
    match = _RE_RATING_TEXT.match(comment.strip())
    if not match:
        return None
    try:
        value = float(match.group(1))
        return value if 0 <= value <= 5 else None
    except ValueError:
        return None


# ============================================================
#  CRUD
# ============================================================
def add_record(
    name: str,
    address: str = "",
    people: Optional[int] = None,
    avg_cost: Optional[float] = None,
    total_cost: Optional[float] = None,
    comment: str = "",
) -> dict:
    """
    新增一条消费记录。

    :param name:       饭店名称（必填）
    :param address:    地址
    :param people:     本次消费人数
    :param avg_cost:   人均消费（元）
    :param total_cost: 总价（元）
    :param comment:    评价（文字或 X.X 分）
    :return:           完整记录字典（含 id / created_at）
    """
    name = (name or "").strip()
    if not name:
        raise ValueError("饭店名称不能为空")

    record = {
        "id": uuid.uuid4().hex[:12],
        "name": name,
        "address": (address or "").strip(),
        "people": int(people) if people else None,
        "avg_cost": float(avg_cost) if avg_cost else None,
        "total_cost": float(total_cost) if total_cost else None,
        "comment": (comment or "").strip(),
        "created_at": int(time.time()),
    }
    with _LOCK:
        records = _load_all()
        records.append(record)
        _save_all(records)
    return record


def list_records() -> List[dict]:
    """列出全部消费记录（按录入时间倒序）。"""
    with _LOCK:
        records = _load_all()
    return sorted(records, key=lambda r: r.get("created_at", 0), reverse=True)


def delete_record(record_id: str) -> bool:
    """按 id 删除一条记录，返回是否删除成功。"""
    with _LOCK:
        records = _load_all()
        remaining = [r for r in records if r.get("id") != record_id]
        if len(remaining) == len(records):
            return False
        _save_all(remaining)
    return True


# ============================================================
#  搜索匹配 + 转 Place 模型
# ============================================================
def _record_text(record: dict) -> str:
    """把记录里可用于匹配的文本拼到一起。"""
    return " ".join(filter(None, [
        record.get("name", ""),
        record.get("address", ""),
        record.get("comment", ""),
    ]))


def search_records(keyword: str, address: str = "", limit: int = 5) -> List[dict]:
    """
    按关键词匹配用户消费记录。

    匹配策略：店名 / 地址 / 评价 中包含关键词里的任一词即命中，
    命中条数多时按"命中词数"排序，保证最相关的亲测记录排最前。

    :param keyword: 需求关键词（如 "川菜" / "火锅"）
    :param address: 用户当前地址（同城记录优先）
    :param limit:   最多返回条数
    :return:        匹配到的记录列表（已排序）
    """
    with _LOCK:
        records = _load_all()
    if not records:
        return []

    # 分词：中文按 2 字滑窗 + 直接切出品类词，简单但够用
    words = set()
    text = f"{keyword or ''}"
    for w in re.findall(r"[\u4e00-\u9fa5]{2,}|[a-zA-Z]+", text):
        words.add(w)
    # 单字品类也保留（如 "辣"）
    for ch in text:
        if "\u4e00" <= ch <= "\u9fa5":
            words.add(ch)
    words.discard("")
    if not words:
        return []

    scored = []
    for record in records:
        hay = _record_text(record)
        hits = sum(1 for w in words if w in hay)
        if hits <= 0:
            continue
        # 地址同城加分（地址非空且与当前地址有交集）
        rec_addr = record.get("address", "")
        addr_bonus = 1 if (address and rec_addr and any(
            seg in rec_addr for seg in address.split() if len(seg) >= 2)) else 0
        scored.append((hits + addr_bonus, record.get("created_at", 0), record))

    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [item[2] for item in scored[:limit]]


def record_to_place(record: dict) -> Place:
    """
    把一条用户消费记录转成统一的 Place 模型。

    转换后即可注入候选列表参与 Prompt 构造与规则兜底打分，
    source 标记为"我的消费记录"，前端/大模型可识别其来源。
    """
    name = (record.get("name") or "").strip()
    address = (record.get("address") or "").strip()
    people = record.get("people")
    avg_cost = record.get("avg_cost")
    total_cost = record.get("total_cost")
    comment = (record.get("comment") or "").strip()

    rating = _parse_rating(comment)

    # 组装"真实依据"摘要：亲测数据比网页抓取更可信，字段尽量全
    parts = [f"店名：{name}"]
    if address:
        parts.append(f"地址：{address}")
    if people:
        parts.append(f"本次消费人数：{people} 人")
    if avg_cost:
        parts.append(f"人均：{avg_cost:.0f} 元")
    if total_cost:
        parts.append(f"总价：{total_cost:.0f} 元")
    if comment:
        parts.append(f"我的评价：{comment}")
    snippet = "，".join(parts)

    tags = []
    if comment and not rating:
        tags.append(comment[:12])
    tags.append("本人消费过")

    return Place(
        name=name,
        address=address,
        rating=rating,
        avg_cost=float(avg_cost) if avg_cost else None,
        distance_m=parse_distance(address) or None,   # 地址里若含距离描述则解析
        category="",
        tags=tags,
        url="",
        snippet=snippet,
        source="我的消费记录",
    )