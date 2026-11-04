"""
# ============================================================
#  知途 · AI 出行与消费性价比决策 Agent  ——  HTTP 接口层
# ============================================================
#
#  接口清单
#    GET    /api/health               健康检查
#    GET    /api/agent/status         各依赖配置自检（大模型 / 搜索渠道）
#    POST   /api/agent/recommend      核心接口：需求 + 定位 -> 联网搜索 -> 大模型推荐
#    GET    /api/records              列出用户消费记录（我的消费记录）
#    POST   /api/records              新增一条用户消费记录
#    DELETE /api/records/<id>         删除一条用户消费记录
#
#  一次 /api/agent/recommend 的完整链路：
#    ① 归一化定位（经纬度 -> 地址，或直接用用户手输地址）
#    ② 组装搜索引擎 Query
#    ③ 获取候选商家（第零优先：我的消费记录亲测数据 → 高德/DDG/OSM联网 → Mock兜底）
#    ④ 构造 Prompt（需求 + 定位 + 带编号的真实数据）
#    ⑤ 调大模型 输出 Markdown 推荐
#    ⑥ 大模型不可用时，用同一套打分口径在 Python 里兜底，保证永远有结果
# ============================================================
"""
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Tuple

from flask import Blueprint, jsonify, request

from config import Config
from prompts.system_prompt import SYSTEM_PROMPT, build_user_prompt
from services import geo, llm
from mock_db import get_mock_places
import user_db
from services.search.base import Place, parse_distance, dedupe
from services.search import osm as osm_provider
from services.search import duckduckgo as ddg_provider
from services.search import amap as amap_provider

api_bp = Blueprint("api", __name__, url_prefix="/api")


# ============================================================
#  工具函数
# ============================================================
def _to_float(value) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


_RE_NUM_IN_STR = re.compile(r"(\d+(?:\.\d+)?)")


def _extract_num(text) -> Optional[float]:
    """从 "85元" / "1.2km" 这类字符串里抽出数值。"""
    match = _RE_NUM_IN_STR.search(str(text or ""))
    return float(match.group(1)) if match else None


def _mock_to_places(raw_items: List[dict]) -> List[Place]:
    """
    把 mock_db.get_mock_places() 返回的字典列表转成统一的 Place 模型。

    转换后下游（Prompt 构造 / 规则兜底打分 / 前端展示）无需任何改动，
    未来切换到高德 API 时，只需让高德结果也产出同样的 Place 即可无缝替换。
    """
    places: List[Place] = []
    for item in raw_items:
        name = (item.get("name") or "").strip()
        if not name:
            continue
        rating = _to_float(item.get("rating"))
        cost = _extract_num(item.get("cost"))          # "85元" -> 85.0
        dist_text = str(item.get("distance") or "")
        distance_m = parse_distance(dist_text)          # "1.2km" -> 1200
        address = (item.get("address") or "").strip()
        tags = list(item.get("tags") or [])

        # 干净的结构化文本，作为「真实依据」喂给大模型做性价比分析
        snippet = (
            f"店名：{name}，距离：{dist_text}，"
            f"评分：{rating if rating else '未获取到'}，"
            f"人均：{f'{cost:.0f}元' if cost else '未获取到'}"
        )

        places.append(Place(
            name=name,
            address=address,
            rating=rating,
            avg_cost=cost,
            distance_m=distance_m,
            category=(item.get("category") or "").strip(),
            tags=tags,
            url="",
            snippet=snippet,
            source="离线演示数据（Mock）",
        ))
    return places


