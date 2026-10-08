"""Destination catalogs, coordinate transforms and geographic helpers."""

from dataclasses import dataclass
from math import asin, cos, pi, radians, sin, sqrt


@dataclass(frozen=True)
class Place:
    id: str
    name: str
    lat: float
    lon: float
    category: str
    indoor: bool
    minutes: int
    cost: float
    description: str
    source: str = "演示地点资料 · 门票为预算样例"
    url: str = ""


# WGS84 coordinates. Cost and duration fields are planning inputs for demo mode.
CATALOG = {
    "杭州": [
        ("西湖湖滨", 30.258911, 120.154122, "自然", False, 120, 0),
        ("浙江省博物馆孤山馆区", 30.253547, 120.139041, "人文", True, 100, 0),
        ("中国丝绸博物馆", 30.225188, 120.146578, "人文", True, 100, 0),
        ("雷峰塔", 30.233248, 120.144127, "人文", False, 80, 40),
        ("太子湾公园", 30.227774, 120.137439, "自然", False, 90, 0),
        ("花港观鱼", 30.232458, 120.132865, "自然", False, 80, 0),
        ("苏堤", 30.242637, 120.134544, "自然", False, 100, 0),
        ("曲院风荷", 30.251578, 120.128572, "自然", False, 80, 0),
        ("岳王庙", 30.254735, 120.129831, "人文", False, 80, 25),
        ("浙江美术馆", 30.233376, 120.152195, "艺术", True, 100, 0),
        ("中国茶叶博物馆双峰馆区", 30.234661, 120.115747, "人文", True, 100, 0),
        ("龙井村", 30.220755, 120.10188, "自然", False, 120, 0),
        ("九溪烟树", 30.204672, 120.108557, "自然", False, 110, 0),
        ("灵隐寺", 30.243099, 120.096596, "人文", False, 150, 75),
        ("北高峰", 30.247766, 120.093101, "自然", False, 120, 0),
        ("河坊街", 30.242421, 120.164258, "美食", False, 100, 0),
        ("南宋御街", 30.242598, 120.164863, "人文", False, 80, 0),
        ("胡庆余堂中药博物馆", 30.242065, 120.16432, "人文", True, 80, 10),
        ("杭州博物馆", 30.241435, 120.161853, "人文", True, 100, 0),
        ("吴山广场", 30.241522, 120.159006, "休闲", False, 70, 0),
        ("杭州工艺美术博物馆", 30.317933, 120.132171, "艺术", True, 90, 0),
        ("中国京杭大运河博物馆", 30.319698, 120.136582, "人文", True, 100, 0),
        ("小河直街", 30.309664, 120.132267, "美食", False, 90, 0),
        ("拱宸桥", 30.320393, 120.135092, "人文", False, 60, 0),
        ("杭州低碳科技馆", 30.211769, 120.197401, "亲子", True, 100, 0),
        ("钱江新城市民中心", 30.248972, 120.205334, "城市", False, 80, 0),
        ("杭州图书馆", 30.248782, 120.203649, "人文", True, 80, 0),
        ("城市阳台", 30.244257, 120.212272, "自然", False, 70, 0),
    ],
    "北京": [
        ("故宫博物院", 39.916438, 116.390787, "人文", False, 180, 60),
        ("景山公园", 39.924, 116.391, "自然", False, 80, 10),
        ("北海公园", 39.924, 116.383, "自然", False, 110, 10),
        ("中国美术馆", 39.926, 116.402, "艺术", True, 100, 0),
        ("中国国家博物馆", 39.903, 116.401, "人文", True, 150, 0),
        ("前门大街", 39.894, 116.391, "美食", False, 90, 0),
        ("北京坊", 39.896, 116.387, "休闲", False, 70, 0),
        ("首都博物馆", 39.906, 116.335, "人文", True, 120, 0),
        ("天坛公园", 39.883, 116.406, "人文", False, 140, 34),
        ("自然博物馆", 39.883, 116.393, "亲子", True, 100, 0),
        ("陶然亭公园", 39.872, 116.373, "自然", False, 90, 2),
        ("琉璃厂文化街", 39.893, 116.378, "艺术", False, 90, 0),
        ("什刹海", 39.938, 116.377, "自然", False, 100, 0),
        ("恭王府", 39.938, 116.380, "人文", False, 120, 40),
        ("南锣鼓巷", 39.934, 116.397, "美食", False, 90, 0),
        ("钟鼓楼", 39.940, 116.390, "人文", False, 80, 30),
        ("颐和园", 39.993, 116.268, "自然", False, 180, 30),
        ("圆明园", 40.006, 116.292, "人文", False, 140, 25),
        ("清华大学艺术博物馆", 40.001, 116.330, "艺术", True, 100, 20),
        ("中国地质博物馆", 39.923, 116.366, "亲子", True, 90, 15),
        ("国家动物博物馆", 40.000, 116.371, "亲子", True, 100, 40),
        ("中国科学技术馆", 40.000, 116.392, "亲子", True, 150, 30),
        ("奥林匹克森林公园", 40.014, 116.385, "自然", False, 120, 0),
        ("国家体育场外观", 39.991, 116.390, "城市", False, 70, 0),
        ("中国铁道博物馆正阳门馆", 39.897, 116.397, "人文", True, 100, 20),
        ("中国工艺美术馆", 40.002, 116.389, "艺术", True, 110, 0),
        ("朝阳公园", 39.944, 116.475, "自然", False, 110, 0),
        ("三里屯", 39.936, 116.450, "美食", False, 90, 0),
    ],
    "上海": [
        ("外滩", 31.235496, 121.487651, "城市", False, 100, 0),
        ("上海博物馆人民广场馆", 31.228, 121.470, "人文", True, 120, 0),
        ("上海城市规划展示馆", 31.236, 121.470, "人文", True, 100, 0),
        ("南京东路", 31.236, 121.479, "美食", False, 90, 0),
        ("豫园", 31.226, 121.487, "人文", False, 110, 40),
        ("上海城隍庙商圈", 31.224, 121.487, "美食", False, 90, 0),
        ("复星艺术中心", 31.223, 121.493, "艺术", True, 100, 100),
        ("外滩源", 31.245, 121.483, "人文", False, 90, 0),
        ("上海自然博物馆", 31.236, 121.456, "亲子", True, 140, 30),
        ("静安雕塑公园", 31.237, 121.456, "艺术", False, 80, 0),
        ("静安寺", 31.223, 121.440, "人文", False, 90, 50),
        ("上海邮政博物馆", 31.246, 121.479, "人文", True, 90, 0),
        ("武康路", 31.207, 121.437, "人文", False, 100, 0),
        ("宋庆龄故居纪念馆", 31.207, 121.429, "人文", True, 90, 20),
        ("徐家汇书院", 31.192, 121.433, "人文", True, 80, 0),
        ("衡山路", 31.204, 121.445, "休闲", False, 80, 0),
        ("中华艺术宫", 31.184, 121.484, "艺术", True, 120, 0),
        ("上海当代艺术博物馆", 31.203, 121.490, "艺术", True, 110, 0),
        ("世博公园", 31.188, 121.485, "自然", False, 90, 0),
        ("田子坊", 31.210, 121.461, "艺术", False, 90, 0),
        ("浦东滨江大道", 31.239, 121.496, "自然", False, 100, 0),
        ("上海海洋水族馆", 31.239, 121.501, "亲子", True, 120, 160),
        ("上海中心观光厅", 31.234, 121.499, "城市", True, 100, 180),
        ("陆家嘴中心绿地", 31.240, 121.506, "自然", False, 80, 0),
        ("上海图书馆东馆", 31.219, 121.539, "人文", True, 100, 0),
        ("浦东美术馆", 31.236, 121.492, "艺术", True, 110, 100),
        ("世纪公园", 31.213, 121.548, "自然", False, 120, 0),
        ("北外滩滨江绿地", 31.250, 121.493, "自然", False, 90, 0),
    ],
    "成都": [
        ("人民公园", 30.659428, 104.055156, "休闲", False, 100, 0),
        ("成都博物馆", 30.659447, 104.061422, "人文", True, 120, 0),
        ("四川美术馆", 30.660, 104.060, "艺术", True, 100, 0),
        ("宽窄巷子", 30.664, 104.049, "美食", False, 100, 0),
        ("武侯祠", 30.646, 104.042, "人文", False, 120, 50),
        ("锦里", 30.646, 104.044, "美食", False, 90, 0),
        ("四川博物院", 30.661, 104.025, "人文", True, 120, 0),
        ("杜甫草堂", 30.660, 104.021, "人文", False, 120, 50),
        ("浣花溪公园", 30.656, 104.025, "自然", False, 100, 0),
        ("青羊宫", 30.660, 104.030, "人文", False, 90, 10),
        ("文殊院", 30.692, 104.067, "人文", False, 100, 0),
        ("文殊坊", 30.690, 104.067, "美食", False, 90, 0),
        ("成都画院", 30.665, 104.058, "艺术", True, 90, 0),
        ("金沙遗址博物馆", 30.680, 104.006, "人文", True, 150, 70),
        ("永陵博物馆", 30.676, 104.037, "人文", True, 90, 20),
        ("四川科技馆", 30.660, 104.065, "亲子", True, 120, 0),
        ("大慈寺", 30.649, 104.080, "人文", False, 90, 0),
        ("太古里", 30.649, 104.079, "美食", False, 100, 0),
        ("春熙路", 30.653, 104.078, "城市", False, 90, 0),
        ("望平街", 30.655, 104.088, "休闲", False, 90, 0),
        ("望江楼公园", 30.627, 104.087, "自然", False, 110, 20),
        ("四川大学博物馆", 30.631, 104.079, "人文", True, 110, 0),
        ("东郊记忆", 30.667, 104.121, "艺术", False, 110, 0),
        ("成都自然博物馆", 30.670, 104.138, "亲子", True, 120, 0),
        ("成都大熊猫繁育研究基地", 30.740, 104.138, "亲子", False, 180, 55),
        ("成都图书馆", 30.658, 104.056, "人文", True, 90, 0),
        ("天府艺术公园", 30.728, 104.005, "自然", False, 100, 0),
        ("成都市美术馆", 30.729, 104.006, "艺术", True, 110, 0),
    ],
}


