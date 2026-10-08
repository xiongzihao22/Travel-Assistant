import os

import httpx


async def query_weather(city: str) -> dict:
    """查询城市当前天气（非预报）；建议城市名加国家代码，例如 Beijing,CN。"""
    city = city.strip()
    if not city or len(city) > 120:
        return {"error": "城市名称不能为空且不能超过 120 字符。"}
    if os.getenv("APP_MODE", "demo") == "demo":
        return {
            "demo": True,
            "city": city,
            "description": "多云（固定演示数据）",
            "temperature_c": 23,
            "humidity_percent": 60,
            "source": "本地固定演示数据",
        }
    key = os.getenv("OPENWEATHER_API_KEY", "")
    if not key:
        return {"error": "未配置 OPENWEATHER_API_KEY，无法查询实时天气。"}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                "https://api.openweathermap.org/data/2.5/weather",
                params={"q": city, "appid": key, "units": "metric", "lang": "zh_cn"},
            )
        if response.status_code == 404:
            return {"error": "未找到城市，请尝试英文城市名和国家代码，例如 Beijing,CN。"}
        if response.status_code in (401, 403):
            return {"error": "天气服务密钥无效或尚未激活。"}
        if response.status_code == 429:
            return {"error": "天气服务请求额度已用尽，请稍后重试。"}
        response.raise_for_status()
        data = response.json()
        return {
            "city": data["name"],
            "description": data["weather"][0]["description"],
            "temperature_c": data["main"]["temp"],
            "humidity_percent": data["main"]["humidity"],
            "wind_m_s": data.get("wind", {}).get("speed"),
            "observed_at_unix": data["dt"],
            "source": "OpenWeather current weather",
        }
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
        # Do not expose exception strings: request URLs contain an API key.
        return {"error": "天气服务暂时不可用或响应格式异常，请稍后重试。"}