_RE_BUDGET_ARABIC = re.compile(r"(\d{2,5})\s*(?:元|块|rmb|RMB|块钱)")
_RE_BUDGET_AFTER = re.compile(r"预算[^\d]{0,4}(\d{2,5})")
_RE_BUDGET_PER = re.compile(r"人均[^\d]{0,4}(\d{2,5})")
# 裸数字 + 以内/以下/左右（如「100以内」）；「1000米以内」因中间有「米」天然不匹配
_RE_BUDGET_BARE = re.compile(r"(\d{2,5})\s*(?:以内|以下|左右)")
_CN_NUM = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
           "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_RE_BUDGET_CN = re.compile(r"(?:预算)?([一二两三四五六七八九]?[十百千万]?[一二两三四五六七八九]?[十百]?)\s*(?:元|块)\s*(?:以内|以下|左右)?")


def _cn_to_number(text: str) -> Optional[float]:
    """把「一百五」「两千」「三百」这类中文数字转成阿拉伯数字。"""
    if not text:
        return None
    if "万" in text:
        head, _, tail = text.partition("万")
        base = _cn_to_number(head) or 1
        return base * 10000 + (_cn_to_number(tail) or 0)
    total, section, number = 0, 0, 0
    for ch in text:
        if ch in _CN_NUM:
            number = _CN_NUM[ch]
        elif ch == "十":
            section += (number or 1) * 10
            number = 0
        elif ch == "百":
            section += (number or 1) * 100
            number = 0
        elif ch == "千":
            section += (number or 1) * 1000
            number = 0
    total += section + number
    return float(total) if total else None


def parse_budget(query: str) -> float:
    """
    从自然语言里抽预算，抽不到就用默认参考线。
    覆盖：「预算100」「人均100」「一百以内」「两百块左右」
    """
    text = query or ""

    for regex in (_RE_BUDGET_ARABIC, _RE_BUDGET_AFTER, _RE_BUDGET_PER, _RE_BUDGET_BARE):
        match = regex.search(text)
        if match:
            value = _to_float(match.group(1))
            if value and 5 <= value <= 100000:
                return value

    match = _RE_BUDGET_CN.search(text)
    if match:
        value = _cn_to_number(match.group(1))
        if value and 5 <= value <= 100000:
            return value

    return Config.DEFAULT_BUDGET


# 搜索时要去掉的"意图词"，留下真正的品类词
_NOISE_WORDS = [
    "帮我", "请帮我", "麻烦", "我想", "我要", "想要", "一下", "推荐一下",
    "推荐", "附近", "周边", "周围", "性价比", "性价比高", "好吃", "好吃的",
    "的", "找", "来个", "整点", "有没有", "什么", "比较", "好点", "餐厅",
    "预算", "以内", "左右", "元", "块",
    # 时间/意图词：对搜索引擎无召回价值
    "周末", "周六", "周日", "今天", "明天", "今晚", "中午", "晚上", "夜里",
    "下午", "早上", "想去", "想", "去", "吃顿", "顿", "吃点", "喝点",
]

# 吃喝意图信号：没命中品类词典、但明显是"吃/喝"需求时，用「美食」兜底
_EATING_HINTS = ("吃", "餐", "饭", "喝", "味", "食", "馋")


# 本地生活高频品类词：命中即作为搜索核心词，召回质量远好于整句丢给搜索引擎
_CATEGORY_KEYWORDS = [
    "川菜", "火锅", "烧烤", "串串", "冒菜", "小吃", "面馆", "快餐", "简餐", "日料",
    "寿司", "西餐", "牛排", "披萨", "韩餐", "东北菜", "湘菜", "粤菜", "江浙菜",
    "云南菜", "新疆菜", "清真", "素食", "早茶", "夜宵", "咖啡", "奶茶", "甜品",
    "蛋糕", "面包", "茶餐厅", "自助餐", "砂锅", "米线", "螺蛳粉", "饺子", "包子",
    # 口语化变体：用户不一定说标准品类名
    "东北", "铁锅炖", "锅包肉", "辣椒炒肉", "剁椒", "烧腊", "部队锅", "炸鸡",
    "螺蛳", "担担面", "烤鱼", "烤肉", "串串香", "钵钵鸡",
]


