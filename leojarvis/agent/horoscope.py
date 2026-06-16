"""星座运势胶囊 —— 离线、确定性、可缓存。

设计原则（照抄 cli_agents 的声明式 + 纯函数 + 返回 dict 模式）：
  - 不依赖外部网络 / LLM 也能跑：用「日期 + 星座」做确定性种子
    （hashlib.sha256 对 f"{sign}{date}" 取摘要）派生当天运势。
  - 同一天同一星座结果稳定 —— 便于验证，也便于当天缓存。
  - 中文输出；支持中文 / 英文星座名（做映射）。

对外函数：
  horoscope(sign, date=None) -> dict   单个星座当天运势（工具 + REST 用）
  all_today(date=None)      -> list    12 星座当天一句话概览（晨间简报"生活段"用）
"""

from __future__ import annotations

import datetime as _dt
import hashlib
from typing import Any

# 12 星座规范名（中文）+ 别名映射（中文别名 / 英文 / 符号）→ 规范中文名。
# 规范名用两字简称（白羊…），与任务给的中文星座名一致。
_SIGNS: list[str] = [
    "白羊", "金牛", "双子", "巨蟹", "狮子", "处女",
    "天秤", "天蝎", "射手", "摩羯", "水瓶", "双鱼",
]

# 规范名 -> 英文名（展示用）。
_EN: dict[str, str] = {
    "白羊": "Aries", "金牛": "Taurus", "双子": "Gemini", "巨蟹": "Cancer",
    "狮子": "Leo", "处女": "Virgo", "天秤": "Libra", "天蝎": "Scorpio",
    "射手": "Sagittarius", "摩羯": "Capricorn", "水瓶": "Aquarius", "双鱼": "Pisces",
}

# 各种写法 -> 规范名。键统一小写处理。
_ALIASES: dict[str, str] = {}


def _register_aliases() -> None:
    for cn in _SIGNS:
        en = _EN[cn]
        forms = {
            cn, cn + "座", cn + "宫",
            en, en.lower(),
        }
        # 常见全称中文别名
        forms |= {
            {
                "白羊": "牡羊", "金牛": "金牛", "双子": "双子", "巨蟹": "巨蟹",
                "狮子": "狮子", "处女": "室女", "天秤": "天平", "天蝎": "天蝎",
                "射手": "人马", "摩羯": "山羊", "水瓶": "宝瓶", "双鱼": "双鱼",
            }[cn],
        }
        for f in forms:
            _ALIASES[f.lower()] = cn
            _ALIASES[(f + "座").lower()] = cn


_register_aliases()

_LUCKY_COLORS = [
    "正红", "天青", "明黄", "墨绿", "藕粉", "靛蓝", "象牙白",
    "珊瑚橙", "薰衣草紫", "石墨灰", "薄荷绿", "酒红", "金棕", "湖蓝",
]

# 综合评分分档 -> (标签, 宜, 忌, 一句话建议池)。
_BANDS: list[dict[str, Any]] = [
    {
        "min": 85, "label": "极佳",
        "yi": ["主动出击", "签约谈判", "表白告白", "启动新计划"],
        "ji": ["犹豫拖延", "闷头独处"],
        "tips": [
            "今天气场全开，该争取的别客气。",
            "状态在线，把搁置很久的大事推一把。",
            "好运在背后推你，大胆做决定。",
        ],
    },
    {
        "min": 70, "label": "顺遂",
        "yi": ["推进项目", "约见朋友", "整理复盘", "学习充电"],
        "ji": ["冲动消费", "钻牛角尖"],
        "tips": [
            "节奏稳、贵人近，按计划走就好。",
            "顺风局，专注手头事会有小惊喜。",
            "沟通顺畅，多表达需求会被听见。",
        ],
    },
    {
        "min": 55, "label": "平稳",
        "yi": ["按部就班", "补觉养神", "处理杂务", "运动出汗"],
        "ji": ["重大决策", "对外承诺"],
        "tips": [
            "普通的一天，守住基本盘别折腾。",
            "宜静不宜动，把节奏放慢一点。",
            "把待办清掉，别给明天留尾巴。",
        ],
    },
    {
        "min": 40, "label": "略低",
        "yi": ["低调行事", "多听少说", "提前备份", "深呼吸"],
        "ji": ["争执口角", "签字画押", "熬夜"],
        "tips": [
            "能量偏低，遇事先缓三秒再回应。",
            "今天容易踩雷，重要的事往后挪一挪。",
            "照顾好情绪，给自己留点余地。",
        ],
    },
    {
        "min": 0, "label": "蛰伏",
        "yi": ["休息复位", "断舍离", "独处冥想", "早点睡"],
        "ji": ["对外冲突", "重大投入", "钻死胡同"],
        "tips": [
            "低谷期，今天主打一个'稳'字。",
            "别和自己较劲，养精蓄锐要紧。",
            "把期待调低，安稳过完就是赢。",
        ],
    },
]


