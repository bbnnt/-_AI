"""
DuckDuckGo 免费联网搜索（无需 API Key）

两级实现，互为备份：
1. 装了 ddgs / duckduckgo_search 库 -> 用官方封装（推荐）
2. 没装库 -> 用 requests 抓 html.duckduckgo.com（纯标准库逆袭，零依赖）

返回结果会尽量从网页摘要里抽出「评分 / 人均 / 距离」，抽不到就留空，
由大模型结合上下文判断，绝不编造数字。
"""
import re
from typing import List, Optional
from urllib.parse import unquote, urlparse, parse_qs
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

import requests

from config import Config
from .base import Place, SearchUnavailable, parse_rating, parse_cost, parse_distance

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
)

# 明显不是「商家/门店」的结果：视频站、地图首页、政务站等，过滤掉避免污染推荐
_JUNK_DOMAINS = (
    "youtube.com", "youtu.be", "bilibili.com", "map.baidu.com",
    "amap.com", "gov.cn", "weibo.com", "douyin.com", "tieba.baidu.com",
)
_JUNK_TITLE_HINTS = (
    "watch?v=", "哔哩哔哩", "bilibili", "- youtube", "【视频】", "直播", "完整版",
    # 资讯/攻略页特征：商家名不会长这样
    "怎么", "如何", "清单", "攻略", "免费", "下载", "排行榜", "top10", "top 10",
    "？", "?",
)


def _is_junk(title: str, url: str) -> bool:
    lower_url = (url or "").lower()
    lower_title = (title or "").lower()
    if any(domain in lower_url for domain in _JUNK_DOMAINS):
        return True
    if any(hint in lower_title for hint in _JUNK_TITLE_HINTS):
        return True
    # 「35家市井美食清单」这类榜单文章
    if re.search(r"\d+\s*家", title or ""):
        return True
    # 纯首页（无路径）基本不会是商家详情页，如 map.baidu.com /
    if re.match(r"^https?://[^/]+/?$", lower_url):
        return True
    return False


def _clean_title(title: str) -> str:
    """DDG 标题常带站点后缀，如 'xx火锅 - 大众点评'，取主体做店名。"""
    title = re.sub(r"\s*[-_|｜]\s*(大众点评|美团|携程|小红书|知乎|百度百科|维基百科|Trip\.com).*$", "", title)
    title = re.sub(r"^\s*(推荐|好评|【.*?】)", "", title)
    return title.strip()[:60]


def _to_place(title: str, body: str, url: str, source: str) -> Place:
    blob = f"{title} {body}"
    return Place(
        name=_clean_title(title),
        address="",
        rating=parse_rating(blob),
        avg_cost=parse_cost(blob),
        distance_m=parse_distance(blob),
        category="",
        tags=[],
        url=url,
        snippet=re.sub(r"\s+", " ", body).strip()[:220],
        source=source,
    )


def _ddgs_text_call(query: str, limit: int):
    """在子线程中执行 ddgs.text（库本身无 timeout 参数，用线程兜底防挂死）。"""
    from ddgs import DDGS  # type: ignore
    with DDGS() as ddgs:
        return list(ddgs.text(query, region=Config.DDG_REGION, max_results=max(limit * 2, 8)))


def _search_with_library(query: str, limit: int) -> List[Place]:
    DDGS = None
    try:                       # 新版包名
        from ddgs import DDGS  # type: ignore
    except ImportError:
        try:                   # 旧版包名
            from duckduckgo_search import DDGS  # type: ignore
        except ImportError:
            return []

    try:
        # ddgs 库无 timeout 参数，用线程池 + 超时兜底，防止国内网络不通时挂死
        # 注意：不能用 with 上下文（退出时会等线程跑完），必须 shutdown(wait=False)
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(_ddgs_text_call, query, limit)
        try:
            rows = future.result(timeout=Config.SEARCH_TIMEOUT)
        finally:
            executor.shutdown(wait=False)  # 超时后不等待残留线程，立即放行
    except FuturesTimeout:
        raise SearchUnavailable(f"DuckDuckGo 库调用超时（{Config.SEARCH_TIMEOUT}s），跳过联网搜索")
    except Exception as exc:   # 网络限流/被墙都归为不可用
        raise SearchUnavailable(f"DuckDuckGo 库调用失败：{exc}") from exc

    places = []
    for row in rows:
        title = row.get("title") or ""
        if not title:
            continue
        places.append(_to_place(title, row.get("body") or "", row.get("href") or "", "DuckDuckGo"))
        if len(places) >= limit:
            break
    return places


def _search_with_html(query: str, limit: int) -> List[Place]:
    """无第三方库时的兜底：解析 DDG 的无 JS HTML 版结果页。"""
    try:
        resp = requests.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query, "kl": "cn-zh"},
            headers={"User-Agent": _UA, "Accept-Language": "zh-CN,zh;q=0.9"},
            timeout=Config.SEARCH_TIMEOUT,
        )
        resp.raise_for_status()
        html = resp.text
    except requests.RequestException as exc:
        raise SearchUnavailable(f"DuckDuckGo HTML 抓取失败：{exc}") from exc

    pattern = re.compile(
        r'<a[^>]+class="result__a"[^>]*href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>'
        r'(?:.*?class="result__snippet"[^>]*>(?P<body>.*?)</a>)?',
        re.S,
    )

    places: List[Place] = []
    for match in pattern.finditer(html):
        title = re.sub(r"<[^>]+>", "", match.group("title") or "").strip()
        body = re.sub(r"<[^>]+>", "", match.group("body") or "").strip()
        href = match.group("href") or ""
        if href.startswith("//duckduckgo.com/l/"):
            qs = parse_qs(urlparse("https:" + href).query)
            href = unquote(qs.get("uddg", [href])[0])
        if not title:
            continue
        places.append(_to_place(title, body, href, "DuckDuckGo"))
        if len(places) >= limit:
            break

    if not places:
        raise SearchUnavailable("DuckDuckGo 结果解析为空（可能被限流）")
    return places


def search(query: str, limit: Optional[int] = None, **_ignored) -> List[Place]:
    limit = limit or Config.SEARCH_LIMIT

    found: List[Place] = []
    library_timed_out = False
    try:
        found = _search_with_library(query, limit)
    except SearchUnavailable as exc:
        # 库超时说明网络不通，HTML 兜底走同一网络必然也超时，跳过省 12s
        if "超时" in str(exc):
            library_timed_out = True
    if not found and not library_timed_out:
        found = _search_with_html(query, limit)

    # 过滤视频/地图首页等与「商家推荐」无关的结果
    found = [p for p in found if not _is_junk(p.name, p.url)]
    if not found:
        raise SearchUnavailable("DuckDuckGo 结果均为无关页面（视频/地图等），已全部过滤")
    return found[:limit]