def extract_keywords(query: str) -> str:
    """
    从自然语言里抽「搜索引擎能听懂」的核心词。
    ① 优先命中品类词典（「想吃顿好的」这种口语化表达，词典能救回来）
    ② 没命中词典但含吃喝意图 -> 用「美食」兜底，比把口语整句丢给搜索引擎召回更好
    ③ 其次去掉噪音词后取剩余短语
    ④ 都失败则原样返回，避免把 Query 洗成空串
    """
    text = query or ""

    hits = [word for word in _CATEGORY_KEYWORDS if word in text]
    if hits:
        return " ".join(hits[:2])

    if any(hint in text for hint in _EATING_HINTS):
        return "美食"

    cleaned = re.sub(r"\d+\s*(?:元|块|rmb|RMB|块钱)", "", text)
    cleaned = re.sub(r"\d{2,5}", "", cleaned)  # 剥离裸数字（通常是预算/人数残留）
    for word in _NOISE_WORDS:
        cleaned = cleaned.replace(word, "")
    cleaned = re.sub(r"[，。！？、,.!?；;:：\s]+", " ", cleaned).strip()

    return cleaned if len(cleaned) >= 2 else (query or "").strip()


def build_search_query(query: str, address: str) -> str:
    """组装适合搜索引擎的 Query（本地生活场景：位置 + 品类 + 人均/评分）。"""
    core = extract_keywords(query)
    prefix = address or ""
    # 地址太长（如 OSM 返回的完整串）时只取前两段，避免 Query 过长导致召回发散
    prefix = " ".join(prefix.split(",")[:2]).strip()
    parts = [p for p in [prefix, core, "人均 评分 推荐"] if p]
    return " ".join(parts).strip()


# ============================================================
#  规则兜底：大模型不可用时，用同一套口径自己算性价比
# ============================================================
def _score_place(place: Place, budget: float) -> Optional[Dict[str, object]]:
    """与 System Prompt 里定义的口径保持一致，方便评委对照。"""
    if place.avg_cost and place.avg_cost > budget:
        return None  # 超预算直接剔除

    rating_part = ((place.rating / 5.0) * 50) if place.rating else 40.0

    if place.avg_cost:
        ratio = min(place.avg_cost / budget, 1.0)
        price_part = 35 * (1 - ratio * 0.5)
    else:
        price_part = 20.0

    if place.distance_m is None:
        distance_part = 8.0
    else:
        km = place.distance_m / 1000.0
        distance_part = 15.0 if km <= 1 else max(0.0, 15 - (km - 1) * 3)

    total = rating_part + price_part + distance_part
    return {
        "place": place,
        "score": round(total, 1),
        "rating_part": round(rating_part, 1),
        "price_part": round(price_part, 1),
        "distance_part": round(distance_part, 1),
    }


