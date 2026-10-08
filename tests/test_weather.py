import httpx

from travel_assistant.weather import query_weather


async def test_demo_is_labelled_and_offline(monkeypatch):
    monkeypatch.setenv("APP_MODE", "demo")
    result = await query_weather("Beijing,CN")
    assert result["demo"] is True
    assert "非实时" in result["source"]


async def test_missing_key(monkeypatch):
    monkeypatch.setenv("APP_MODE", "live")
    monkeypatch.delenv("OPENWEATHER_API_KEY", raising=False)
    assert "OPENWEATHER_API_KEY" in (await query_weather("Beijing"))["error"]


async def test_weather_api_and_redaction(monkeypatch):
    monkeypatch.setenv("APP_MODE", "live")
    monkeypatch.setenv("OPENWEATHER_API_KEY", "secret-test-only")
    original = httpx.AsyncClient

    def handler(request):
        assert request.url.params["units"] == "metric"
        assert request.url.params["q"] == "Beijing,CN"
        return httpx.Response(
            200,
            json={
                "name": "Beijing",
                "weather": [{"description": "晴"}],
                "main": {"temp": 22, "humidity": 40},
                "dt": 123,
            },
        )

    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: original(**kw, transport=httpx.MockTransport(handler))
    )
    assert (await query_weather("Beijing,CN"))["temperature_c"] == 22

    def broken(request):
        raise httpx.ConnectError("URL contains secret-test-only", request=request)

    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: original(**kw, transport=httpx.MockTransport(broken))
    )
    result = await query_weather("Beijing,CN")
    assert "error" in result
    assert "secret-test-only" not in str(result)
