"""Restaurant retrieval and ranking for geographic, food and meal constraints."""

import asyncio
import math
import re
from datetime import date as Date
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from urllib.parse import quote

from .destinations import distance_km, gcj_to_wgs, normalize_city, wgs_to_gcj
from .models import Preferences, Restaurant
from .restaurant_data import LOCAL_CUISINE, demo_restaurants

CUISINE_ALIASES = {
    "杭帮菜": ("杭帮", "杭州菜", "浙江菜"),
    "川菜": ("川菜", "四川菜", "川味"),
    "粤菜": ("粤菜", "广东菜", "潮汕", "港式", "茶餐厅"),
    "江浙菜": ("江浙菜", "江浙", "杭帮", "浙江菜", "江苏菜", "淮扬菜", "苏帮"),
    "北京菜": ("北京菜", "京菜", "京味", "北京烤鸭", "老北京"),
    "上海菜": ("上海菜", "本帮菜", "本帮", "沪菜"),
    "东北菜": ("东北菜", "东北", "铁锅炖"),
    "日料": ("日料", "日本料理", "日式", "寿司"),
    "西餐": ("西餐", "意大利菜", "法餐", "牛排", "披萨", "汉堡"),
    "面食": ("面食", "面馆", "面条", "拉面", "饺子", "馄饨"),
    "火锅": ("火锅", "涮肉", "涮羊肉"),
    "小吃": ("小吃", "快餐", "简餐", "点心"),
}
DIET_ALIASES = {
    "素食": ("素食", "素斋", "蔬食", "斋菜", "素膳", "纯素"),
    "清真": ("清真",),
    "不辣": ("不辣", "不吃辣", "免辣"),
    "清淡": ("清淡", "少油少盐"),
    "不吃海鲜": ("不吃海鲜", "无海鲜"),
    "不吃牛肉": ("不吃牛肉", "无牛肉"),
    "不吃猪肉": ("不吃猪肉", "无猪肉"),
}
SOFT_DIETS = {"清淡", "不辣"}
WEEKDAY = {ch: i for i, ch in enumerate("一二三四五六日")}
WEEKDAY.update({"天": 6, **{str(i + 1): i for i in range(7)}})
WEEK_PATTERN = re.compile(
    r"(?:周|星期)([一二三四五六日天1-7])(?:\s*(?:至|到|[-~～—])\s*(?:周|星期)?([一二三四五六日天1-7]))?"
)
TIME_PATTERN = re.compile(
    r"(\d{1,2})[:：](\d{2})\s*(?:至|到|[-~～—])\s*(\d{1,2})[:：](\d{2})"
)


def _text(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def _positive_number(value, maximum=None):
    try:
        parsed = float(value)
    except (ValueError, TypeError):
        return None
    if not math.isfinite(parsed) or parsed <= 0:
        return None
    return parsed if maximum is None or parsed <= maximum else None


def _minute(value: str) -> int:
    hour, minute = value.split(":")
    return int(hour) * 60 + int(minute)


def _china_today() -> Date:
    return datetime.now(timezone(timedelta(hours=8))).date()


def _date(value) -> Date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, Date):
        return value
    try:
        return Date.fromisoformat(value) if value else None
    except (ValueError, TypeError):
        return None


def _canonical(values, aliases) -> list[str]:
    result = []
    for value in values:
        value = value.strip()
        name = next(
            (
                key
                for key, options in aliases.items()
                if value == key or value in options
            ),
            value,
        )
        if name and name not in result:
            result.append(name)
    return result