def _fallback_markdown(
    query: str,
    location: dict,
    places: List[Place],
    budget: float,
    provider_label: str,
    reason: str,
    user_profile: dict = None,
) -> str:
    """规则兜底也输出 CoT 三段式，保证无 API Key 演示时评委同样能看到思考链。"""
    user_profile = user_profile or {}
    transport = user_profile.get("transport") or "步行/骑行"
    people = int(user_profile.get("people") or 2)
    has_coupon = bool(user_profile.get("has_coupon"))
    with_kids = bool(user_profile.get("with_kids"))

    # 打分 + 记录被剔除的超预算项（思考链需要展示剔除过程）
    all_scored, rejected = [], []
    for p in places:
        s = _score_place(p, budget)
        if s:
            all_scored.append(s)
        elif p.avg_cost and p.avg_cost > budget:
            rejected.append(p)
    all_scored.sort(key=lambda item: item["score"], reverse=True)
    scored = all_scored[:5]

    head = (
        f"> ⚙️ 当前未接入大模型（{reason}），以下由规则引擎按**同一套性价比口径**计算，"
        f"并模拟了 Agent 思考链。数据来源：{provider_label}。\n"
    )

    if not scored:
        return head + (
            f"\n### 🤔 我的思考过程\n"
            f"1. **理解需求**：{query}，人均预算 {budget:.0f} 元。\n"
            f"2. **剔除不合适选项**：检索到 {len(places)} 家候选，"
            f"其中 {len(rejected)} 家超预算被剔除，剩余 0 家在预算内。\n"
            f"3. **结论**：没有找到符合预算的方案。\n\n"
            f"### 🏆 最终推荐方案\n"
            f"**未获取到**预算内的候选商家。建议把预算提高到 {budget * 1.5:.0f} 元左右，或换个品类试试。\n\n"
            f"### 💰 真实花费预估\n无法计算（无可用候选）。\n"
        )

    # ---- 🤔 思考过程 ----
    think_lines = [
        f"1. **理解需求**：{query}，人均预算 {budget:.0f} 元，{transport}出行"
        + ("，带小孩" if with_kids else "") + "。",
        f"2. **剔除不合适选项**：共检索到 {len(places)} 家候选——",
    ]
    for p in rejected:
        think_lines.append(
            f"   - {p.name}：人均 {p.avg_cost:.0f} 元 > 预算 {budget:.0f} 元，**超预算剔除**。")
    if not rejected:
        think_lines.append(f"   - 全部 {len(places)} 家均在预算内，无需剔除。")
    think_lines.append(f"3. **计算真实花费**：以人均 × {people} 人 + {transport}费估算。")
    think_lines.append(
        f"4. **排序得出结论**：剩余 {len(all_scored)} 家按性价比分排序，"
        f"第一名 {scored[0]['place'].name}（{scored[0]['score']} 分）胜出。")

    # ---- 🏆 推荐方案 ----
    best = scored[0]
    best_place = best["place"]
    rec_lines = [f"**{best_place.name}**（性价比分 {best['score']}）"]
    if best_place.rating:
        rec_lines.append(f"- 评分 {best_place.rating:.1f} 分，品质得分项 {best['rating_part']}/50")
    if best_place.avg_cost:
        rec_lines.append(f"- 人均 {best_place.avg_cost:.0f} 元，价格得分项 {best['price_part']}/35")
    if best_place.distance_m is not None:
        rec_lines.append(f"- {best_place.to_dict()['distance_text']}，距离得分项 {best['distance_part']}/15")
    if with_kids:
        rec_lines.append(f"- 适合带小孩前往")
    if len(scored) > 1:
        sp = scored[1]["place"]
        rec_lines.append(
            f"\n备选：**{sp.name}**（性价比分 {scored[1]['score']}），人均 "
            f"{f'{sp.avg_cost:.0f}元' if sp.avg_cost else '未获取到'}，"
            f"评分 {f'{sp.rating:.1f}' if sp.rating else '未获取到'}。")

    # ---- 💰 花费预估 ----
    cost = best_place.avg_cost or budget
    food_total = cost * people
    if "打车" in transport:
        traffic_fee = 15
    elif "地铁" in transport or "公交" in transport:
        traffic_fee = 4
    else:
        traffic_fee = 0
    coupon = 20 if (has_coupon and food_total >= 200) else (10 if has_coupon else 0)
    real_total = food_total + traffic_fee - coupon
    dist_text = best_place.to_dict()["distance_text"] if best_place.distance_m is not None else "未知"
    cost_lines = [
        "> 真实花费 = 人均 × 人数 + 交通费 - 优惠",
        "",
        f"- 人均 {cost:.0f} 元 × {people} 人 = {food_total:.0f} 元",
        f"- {transport}费约 {traffic_fee} 元（距离 {dist_text} 估算）",
        f"- 优惠券抵扣：{'-' + str(coupon) + ' 元' if coupon else '无'}",
        f"- **真实花费 ≈ {real_total:.0f} 元**",
    ]

    return head + (
        f"\n### 🤔 我的思考过程\n" + "\n".join(think_lines) + "\n\n"
        f"### 🏆 最终推荐方案\n" + "\n".join(rec_lines) + "\n\n"
        f"### 💰 真实花费预估\n" + "\n".join(cost_lines) + "\n"
    )


