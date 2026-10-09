"""Named demonstration dining points on a fixed WGS84 neighborhood grid."""

from .destinations import normalize_city
from .models import Restaurant

# These are neighborhood anchors for fictional demo restaurants, not merchant POIs.
# Restaurant names and source labels keep that distinction visible in saved plans.
DINING_AREAS = {
    "杭州": [
        ("湖滨", 30.2602, 120.1567),
        ("北山街", 30.2561, 120.1335),
        ("南山路", 30.2328, 120.1546),
        ("龙井路", 30.2322, 120.1157),
        ("灵隐路", 30.2427, 120.1013),
        ("九溪", 30.1967, 120.1166),
        ("清河坊", 30.2405, 120.1649),
        ("拱宸桥", 30.3186, 120.1369),
        ("滨江", 30.2128, 120.1975),
        ("钱江新城", 30.2487, 120.2076),
    ],
    "北京": [
        ("东华门", 39.9180, 116.3970),
        ("景山", 39.9261, 116.3931),
        ("前门", 39.8935, 116.3940),
        ("白云路", 39.9073, 116.3378),
        ("天坛", 39.8825, 116.4090),
        ("陶然亭", 39.8750, 116.3749),
        ("鼓楼", 39.9390, 116.3919),
        ("颐和园路", 39.9890, 116.2810),
        ("清华东路", 40.0002, 116.3335),
        ("奥体", 39.9977, 116.3910),
        ("三里屯", 39.9367, 116.4522),
        ("朝阳公园", 39.9420, 116.4700),
    ],
    "上海": [
        ("南京东路", 31.2353, 121.4808),
        ("人民广场", 31.2320, 121.4707),
        ("豫园", 31.2235, 121.4872),
        ("苏州河", 31.2455, 121.4810),
        ("静安", 31.2275, 121.4430),
        ("武康路", 31.2082, 121.4385),
        ("徐家汇", 31.1930, 121.4356),
        ("陆家嘴", 31.2380, 121.4970),
        ("世纪公园", 31.2190, 121.5390),
        ("龙美术馆周边", 31.1904, 121.4580),
        ("虹口", 31.2730, 121.4740),
        ("田子坊", 31.2080, 121.4630),
    ],
    "成都": [
        ("天府广场", 30.6575, 104.0612),
        ("宽窄巷子", 30.6651, 104.0487),
        ("武侯祠", 30.6448, 104.0467),
        ("杜甫草堂", 30.6604, 104.0267),
        ("文殊院", 30.6823, 104.0690),
        ("太古里", 30.6519, 104.0798),
        ("望江楼", 30.6267, 104.0862),
        ("金沙", 30.6800, 104.0090),
        ("熊猫大道", 30.7351, 104.1384),
        ("东郊记忆", 30.6690, 104.1190),
        ("锦城湖", 30.5762, 104.0559),
        ("成都自然博物馆周边", 30.6810, 104.1390),
    ],
}

LOCAL_CUISINE = {"杭州": "杭帮菜", "北京": "北京菜", "上海": "上海菜", "成都": "川菜"}

CUISINES = [
    "杭帮菜",
    "川菜",
    "粤菜",
    "江浙菜",
    "北京菜",
    "上海菜",
    "东北菜",
    "日料",
    "西餐",
    "面食",
    "火锅",
    "小吃",
]


def demo_restaurants(city: str) -> list[Restaurant]:
    """Build clearly labeled fixtures with independent, deterministic positions."""
    city = normalize_city(city)
    if city not in DINING_AREAS:
        raise ValueError("演示餐饮支持杭州、北京、上海、成都。")
    restaurants = []
    for area_index, (area, lat, lon) in enumerate(DINING_AREAS[city]):
        for cuisine_index, cuisine in enumerate(CUISINES):
            # Each cuisine has multiple price/food profiles for preference filtering.
            for kind, price, label, tags in (
                (0, 28, "家常食堂", ["清淡", "不辣"]),
                (
                    1,
                    38,
                    "蔬食小馆",
                    ["素食", "清淡", "不辣", "不吃海鲜", "不吃牛肉", "不吃猪肉"],
                ),
                (2, 48, "清真小馆", ["清真", "清淡", "不辣", "不吃猪肉", "不吃海鲜"]),
                (
                    3,
                    20,
                    "蔬食便餐",
                    ["素食", "清淡", "不辣", "不吃海鲜", "不吃牛肉", "不吃猪肉"],
                ),
                (
                    4,
                    58,
                    "清真蔬食",
                    [
                        "清真",
                        "素食",
                        "清淡",
                        "不辣",
                        "不吃海鲜",
                        "不吃牛肉",
                        "不吃猪肉",
                    ],
                ),
            ):
                point = cuisine_index * 5 + kind
                restaurants.append(
                    Restaurant(
                        id=f"demo-dining-{city}-{area_index}-{cuisine_index}-{kind}",
                        name=f"{area}·{cuisine}{label}（样例）",
                        lat=round(lat + ((point % 8) - 3.5) * 0.00022, 6),
                        lon=round(lon + ((point // 8) - 3.5) * 0.00024, 6),
                        address=f"{city}{area}餐饮样例点",
                        cuisines=[cuisine],
                        dietary_tags=tags,
                        cost_per_person=price,
                        price_source="演示餐费",
                        opening_hours="每日 10:30-21:30",
                        source="演示餐饮 · 区域样例点",
                    )
                )
    return restaurants