class DiningService:
    def __init__(self, settings, amap_async_callback):
        self.settings = settings
        self._amap = amap_async_callback

    @staticmethod
    def is_open(restaurant: Restaurant, start_time: str, end_time: str, date=None):
        """Return None for unparseable or date-inapplicable opening information."""
        text = restaurant.opening_hours.strip()
        if not text:
            return None
        planned_date = _date(date)
        today_match = re.match(r"今日\((\d{4}-\d{2}-\d{2})\)\s*", text)
        if today_match:
            if planned_date != Date.fromisoformat(today_match.group(1)):
                return None
            text = text[today_match.end() :]
        elif "今日" in text:
            return None
        if re.search(r"暂停营业|永久关闭|歇业", text):
            return False
        if re.search(r"节假日|节日|预约|另行|临时", text):
            return None
        try:
            start, end = _minute(start_time), _minute(end_time)
        except (ValueError, AttributeError):
            return None
        if end <= start:
            end += 1440
        selected = []
        for clause in re.split(r"[;；\n]", text):
            weekdays = set()
            for match in WEEK_PATTERN.finditer(clause):
                first = WEEKDAY[match.group(1)]
                last = WEEKDAY[match.group(2)] if match.group(2) else first
                weekdays.update((first + i) % 7 for i in range((last - first) % 7 + 1))
            if weekdays:
                if planned_date is None:
                    return None
                if planned_date.weekday() not in weekdays:
                    continue
                # Multiple weekday clauses without separators are ambiguous.
                first_time = TIME_PATTERN.search(clause)
                if first_time and WEEK_PATTERN.search(clause[first_time.end() :]):
                    return None
            selected.append(clause)
        if not selected:
            return None
        windows = []
        closed = False
        for clause in selected:
            if re.search(r"休息|不营业|休店|闭店", clause):
                closed = True
                continue
            if re.search(r"24\s*小时|全天|00:00\s*[-~～]\s*24:00", clause):
                return True
            for match in TIME_PATTERN.finditer(clause):
                first_h, first_m, last_h, last_m = map(int, match.groups())
                if max(first_h, last_h) > 24 or max(first_m, last_m) > 59:
                    continue
                first, last = first_h * 60 + first_m, last_h * 60 + last_m
                if last <= first:
                    last += 1440
                windows.extend(((first, last), (first - 1440, last - 1440)))
        if windows:
            return any(first <= start and end <= last for first, last in windows)
        return False if closed else None

    @staticmethod
    def _cuisines(preferences: Preferences) -> list[str]:
        local = LOCAL_CUISINE.get(normalize_city(preferences.destination))
        values = [
            local
            if value in {"本地菜", "当地菜", "当地特色", "地方菜"} and local
            else value
            for value in preferences.cuisine_preferences
        ]
        return _canonical(values, CUISINE_ALIASES)

    @staticmethod
    def _parse_poi(poi, meal_budget: float) -> Restaurant | None:
        if not isinstance(poi, dict):
            return None
        name, identifier = _text(poi.get("name")), _text(poi.get("id"))
        try:
            lon, lat = map(float, _text(poi.get("location")).split(","))
            if not all(math.isfinite(v) for v in (lat, lon)) or not (
                -90 <= lat <= 90 and -180 <= lon <= 180
            ):
                return None
            lon, lat = gcj_to_wgs(lon, lat)
        except (ValueError, TypeError):
            return None
        if not name or not identifier:
            return None
        business = poi.get("business")
        business = business if isinstance(business, dict) else {}
        description = " ".join(
            [
                name,
                _text(poi.get("type")),
                _text(business.get("tag")),
                _text(business.get("keytag")),
            ]
        )
        cuisines = [
            cuisine
            for cuisine, aliases in CUISINE_ALIASES.items()
            if cuisine in description or any(alias in description for alias in aliases)
        ]
        dietary = [
            diet
            for diet, aliases in DIET_ALIASES.items()
            if any(alias in description for alias in aliases)
        ]
        if "素食" in dietary:
            dietary.extend(["不吃海鲜", "不吃牛肉", "不吃猪肉"])
        if "清真" in dietary:
            dietary.append("不吃猪肉")
        cost = _positive_number(business.get("cost"))
        weekly = _text(business.get("opentime_week"))
        today = _text(business.get("opentime_today"))
        hours = weekly or (
            f"今日({_china_today().isoformat()}) {today}" if today else ""
        )
        return Restaurant(
            id=identifier,
            name=name,
            lat=lat,
            lon=lon,
            address="".join(
                _text(poi.get(field)) for field in ("cityname", "adname", "address")
            ),
            cuisines=cuisines,
            dietary_tags=sorted(set(dietary)),
            cost_per_person=cost if cost is not None else meal_budget,
            price_source="高德人均消费参考"
            if cost is not None
            else "按每餐预算估算 · 门店未提供人均消费",
            rating=_positive_number(business.get("rating"), 5),
            opening_hours=hours,
            source="高德餐饮 POI",
            source_url="https://www.amap.com/place/" + quote(identifier, safe=""),
        )

    async def _live_candidates(self, preferences, before, after, radius):
        cuisines = self._cuisines(preferences)
        diets = _canonical(preferences.dietary_preferences, DIET_ALIASES)
        if "清真" in diets:
            keywords = ["清真"]
        elif set(diets) & {"素食", "不吃海鲜", "不吃牛肉", "不吃猪肉"}:
            keywords = ["素食"]
        else:
            keywords = cuisines[:2] or [""]
        anchors = [before]
        if after and distance_km(before, after) > 1.5:
            anchors.append(
                SimpleNamespace(
                    lat=(before.lat + after.lat) / 2, lon=(before.lon + after.lon) / 2
                )
            )

        async def fetch(anchor, keyword):
            lon, lat = wgs_to_gcj(anchor.lon, anchor.lat)
            params = {
                "location": f"{lon:.6f},{lat:.6f}",
                "radius": radius,
                "types": "050000",
                "show_fields": "business",
                "page_size": 25,
                "page_num": 1,
                "sortrule": "distance",
            }
            if keyword:
                params["keywords"] = keyword
            data = await self._amap("/v5/place/around", params)
            return data.get("pois", [])

        results = await asyncio.gather(
            *(fetch(anchor, keyword) for anchor in anchors for keyword in keywords)
        )
        restaurants = {}
        for rows in results:
            for poi in rows if isinstance(rows, list) else []:
                restaurant = self._parse_poi(poi, preferences.meal_budget_per_person)
                if restaurant:
                    restaurants[restaurant.id] = restaurant
        return list(restaurants.values())

    def _rank(
        self, candidates, preferences, before, after, excluded_ids, start_time, date
    ):
        cuisines = self._cuisines(preferences)
        diets = _canonical(preferences.dietary_preferences, DIET_ALIASES)
        hard_diets = set(diets) - SOFT_DIETS
        limit = preferences.meal_budget_per_person
        speed = {"walking": 4.5, "transit": 18, "driving": 24}[preferences.transport]
        minute = _minute(start_time) + 60
        end_time = f"{minute // 60:02}:{minute % 60:02}"
        ranked = []
        for original in candidates:
            if original.id in excluded_ids or original.cost_per_person > limit:
                continue
            if hard_diets - set(original.dietary_tags):
                continue
            matched_cuisines = set(cuisines) & set(original.cuisines)
            if cuisines and not matched_cuisines:
                continue
            known_open = self.is_open(original, start_time, end_time, date)
            if known_open is False:
                continue
            first_leg = distance_km(before, original)
            if after:
                second_leg = distance_km(original, after)
                detour = max(0, first_leg + second_leg - distance_km(before, after))
            else:
                detour = first_leg
            # Straight-line distances become explicit road/detour estimates.
            detour_minutes = math.ceil(detour * 1.25 / speed * 60)
            if first_leg > (4 if preferences.transport == "walking" else 12):
                continue
            soft_missing = set(diets) & SOFT_DIETS - set(original.dietary_tags)
            reason = [
                f"距前一站约 {first_leg:.1f} 公里",
                f"预计{'绕行' if after else '前往'} {detour_minutes} 分钟",
            ]
            if matched_cuisines:
                reason.append("菜系匹配：" + "、".join(sorted(matched_cuisines)))
            if hard_diets:
                reason.append("饮食标签匹配：" + "、".join(sorted(hard_diets)))
            matched_soft = set(diets) & SOFT_DIETS & set(original.dietary_tags)
            if matched_soft:
                reason.append("口味标签：" + "、".join(sorted(matched_soft)))
            if soft_missing:
                reason.append(
                    "点餐备注：" + "、".join(sorted(soft_missing)) + "，门店尚未确认"
                )
            if "估算" in original.price_source:
                reason.append(f"暂按每人 ¥{limit:g} 预留餐费")
            else:
                reason.append(
                    f"人均 ¥{original.cost_per_person:g}，在 ¥{limit:g} 预算内"
                )
            if known_open is None:
                reason.append("用餐时段营业状态待确认")
            restaurant = original.model_copy(
                update={
                    "detour_minutes": detour_minutes,
                    "recommendation_reason": "；".join(reason),
                }
            )
            price_score = original.cost_per_person / max(limit, 1)
            score = (
                detour_minutes
                + price_score * 8
                + len(soft_missing) * 10
                + (2 if known_open is None else 0)
            )
            if original.rating is not None:
                score -= original.rating * 0.4
            ranked.append((score, first_leg, restaurant.id, restaurant))
        ranked.sort(key=lambda row: row[:3])
        return [row[3] for row in ranked[:3]]

    async def recommend(
        self,
        preferences,
        before,
        after=None,
        slot="lunch",
        excluded_ids=(),
        start_time="12:00",
        date=None,
    ) -> list[Restaurant]:
        """Return up to three restaurants satisfying all known hard constraints."""
        if slot not in {"lunch", "dinner"}:
            raise ValueError("餐次应为午餐或晚餐。")
        if self.settings.app_mode == "demo":
            candidates = demo_restaurants(preferences.destination)
            ranked = self._rank(
                candidates,
                preferences,
                before,
                after,
                set(excluded_ids),
                start_time,
                date,
            )
        else:
            candidates = await self._live_candidates(preferences, before, after, 3000)
            ranked = self._rank(
                candidates,
                preferences,
                before,
                after,
                set(excluded_ids),
                start_time,
                date,
            )
            if len(ranked) < 3:
                wider = await self._live_candidates(preferences, before, after, 10000)
                merged = {
                    restaurant.id: restaurant for restaurant in [*candidates, *wider]
                }
                ranked = self._rank(
                    list(merged.values()),
                    preferences,
                    before,
                    after,
                    set(excluded_ids),
                    start_time,
                    date,
                )
        if not ranked:
            meal = "午餐" if slot == "lunch" else "晚餐"
            raise ValueError(
                f"未找到适合这段路线的{meal}餐厅：人均不超过 ¥{preferences.meal_budget_per_person:g}"
                "，且满足菜系、饮食偏好及可用时段。请调整餐费、菜系或用餐位置。"
            )
        return ranked