# ============================================================
#  API
# ============================================================
@api_bp.get("/health")
def health():
    return jsonify({"status": "ok", "service": "zhitu-consumer-agent", "time": int(time.time())})


# ============================================================
#  用户消费记录（我的消费记录）CRUD
# ============================================================
@api_bp.get("/records")
def records_list():
    """列出全部用户消费记录（按录入时间倒序）。"""
    return jsonify({"ok": True, "records": user_db.list_records()})


@api_bp.post("/records")
def records_add():
    """
    新增一条消费记录。
    请求体 JSON:
      { "name": "老李川菜馆", "address": "武侯区科华北路12号",
        "people": 3, "avg_cost": 85, "total_cost": 255, "comment": "4.5" }
    """
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "饭店名称不能为空"}), 400

    def _num(key):
        v = payload.get(key)
        if v is None or v == "":
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    people = _num("people")
    avg_cost = _num("avg_cost")
    total_cost = _num("total_cost")
    try:
        record = user_db.add_record(
            name=name,
            address=(payload.get("address") or "").strip(),
            people=int(people) if people else None,
            avg_cost=avg_cost,
            total_cost=total_cost,
            comment=(payload.get("comment") or "").strip(),
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "record": record})


@api_bp.delete("/records/<record_id>")
def records_delete(record_id: str):
    """按 id 删除一条消费记录。"""
    ok = user_db.delete_record(record_id)
    if not ok:
        return jsonify({"ok": False, "error": "记录不存在或已删除"}), 404
    return jsonify({"ok": True})


@api_bp.get("/agent/status")
def agent_status():
    """配置自检：一眼看出哪个 Key 没配、当前走哪条链路。"""
    llm_state = llm.health()
    channels = Config.search_ready()
    return jsonify({
        "llm": llm_state,
        "search": {
            "provider": "我的消费记录(亲测优先) → 高德地图 → DDG/OSM联网 → Mock兜底",
            "available": channels,
            "note": "搜索时优先匹配「我的消费记录」中用户亲测过的店；其余按 高德POI(配AMAP_KEY) → DDG/OSM联网 → Mock兜底 依次补充",
        },
        "budget_default": Config.DEFAULT_BUDGET,
    })


