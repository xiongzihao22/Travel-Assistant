import asyncio
import json
import sys
from urllib.parse import urlencode, urlsplit, urlunsplit

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph

from travel_assistant.config import ROOT, Settings
from travel_assistant.demo import DemoModel

# Exclude remote tools that create maps/orders or launch other external actions.
AMAP_READ_TOOLS = {
    "maps_geo",
    "maps_regeocode",
    "maps_text_search",
    "maps_around_search",
    "maps_search_detail",
    "maps_weather",
    "maps_bicycling",
    "maps_direction_walking",
    "maps_direction_driving",
    "maps_direction_transit_integrated",
    "maps_distance",
}


def server_connections(settings: Settings) -> dict:
    specifications = json.loads((ROOT / "servers_config.json").read_text(encoding="utf-8"))
    connections = {}
    for name, spec in specifications.items():
        if spec.get("mode", settings.app_mode) != settings.app_mode:
            continue
        if spec.get("remote"):
            key = settings.amap_api_key.get_secret_value()
            if not key:
                continue
            url = urlsplit(settings.amap_mcp_url)
            if url.scheme != "https" or url.hostname != "mcp.amap.com" or url.query:
                raise ValueError("AMAP_MCP_URL 必须是无查询参数的高德 HTTPS 地址。")
            connections[name] = {
                "transport": settings.amap_transport,
                "url": urlunsplit(url._replace(query=urlencode({"key": key}))),
            }
        else:
            connections[name] = {
                "transport": "stdio",
                "command": sys.executable,
                "args": [str(ROOT / spec["script"])],
                "cwd": str(ROOT),
                "env": {
                    "APP_MODE": settings.app_mode,
                    "OPENWEATHER_API_KEY": settings.openweather_api_key.get_secret_value(),
                    "OUTPUT_DIR": str(settings.output_path),
                    "PYTHONUTF8": "1",
                },
            }
    return connections


def build_graph(model, tools, checkpointer):
    by_name = {tool.name: tool for tool in tools}
    prompt = (ROOT / "agent_prompts.txt").read_text(encoding="utf-8")

    async def reason(state: MessagesState):
        result = await model.ainvoke([SystemMessage(content=prompt), *state["messages"]])
        return {"messages": [result]}

    async def act(state: MessagesState, config: RunnableConfig):
        messages = []
        for call in state["messages"][-1].tool_calls:
            name = call["name"]
            status = "success"
            if name == "write_file" and not config.get("configurable", {}).get("allow_save"):
                value = "保存未执行：请勾选‘允许本次保存文件’后重试。"
                status = "error"
            elif name not in by_name:
                value, status = "当前未启用该工具。", "error"
            else:
                try:
                    result = await asyncio.wait_for(by_name[name].ainvoke(call), timeout=25)
                    if isinstance(result, ToolMessage):
                        messages.append(result)
                        continue
                    value = (
                        result
                        if isinstance(result, str)
                        else json.dumps(result, ensure_ascii=False)
                    )
                except Exception:
                    value, status = "工具调用失败，请检查服务配置或稍后重试。", "error"
            messages.append(
                ToolMessage(content=value, tool_call_id=call["id"], name=name, status=status)
            )
        return {"messages": messages}

    graph = StateGraph(MessagesState)
    graph.add_node("reason", reason)
    graph.add_node("tools", act)
    graph.add_edge(START, "reason")
    graph.add_conditional_edges(
        "reason", lambda state: "tools" if state["messages"][-1].tool_calls else END
    )
    graph.add_edge("tools", "reason")
    return graph.compile(checkpointer=checkpointer)


class AgentService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.memory = InMemorySaver()
        self.graph = None
        self.tools = []
        self.warnings = []
        self.client = None

    async def start(self):
        if (
            self.settings.app_mode == "live"
            and not self.settings.dashscope_api_key.get_secret_value()
        ):
            raise ValueError("live 模式必须设置 DASHSCOPE_API_KEY。")
        self.client = MultiServerMCPClient(server_connections(self.settings))
        for name in self.client.connections:
            try:
                discovered = await asyncio.wait_for(self.client.get_tools(server_name=name), 25)
                self.tools.extend(
                    tool for tool in discovered if name != "amap" or tool.name in AMAP_READ_TOOLS
                )
            except Exception:
                self.warnings.append(f"{name} 服务不可用，请检查配置并重启。")
        if self.settings.app_mode == "demo":
            model = DemoModel()
        else:
            if not self.settings.amap_api_key.get_secret_value():
                self.warnings.append("未配置高德密钥，地图工具未启用。")
            if not self.settings.openweather_api_key.get_secret_value():
                self.warnings.append("未配置天气密钥，实时天气不可用。")
            model = ChatOpenAI(
                model=self.settings.model,
                api_key=self.settings.dashscope_api_key,
                base_url=self.settings.model_base_url,
                temperature=0.2,
                timeout=40,
                max_retries=1,
                use_responses_api=False,
            ).bind_tools(self.tools)
        self.graph = build_graph(model, self.tools, self.memory)

    async def chat(self, message: str, thread_id: str, allow_save: bool = False):
        result = await self.graph.ainvoke(
            {"messages": [HumanMessage(content=message)]},
            {
                "configurable": {"thread_id": thread_id, "allow_save": allow_save},
                "recursion_limit": 16,
            },
        )
        messages = result["messages"]
        current = []
        for item in reversed(messages):
            if isinstance(item, HumanMessage):
                break
            current.append(item)
        trace = [
            {"name": item.name, "status": item.status}
            for item in reversed(current)
            if isinstance(item, ToolMessage)
        ]
        answer = messages[-1]
        if not isinstance(answer, AIMessage):
            raise RuntimeError("Agent did not produce a final answer")
        return {"content": answer.text, "tools": trace}

    async def forget(self, thread_id: str):
        await self.memory.adelete_thread(thread_id)

    async def close(self):
        # MultiServerMCPClient.get_tools uses short-lived sessions. No cleanup() API.
        self.graph = None
        self.tools.clear()
        self.client = None
        self.memory = InMemorySaver()