# Official Amap POI anchors individually checked; GCJ-02 positions converted to WGS84.
# Gates are used for Flower Harbor (west) and Xiaohe Street (east) access points.
PLACE_SOURCES = {
    "西湖湖滨": "https://www.amap.com/place/B023B05MLT",
    "浙江省博物馆孤山馆区": "https://www.amap.com/place/B023B06XVX",
    "中国丝绸博物馆": "https://www.amap.com/place/B023B09JLL",
    "雷峰塔": "https://www.amap.com/place/B023B09LKR",
    "太子湾公园": "https://www.amap.com/place/B023B02074",
    "花港观鱼": "https://www.amap.com/place/B0FFF3VIB2",
    "苏堤": "https://www.amap.com/place/B023B0AC72",
    "曲院风荷": "https://www.amap.com/place/B023B0253E",
    "岳王庙": "https://www.amap.com/place/B0FFFDIGWR",
    "浙江美术馆": "https://www.amap.com/place/B023B0BMJ6",
    "中国茶叶博物馆双峰馆区": "https://www.amap.com/place/B023B13PFT",
    "龙井村": "https://www.amap.com/place/B023B17X30",
    "九溪烟树": "https://www.amap.com/place/B0FFHMH4J8",
    "灵隐寺": "https://www.amap.com/place/B023B02842",
    "北高峰": "https://www.amap.com/place/B023B01E9A",
    "河坊街": "https://www.amap.com/place/B023B1E89A",
    "南宋御街": "https://www.amap.com/place/B023B14PP8",
    "胡庆余堂中药博物馆": "https://www.amap.com/place/B0L3JCDNWV",
    "杭州博物馆": "https://www.amap.com/place/B0FFFWQGI8",
    "吴山广场": "https://www.amap.com/place/B023B0A5KT",
    "杭州工艺美术博物馆": "https://www.amap.com/place/B023B0I02U",
    "中国京杭大运河博物馆": "https://www.amap.com/place/B023B07XI3",
    "小河直街": "https://www.amap.com/place/B0L0C1ZHSZ",
    "拱宸桥": "https://www.amap.com/place/B023B1BGM6",
    "杭州低碳科技馆": "https://www.amap.com/place/B023B1944R",
    "钱江新城市民中心": "https://www.amap.com/place/B0FFG08H83",
    "杭州图书馆": "https://www.amap.com/place/B023B0BN0M",
    "城市阳台": "https://www.amap.com/place/B023B1FB36",
    "故宫博物院": "https://www.amap.com/place/B000A8UIN8",
    "外滩": "https://www.amap.com/place/B00155FXB3",
    "人民公园": "https://www.amap.com/place/B001C7X8QA",
    "成都博物馆": "https://www.amap.com/place/B0FFH6WLE4",
}