@api_bp.post("/agent/recommend")
def recommend():
    """
    请求体 JSON:
      {
        "query":   "周末想去周边吃顿好的，预算100",   # 必填
        "lat":     30.659,                            # 二选一：浏览器定位
        "lng":     104.063,
        "address": "成都市武侯区"                      # 二选一：手动地址兜底
      }
    响应体 JSON:
      {
        "ok": true,
        "answer": "<Markdown 文本>",
        "places": [ {name, rating, avg_cost, distance_text, source, ...} ],
        "location": {...},
        "meta": { "llm": "...", "search_provider": "...", "elapsed_ms": 1234, "fallback": false }
      }
    """
    started = time.time()
    payload = request.get_json(silent=True) or {}

    query = (payload.get("query") or "").strip()
    if not query:
        return jsonify({"ok": False, "error": "请先输入你的需求，例如：附近性价比高的川菜"}), 400

    lat = _to_float(payload.get("lat"))
    lng = _to_float(payload.get("lng"))
    address = (payload.get("address") or "").strip()

    # 智能体化：多轮对话历史 + 个性化参数
    chat_history = payload.get("chat_history") or []
    if not isinstance(chat_history, list):
        chat_history = []
    user_profile = payload.get("user_profile") or {}
    if not isinstance(user_profile, dict):
        user_profile = {}

    # 前端开关：AI深度思考（关闭则跳过大模型，规则兜底秒回）
    llm_enabled = payload.get("llm_enabled", True)
    # 前端开关：联网搜索（关闭则跳过DDG/OSM，纯Mock数据）
    web_search_enabled = payload.get("web_search_enabled", True)
    # 前端运行时LLM配置（网页设置面板填入的 API Key / 模型 / Base URL）
    llm_config = payload.get("llm_config") or {}
    if not isinstance(llm_config, dict):
        llm_config = {}

    if (lat is None or lng is None) and not address:
        return jsonify({
            "ok": False,
            "error": "需要先定位：请点击「获取当前位置」，或在下方手动输入地点（如：成都市武侯区）",
        }), 400

    # ① 定位归一化
    location = geo.resolve_location(lat, lng, address)
    budget = parse_budget(query)

    # ② 组装搜索词 + ③ 获取候选商家数据
    search_query = build_search_query(query, location.get("address") or "")
    keyword = extract_keywords(query) or query

    # ③ 获取候选商家数据 —— 联网搜索链：高德POI → DDG/OSM并行 → Mock兜底
    # 高德：配了 AMAP_KEY 时第一优先，真实商家+评分+人均+距离，数据最全最准
    # DDG/OSM：免费联网补充（高德未配Key或未返回足够结果时启用）
    # Mock：15品类110+条随机采样兜底，保证永远有结果
    search_errors = []
    places = []
    provider_label = ""
    osm_notes = []
    search_sources = []          # 记录命中的渠道，用于混合标注

    # ---- 第零优先：我的消费记录（用户亲测数据，最高可信度）----
    # 用户自己录入过的店，搜索时首先匹配并排在候选列表最前面，
    # 让大模型/规则引擎优先基于"真实消费体验"做推荐。
    user_record_hits = user_db.search_records(
        keyword=keyword,
        address=location.get("address") or "",
        limit=Config.SEARCH_LIMIT,
    )
    if user_record_hits:
        for rec in user_record_hits:
            places.append(user_db.record_to_place(rec))
        search_sources.append("我的消费记录")

    # ---- 第一优先：高德地图 POI 搜索（配了 AMAP_KEY 时自动启用）----
    if web_search_enabled and Config.AMAP_KEY:
        try:
            amap_places = amap_provider.search(
                keywords=keyword,
                lat=lat, lng=lng,
                address=location.get("address") or "",
                limit=Config.SEARCH_LIMIT,
                radius_m=Config.SEARCH_RADIUS_M,
            )
            if amap_places:
                places.extend(amap_places)
                search_sources.append("高德地图（联网）")
        except Exception as exc:
            search_errors.append(f"[amap] {exc}")

    # ---- 第二优先：DDG联网 + OSM周边 并行搜索（高德未返回足够结果时补充）----
    if len(places) < 3 and web_search_enabled:
        def _search_ddg():
            """DuckDuckGo 联网搜索，返回 (places, source_label, errors)。"""
            errs = []
            try:
                ddg_query = f"{location.get('address') or ''} {keyword} 大众点评 人均 评分".strip()
                ddg_places = ddg_provider.search(ddg_query, limit=Config.SEARCH_LIMIT + 3)
                ddg_clean = [
                    p for p in ddg_places
                    if "http" not in p.name and "www." not in p.name
                    and ".com" not in p.name and ".html" not in p.name
                    and ".cn" not in p.name and len(p.name) >= 2
                ]
                dropped = len(ddg_places) - len(ddg_clean)
                if dropped:
                    errs.append(f"[ddg] 过滤 {dropped} 条URL/垃圾结果")
                if ddg_clean:
                    ddg_clean.sort(key=lambda p: (p.rating is None and p.avg_cost is None,))
                    return ddg_clean[:Config.SEARCH_LIMIT], "DuckDuckGo 联网", errs
                return [], "", errs
            except Exception as exc:
                errs.append(f"[ddg] {exc}")
                return [], "", errs

        def _search_osm():
            """OSM 真实周边搜索，返回 (places, source_label, notes, errors)。"""
            if not (Config.OSM_SEARCH_ENABLED and lat is not None and lng is not None):
                return [], "", [], []
            try:
                osm_places, notes = osm_provider.search(
                    keyword=keyword,
                    lat=lat, lng=lng,
                    address=location.get("address") or "",
                    limit=Config.SEARCH_LIMIT,
                    radius_m=Config.SEARCH_RADIUS_M,
                )
                if osm_places:
                    return osm_places, "OSM 真实周边", notes, []
                return [], "", notes, []
            except Exception as exc:
                return [], "", [], [f"[osm] {exc}"]

        # 不用 with 上下文（退出时会等线程跑完导致超时后仍卡住），shutdown(wait=False) 立即放行
        _pool = ThreadPoolExecutor(max_workers=2)
        try:
            _ddg_future = _pool.submit(_search_ddg)
            _osm_future = _pool.submit(_search_osm)
            _ddg_places, _ddg_label, _ddg_errs = _ddg_future.result()
            _osm_places, _osm_label, _osm_notes, _osm_errs = _osm_future.result()
        finally:
            _pool.shutdown(wait=False)

        search_errors.extend(_ddg_errs)
        search_errors.extend(_osm_errs)
        osm_notes = _osm_notes
        if _ddg_places:
            places.extend(_ddg_places)
            search_sources.append(_ddg_label)
        if _osm_places:
            places.extend(_osm_places)
            search_sources.append(_osm_label)

    # 去重合并（DDG+OSM可能有同名店）
    if places:
        places = dedupe(places)[:Config.SEARCH_LIMIT]

    # ---- 第三优先：Mock 数据池随机采样（补充/兜底）----
    if len(places) < 3:
        raw_places = get_mock_places(location.get("address") or "", keyword,
                                      sample_size=Config.SEARCH_LIMIT)
        mock_places = _mock_to_places(raw_places)
        if places:
            existing_names = {p.name for p in places}
            for mp in mock_places:
                if mp.name not in existing_names and len(places) < Config.SEARCH_LIMIT:
                    places.append(mp)
            search_sources.append("离线数据")
        else:
            places = mock_places
            search_sources.append("离线数据")

    # 拼装 provider_label
    if search_sources:
        provider_label = " + ".join(search_sources)
    else:
        provider_label = "离线演示数据（Mock·随机采样）"

    # ④⑤ 构造 Prompt 并调用大模型；失败（或用户关闭）则规则兜底
    fallback = False
    fallback_reason = ""
    if not llm_enabled:
        # 用户关闭了 AI 深度思考：跳过大模型，规则兜底秒回
        fallback = True
        fallback_reason = "用户关闭了 AI 深度思考（规则引擎快速响应）"
        answer = _fallback_markdown(query, location, places, budget, provider_label, fallback_reason,
                                    user_profile=user_profile)
        llm_label = "规则引擎（快速模式）"
    else:
        try:
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(
                    query, location, places, budget, provider_label,
                    chat_history=chat_history, user_profile=user_profile)},
            ]
            result = llm.chat(messages, runtime=llm_config)
            answer = result["content"]
            llm_label = result["model_label"]
        except Exception as exc:  # 任何大模型异常（含未预期错误）都不该让接口 500，统一走规则兜底
            fallback = True
            fallback_reason = str(exc) or exc.__class__.__name__
            answer = _fallback_markdown(query, location, places, budget, provider_label, fallback_reason,
                                        user_profile=user_profile)
            llm_label = "规则引擎（兜底）"

    return jsonify({
        "ok": True,
        "answer": answer,
        "places": [p.to_dict() for p in places],
        "location": location,
        "budget": budget,
        "meta": {
            "llm": llm_label,
            "search_provider": provider_label,
            "search_query": search_query,
            "search_errors": search_errors,
            "search_notes": osm_notes,
            "llm_enabled": llm_enabled,
            "web_search_enabled": web_search_enabled,
            "fallback": fallback,
            "fallback_reason": fallback_reason,
            "elapsed_ms": int((time.time() - started) * 1000),
        },
    })
