"""CLI client for the running FastAPI server. /save authorizes one file-writing turn."""

import asyncio

import httpx

from travel_assistant.config import Settings


async def main():
    settings = Settings()
    token = settings.app_api_token.get_secret_value()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:8000", headers=headers, timeout=settings.request_timeout + 10
    ) as client:
        response = await client.post("/sessions")
        response.raise_for_status()
        thread_id = response.json()["thread_id"]
        print("出行助手：/new 新会话，/save 保存上一条结果，/quit 退出。")
        try:
            while True:
                message = await asyncio.to_thread(input, "你 > ")
                if message == "/quit":
                    break
                if message == "/new":
                    await client.delete(f"/sessions/{thread_id}")
                    response = await client.post("/sessions")
                    response.raise_for_status()
                    thread_id = response.json()["thread_id"]
                    continue
                if not message.strip():
                    continue
                response = await client.post(
                    "/chat",
                    json={
                        "thread_id": thread_id,
                        "message": "保存上一条结果" if message == "/save" else message,
                        "allow_save": message == "/save",
                    },
                )
                data = response.json()
                print("助手 >", data.get("content", data.get("detail", "请求失败")))
                if response.status_code in (404, 502, 504):
                    response = await client.post("/sessions")
                    response.raise_for_status()
                    thread_id = response.json()["thread_id"]
        finally:
            await client.delete(f"/sessions/{thread_id}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, EOFError):
        pass
    except httpx.HTTPError:
        print("连接失败，请确认服务已启动且 APP_API_TOKEN 配置一致。")