def normalize_city(value: str) -> str:
    return value.strip().removesuffix("市")


def demo_places(city: str) -> list[Place]:
    city = normalize_city(city)
    if city not in CATALOG:
        raise ValueError(
            "演示模式支持杭州、北京、上海、成都；其他目的地请切换真实模式。"
        )
    return [
        Place(
            f"{city}-{i}",
            name,
            lat,
            lon,
            category,
            indoor,
            minutes,
            cost,
            f"{category}主题体验，建议安排 {minutes} 分钟。",
            source="高德地点资料 · 演示费用"
            if name in PLACE_SOURCES
            else "演示地点资料 · 门票为预算样例",
            url=PLACE_SOURCES.get(name, ""),
        )
        for i, (name, lat, lon, category, indoor, minutes, cost) in enumerate(
            CATALOG[city]
        )
    ]


def distance_km(a, b) -> float:
    lat1, lat2 = radians(a.lat), radians(b.lat)
    dlat, dlon = lat2 - lat1, radians(b.lon - a.lon)
    return (
        6371
        * 2
        * asin(
            min(
                1, sqrt(sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2)
            )
        )
    )


def _offset(lon: float, lat: float) -> tuple[float, float]:
    x, y = lon - 105, lat - 35
    dlat = -100 + 2 * x + 3 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * sqrt(abs(x))
    dlat += (20 * sin(6 * x * pi) + 20 * sin(2 * x * pi)) * 2 / 3
    dlat += (20 * sin(y * pi) + 40 * sin(y / 3 * pi)) * 2 / 3
    dlat += (160 * sin(y / 12 * pi) + 320 * sin(y * pi / 30)) * 2 / 3
    dlon = 300 + x + 2 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * sqrt(abs(x))
    dlon += (20 * sin(6 * x * pi) + 20 * sin(2 * x * pi)) * 2 / 3
    dlon += (20 * sin(x * pi) + 40 * sin(x / 3 * pi)) * 2 / 3
    dlon += (150 * sin(x / 12 * pi) + 300 * sin(x / 30 * pi)) * 2 / 3
    radlat = radians(lat)
    magic = 1 - 0.00669342162296594323 * sin(radlat) ** 2
    dlat = (
        dlat
        * 180
        / ((6378245 * (1 - 0.00669342162296594323)) / (magic * sqrt(magic)) * pi)
    )
    dlon = dlon * 180 / (6378245 / sqrt(magic) * cos(radlat) * pi)
    return dlon, dlat


def wgs_to_gcj(lon: float, lat: float) -> tuple[float, float]:
    if not (72.004 <= lon <= 137.8347 and 0.8293 <= lat <= 55.8271):
        return lon, lat
    dx, dy = _offset(lon, lat)
    return lon + dx, lat + dy


def gcj_to_wgs(lon: float, lat: float) -> tuple[float, float]:
    guess_lon, guess_lat = lon, lat
    for _ in range(4):
        actual_lon, actual_lat = wgs_to_gcj(guess_lon, guess_lat)
        guess_lon -= actual_lon - lon
        guess_lat -= actual_lat - lat
    return round(guess_lon, 6), round(guess_lat, 6)
