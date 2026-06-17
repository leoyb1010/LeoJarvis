"""高德地图能力 —— 地理编码 / 逆地理 / POI 搜索 / 天气 / 路线规划。

走高德 Web 服务 REST API（已实测 key 有效）。key 优先从 config/settings.toml [amap].key，
回退环境变量 AMAP_MAPS_API_KEY / AMAP_API_KEY / GAODE_API_KEY。
自然语言经 ToolBus 注册的 map_* 工具调用；前端小地图用 /api/amap/config 取 JS key。
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

from ..config import settings

_BASE = "https://restapi.amap.com/v3"


def key() -> str:
    k = (settings().get("amap", {}) or {}).get("key", "")
    return (
        k
        or os.environ.get("AMAP_MAPS_API_KEY")
        or os.environ.get("AMAP_API_KEY")
        or os.environ.get("GAODE_API_KEY")
        or ""
    )


def js_key() -> str:
    """前端 JS API key：未单独配置则复用 Web 服务 key。"""
    amap = settings().get("amap", {}) or {}
    return amap.get("js_key") or key()


def configured() -> bool:
    return bool(key())


def _get(path: str, params: dict) -> dict:
    k = key()
    if not k:
        return {"ok": False, "error": "未配置高德 key（config/settings.toml [amap].key）"}
    q = {**{kk: vv for kk, vv in params.items() if vv is not None}, "key": k, "output": "JSON"}
    url = f"{_BASE}{path}?{urllib.parse.urlencode(q)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "LeoJarvis/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"高德请求失败: {exc}"}
    if str(data.get("status")) != "1":
        return {"ok": False, "error": data.get("info") or "高德返回失败", "raw": data}
    return {"ok": True, **data}


def geocode(address: str, city: str | None = None) -> dict:
    """地址 → 经纬度 + 行政区 + adcode。"""
    d = _get("/geocode/geo", {"address": address, "city": city})
    if not d.get("ok"):
        return d
    g = (d.get("geocodes") or [{}])[0]
    return {
        "ok": True,
        "location": g.get("location"),
        "formatted_address": g.get("formatted_address"),
        "province": g.get("province"),
        "city": g.get("city"),
        "district": g.get("district"),
        "adcode": g.get("adcode"),
    }


def regeocode(location: str) -> dict:
    """经纬度(lng,lat) → 结构化地址。"""
    d = _get("/geocode/regeo", {"location": location})
    if not d.get("ok"):
        return d
    rg = (d.get("regeocode") or {})
    return {"ok": True, "formatted_address": rg.get("formatted_address"), "addressComponent": rg.get("addressComponent")}


def poi_search(keywords: str, city: str | None = None, limit: int = 8) -> dict:
    """关键字 POI 搜索（咖啡 / 充电站 / 地铁站…）。"""
    d = _get("/place/text", {"keywords": keywords, "city": city, "offset": max(1, min(25, limit)), "page": 1})
    if not d.get("ok"):
        return d
    pois = []
    for p in (d.get("pois") or [])[:limit]:
        pois.append({
            "name": p.get("name"),
            "address": p.get("address"),
            "location": p.get("location"),
            "type": p.get("type"),
            "tel": p.get("tel") or "",
            "distance": p.get("distance") or "",
        })
    return {"ok": True, "count": d.get("count"), "pois": pois}


def weather(city: str) -> dict:
    """城市天气（实况 + 4 天预报）。city 可是名称或 adcode，名称会先地理编码取 adcode。"""
    adcode = city
    if not str(city).isdigit():
        g = geocode(city)
        if not g.get("ok") or not g.get("adcode"):
            return {"ok": False, "error": f"无法定位城市: {city}"}
        adcode = g["adcode"]
    live = _get("/weather/weatherInfo", {"city": adcode, "extensions": "base"})
    fc = _get("/weather/weatherInfo", {"city": adcode, "extensions": "all"})
    if not live.get("ok"):
        return live
    cur = (live.get("lives") or [{}])[0]
    casts = ((fc.get("forecasts") or [{}])[0].get("casts") or []) if fc.get("ok") else []
    return {
        "ok": True,
        "city": cur.get("city"),
        "weather": cur.get("weather"),
        "temperature": cur.get("temperature"),
        "winddirection": cur.get("winddirection"),
        "windpower": cur.get("windpower"),
        "humidity": cur.get("humidity"),
        "reporttime": cur.get("reporttime"),
        "forecast": [
            {"date": c.get("date"), "day": c.get("dayweather"), "night": c.get("nightweather"),
             "temp": f"{c.get('nighttemp')}~{c.get('daytemp')}°C"}
            for c in casts[:4]
        ],
    }


def route(origin: str, destination: str, mode: str = "driving") -> dict:
    """路线规划。origin/destination 支持「经纬度」或「地址」（地址自动地理编码）。
    mode: driving(驾车) / walking(步行) / bicycling(骑行) / transit(公交，需城市)。"""
    def _resolve(x: str) -> str | None:
        if "," in x and all(part.replace(".", "").replace("-", "").isdigit() for part in x.split(",")[:2]):
            return x
        g = geocode(x)
        return g.get("location") if g.get("ok") else None

    o = _resolve(origin)
    de = _resolve(destination)
    if not o or not de:
        return {"ok": False, "error": "起点或终点无法定位"}
    path_map = {"driving": "/direction/driving", "walking": "/direction/walking",
                "bicycling": "/direction/bicycling", "transit": "/direction/transit/integrated"}
    d = _get(path_map.get(mode, "/direction/driving"), {"origin": o, "destination": de})
    if not d.get("ok"):
        return d
    rt = d.get("route") or {}
    paths = rt.get("paths") or rt.get("transits") or []
    if not paths:
        return {"ok": False, "error": "未找到路线"}
    p = paths[0]
    dist_m = int(p.get("distance") or 0)
    dur_s = int(p.get("duration") or 0)
    return {
        "ok": True,
        "mode": mode,
        "origin": o,
        "destination": de,
        "distance_km": round(dist_m / 1000, 1),
        "duration_min": round(dur_s / 60),
        "tolls": p.get("tolls"),
    }
