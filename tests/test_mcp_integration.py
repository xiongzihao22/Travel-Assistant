"""Real STDIO subprocesses + LangGraph checkpoints, no network or model credentials."""

import pytest

from travel_assistant.agent import AgentService, server_connections
from travel_assistant.config import Settings


async def test_real_mcp_graph_memory_and_file_gate(tmp_path):
    service = AgentService(Settings(_env_file=None, app_mode="demo", output_dir=tmp_path))
    await service.start()
    try:
        assert not service.warnings
        assert {tool.name for tool in service.tools} == {
            "query_weather",
            "write_file",
            "demo_route",
        }
        result = await service.chat("北京天气和行程", "one")
        assert {tool["name"] for tool in result["tools"]} == {"query_weather", "demo_route"}
        assert "非实时" in result["content"]
        assert "第 2 轮" in (await service.chat("你好", "one"))["content"]
        assert "第 1 轮" in (await service.chat("你好", "two"))["content"]
        blocked = await service.chat("保存", "one", allow_save=False)
        assert blocked["tools"][0]["status"] == "error"
        assert not list(tmp_path.iterdir())
        saved = await service.chat("保存", "two", allow_save=True)
        assert saved["tools"][0]["status"] == "success"
        assert len(list(tmp_path.glob("*.md"))) == 1
        await service.forget("one")
        assert "第 1 轮" in (await service.chat("你好", "one"))["content"]
    finally:
        await service.close()


def test_live_connections_require_keys():
    settings = Settings(_env_file=None, app_mode="live")
    assert set(server_connections(settings)) == {"weather", "notes"}


async def test_live_mode_does_not_silently_fall_back():
    service = AgentService(Settings(_env_file=None, app_mode="live"))
    with pytest.raises(ValueError, match="DASHSCOPE_API_KEY"):
        await service.start()