def _today() -> str:
    return _dt.date.today().isoformat()


def normalize_sign(sign: str) -> str | None:
    """把各种写法的星座名归一到规范中文名；无法识别返回 None。"""
    if not sign:
        return None
    key = str(sign).strip().lower()
    if key in _ALIASES:
        return _ALIASES[key]
    # 容错：去掉尾部"座/宫"再试
    for suffix in ("座", "宫"):
        if key.endswith(suffix) and key[: -len(suffix)] in _ALIASES:
            return _ALIASES[key[: -len(suffix)]]
    return None


def _digest_ints(sign_cn: str, date: str) -> list[int]:
    """确定性种子：sha256(f"{sign}{date}") -> 一串 0-255 的整数，供各字段取用。"""
    raw = hashlib.sha256(f"{sign_cn}{date}".encode("utf-8")).digest()
    return list(raw)


def _band_for(score: int) -> dict[str, Any]:
    for band in _BANDS:
        if score >= band["min"]:
            return band
    return _BANDS[-1]


def _pick(pool: list[Any], n: int) -> list[Any]:
    seq = list(pool)
    return seq[n % len(seq)] if seq else None


def horoscope(sign: str, date: str | None = None) -> dict:
    """返回某星座当天运势（确定性、离线）。

    结构：{ok, sign, sign_en, date, score, level, lucky_color, lucky_number,
            advice, yi(list), ji(list), summary}
    同一天同一星座结果稳定。
    """
    cn = normalize_sign(sign)
    if not cn:
        return {
            "ok": False,
            "error": f"无法识别的星座: {sign}",
            "valid_signs": list(_SIGNS),
        }
    day = (date or _today()).strip()
    b = _digest_ints(cn, day)

    # 综合评分 0-100：用两个字节合成，分布更平滑（避免只用一字节集中在 0-255 边角）。
    score = int(((b[0] << 8 | b[1]) / 65535) * 100)
    band = _band_for(score)

    lucky_color = _LUCKY_COLORS[b[2] % len(_LUCKY_COLORS)]
    lucky_number = b[3] % 10  # 0-9 幸运数字
    advice = _pick(band["tips"], b[4])
    # 宜/忌各取两条（确定性、去重）。
    yi_pool, ji_pool = band["yi"], band["ji"]
    yi = sorted({yi_pool[b[5] % len(yi_pool)], yi_pool[b[6] % len(yi_pool)]})
    ji = sorted({ji_pool[b[7] % len(ji_pool)], ji_pool[b[8] % len(ji_pool)]})

    summary = f"{cn}座 · {band['label']}（{score}分）· 幸运色{lucky_color} · {advice}"
    return {
        "ok": True,
        "sign": cn,
        "sign_en": _EN[cn],
        "date": day,
        "score": score,
        "level": band["label"],
        "lucky_color": lucky_color,
        "lucky_number": lucky_number,
        "advice": advice,
        "yi": yi,
        "ji": ji,
        "summary": summary,
    }


def all_today(date: str | None = None) -> list[dict]:
    """12 星座当天一句话概览，给晨间简报"生活段"用。

    每条：{sign, sign_en, score, level, one_liner}。按星座固定顺序，离线确定性。
    """
    day = (date or _today()).strip()
    out: list[dict] = []
    for cn in _SIGNS:
        h = horoscope(cn, day)
        out.append({
            "sign": h["sign"],
            "sign_en": h["sign_en"],
            "score": h["score"],
            "level": h["level"],
            "one_liner": f"{cn}座 {h['score']}分 · {h['advice']}",
        })
    return out
