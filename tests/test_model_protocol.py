"""Check OpenAI-compatible tool serialization without a real account or HTTP call."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver

from travel_assistant.agent import build_graph


async def test_qwen_compatible_tool_round_trip():
    @tool
    async def query_weather(city: str) -> str:
        """Return a weather fixture for a protocol test."""
        assert city == "Beijing,CN"
        return "测试天气：23 度"

    def response(message, reason):
        return SimpleNamespace(
            headers={},
            parse=lambda: {
                "id": "test-completion",
                "object": "chat.completion",
                "created": 0,
                "model": "qwen-plus",
                "choices": [{"index": 0, "message": message, "finish_reason": reason}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )

    create = AsyncMock(
        side_effect=[
            response(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "weather-1",
                            "type": "function",
                            "function": {
                                "name": "query_weather",
                                "arguments": json.dumps({"city": "Beijing,CN"}),
                            },
                        }
                    ],
                },
                "tool_calls",
            ),
            response({"role": "assistant", "content": "测试完成：23 度"}, "stop"),
        ]
    )
    model = ChatOpenAI(
        model="qwen-plus",
        api_key="test-only",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        use_responses_api=False,
        async_client=SimpleNamespace(with_raw_response=SimpleNamespace(create=create)),
    ).bind_tools([query_weather])
    graph = build_graph(model, [query_weather], InMemorySaver())
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="北京天气")]},
        {"configurable": {"thread_id": "protocol"}},
    )
    assert result["messages"][-1].content == "测试完成：23 度"
    assert create.await_count == 2
    sent = create.call_args_list[1].kwargs
    assert sent["model"] == "qwen-plus"
    assert sent["messages"][-1]["role"] == "tool"
    assert sent["messages"][-1]["tool_call_id"] == "weather-1"
