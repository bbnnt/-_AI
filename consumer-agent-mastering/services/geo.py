"""
定位服务：把「浏览器经纬度」或「用户手输地址」统一成一个可读的地点描述。

逆地理编码优先级：
1. 高德 regeo（配了 AMAP_KEY 时，国内地址最准）
2. OSM Nominatim（免费、无需 Key，作为兜底；有速率限制，仅 demo 用）
3. 本地城市坐标库（离线，国内主要城市，OSM 不可达时保证有可读地名）
4. 都失败 -> 退化成 "纬度,经度"
"""
import math
from typing import Dict, Optional

import requests

from config import Config

_UA = "consumer-agent-demo/1.0 (competition demo)"

# ============================================================
#  本地城市坐标库（离线兜底）
#  OSM Nominatim 在国内网络经常超时/被墙，导致定位退化成纯坐标。
#  这里内置主要城市坐标，用简化距离公式找最近城市，保证前端
#  至少能看到「XX市」这种可读地名，而不是一串数字。
#  数据来源：各城市市政府/地标的大致经纬度（演示精度足够）。
# ============================================================
_LOCAL_CITIES = [
    # (纬度, 经度, 城市名)
    (39.9042, 116.4074, "北京市"),
    (31.2304, 121.4737, "上海市"),
    (23.1291, 113.2644, "广州市"),
    (22.5431, 114.0579, "深圳市"),
    (30.5728, 104.0668, "成都市"),
    (29.5630, 106.5516, "重庆市"),
    (30.2741, 120.1551, "杭州市"),
    (30.5928, 114.3055, "武汉市"),
    (34.3416, 108.9398, "西安市"),
    (32.0603, 118.7969, "南京市"),
    (39.3434, 117.3616, "天津市"),
    (31.2989, 120.5853, "苏州市"),
    (28.2282, 112.9388, "长沙市"),
    (34.7466, 113.6254, "郑州市"),
    (36.0671, 120.3826, "青岛市"),
    (41.8057, 123.4315, "沈阳市"),
    (38.9140, 121.6147, "大连市"),
    (45.8038, 126.5349, "哈尔滨市"),
    (43.8171, 125.3235, "长春市"),
    (36.6512, 117.1201, "济南市"),
    (31.8206, 117.2272, "合肥市"),
    (26.0745, 119.2965, "福州市"),
    (24.4798, 118.0894, "厦门市"),
    (24.8801, 102.8329, "昆明市"),
    (26.6470, 106.6302, "贵阳市"),
    (22.8170, 108.3669, "南宁市"),
    (36.0611, 103.8343, "兰州市"),
    (43.8256, 87.6168, "乌鲁木齐市"),
    (29.6500, 91.1000, "拉萨市"),
    (38.4872, 106.2309, "银川市"),
    (36.6171, 101.7782, "西宁市"),
    (20.0444, 110.1990, "海口市"),
    (18.2528, 109.5119, "三亚市"),
    (37.8706, 112.5489, "太原市"),
    (38.0428, 114.5149, "石家庄市"),
    (40.8426, 111.7492, "呼和浩特市"),
    (28.6820, 115.8579, "南昌市"),
    (31.4912, 120.3119, "无锡市"),
    (29.8683, 121.5440, "宁波市"),
    (27.9938, 120.6994, "温州市"),
    (23.0218, 113.1219, "佛山市"),
    (23.0207, 113.7518, "东莞市"),
    (22.2707, 113.5767, "珠海市"),
    (37.4638, 121.4479, "烟台市"),
    (24.8741, 118.6757, "泉州市"),
]


def _nearest_city(lat: float, lng: float, max_km: float = 80.0) -> Optional[str]:
    """
    用简化平面距离估算找最近城市，超过 max_km 视为不匹配返回 None。
    演示场景下精度足够（城市间距离通常 >150km，不会误判）。
    """
    best, best_d = None, max_km
    cos_lat = math.cos(math.radians(lat))
    for c_lat, c_lng, name in _LOCAL_CITIES:
        # 纬度 1°≈111km，经度 1°≈111km×cos(纬度)
        d = math.hypot((lat - c_lat) * 111.0, (lng - c_lng) * 111.0 * cos_lat)
        if d < best_d:
            best, best_d = name, d
    return best


def reverse_geocode(lat: float, lng: float) -> Dict[str, str]:
    if Config.AMAP_KEY:
        try:
            resp = requests.get(
                "https://restapi.amap.com/v3/geocode/regeo",
                params={
                    "key": Config.AMAP_KEY,
                    "location": f"{lng:.6f},{lat:.6f}",
                    "extensions": "base",
                },
                timeout=Config.AMAP_TIMEOUT,
            )
            data = resp.json()
            if str(data.get("status")) == "1":
                regeo = data.get("regeocode") or {}
                formatted = regeo.get("formatted_address") or ""
                if formatted:
                    return {"address": formatted, "source": "高德逆地理"}
        except (requests.RequestException, ValueError):
            pass  # 静默降级

    try:
        resp = requests.get(
            f"{Config.NOMINATIM_URL.rstrip('/')}/reverse",
            params={"lat": lat, "lon": lng, "format": "json", "accept-language": "zh-CN"},
            headers={"User-Agent": _UA},
            timeout=Config.SEARCH_TIMEOUT,
        )
        data = resp.json()
        address = (data.get("display_name") or "").strip()
        if address:
            return {"address": address, "source": "OSM Nominatim"}
    except (requests.RequestException, ValueError):
        pass

    # 第三级兜底：本地城市坐标库（离线，不依赖网络）
    city = _nearest_city(lat, lng)
    if city:
        return {"address": f"{city}（附近）", "source": "本地城市库"}

    return {"address": f"{lat:.5f},{lng:.5f}", "source": "坐标"}


def resolve_location(
    lat: Optional[float],
    lng: Optional[float],
    address: str = "",
) -> Dict[str, Optional[str]]:
    """
    归一化定位信息，前端拿到的 location 字段就来自这里。
    返回 {lat, lng, address, source}
    """
    if lat is not None and lng is not None:
        # 已有手动地址时跳过逆地理编码——省 6s 网络等待，演示更流畅
        if address and len(address) >= 3:
            return {"lat": lat, "lng": lng, "address": address, "source": "手动输入"}
        geo = reverse_geocode(lat, lng)
        return {
            "lat": lat,
            "lng": lng,
            "address": geo["address"] or address,
            "source": geo["source"],
        }
    return {
        "lat": None,
        "lng": None,
        "address": address,
        "source": "手动输入",
    }
