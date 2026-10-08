import json
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


class DemoModel:
    """Deterministic tool routing for offline demos, NOT an LLM."""

    async def ainvoke(self, messages):
        if isinstance(messages[-1], ToolMessage):
            observations = []
            for message in reversed(messages):
                if not isinstance(message, ToolMessage):
                    break
                content = message.content
                if isinstance(content, list):
                    content = "\n".join(
                        block.get("text", "") for block in content if isinstance(block, dict)
                    )
                try:
                    data = json.loads(content)
                except (ValueError, TypeError):
                    observations.append(str(content))
                    continue
                if "error" in data:
                    observations.append(data["error"])
                elif "temperature_c" in data:
                    observations.append(
                        f"北京天气样例：{data['description']}，{data['temperature_c']} °C，"
                        f"湿度 {data['humidity_percent']}%。\n来源：{data['source']}"
                    )
                elif "itinerary" in data:
                    observations.append(
                        "北京一日行程样例：\n"
                        + "\n".join(data["itinerary"])
                        + "\n"
                        + data["notice"]
                    )
                elif data.get("saved"):
                    observations.append(f"已保存到输出目录：{data['filename']}")
                else:
                    observations.append(str(content))
            return AIMessage(
                content="【离线演示 · 非实时数据】\n" + "\n\n".join(reversed(observations))
            )
        text = str(messages[-1].content)
        calls = []
        if "保存" in text:
            previous = next(
                (
                    str(m.content)
                    for m in reversed(messages[:-1])
                    if isinstance(m, AIMessage) and m.content and not m.tool_calls
                ),
                "尚无行程；这是用于验证文件工具的演示笔记。",
            )
            calls.append(
                {
                    "name": "write_file",
                    "args": {
                        "filename": f"travel-{uuid4().hex[:8]}.md",
                        "content": previous,
                    },
                    "id": uuid4().hex,
                    "type": "tool_call",
                }
            )
        else:
            if "天气" in text:
                calls.append(
                    {
                        "name": "query_weather",
                        "args": {"city": "Beijing,CN"},
                        "id": uuid4().hex,
                        "type": "tool_call",
                    }
                )
            if any(word in text for word in ("行程", "路线", "规划", "景点")):
                calls.append(
                    {"name": "demo_route", "args": {}, "id": uuid4().hex, "type": "tool_call"}
                )
        if calls:
            return AIMessage(content="", tool_calls=calls)
        turns = sum(isinstance(m, HumanMessage) for m in messages)
        return AIMessage(
            content=(
                f"【离线演示】这是本会话第 {turns} 轮。当前使用固定规则，不是大模型。\n"
                "可体验：北京天气、北京一日行程、保存上一条结果。其他城市与自由问答请切换 live。"
            )
        )
