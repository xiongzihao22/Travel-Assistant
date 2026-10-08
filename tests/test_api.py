import asyncio
from uuid import uuid4

from fastapi.testclient import TestClient
from pydantic import SecretStr

from api_server import create_app
from travel_assistant.config import Settings


class StubService:
    tools = []
    warnings = []

    async def start(self):
        pass

    async def close(self):
        pass

    async def forget(self, key):
        pass

    async def chat(self, message, key, allow_save):
        return {"content": message, "tools": []}


def test_auth_sessions_validation_and_limit():
    settings = Settings(_env_file=None, app_api_token=SecretStr("test-token"), max_turns=1)
    with TestClient(create_app(settings, StubService())) as client:
        assert client.get("/health").status_code == 401
        client.headers["Authorization"] = "Bearer test-token"
        key = client.post("/sessions").json()["thread_id"]
        assert client.post("/chat", json={"thread_id": key, "message": " "}).status_code == 422
        assert (
            client.post("/chat", json={"thread_id": str(uuid4()), "message": "hi"}).status_code
            == 404
        )
        assert client.post("/chat", json={"thread_id": key, "message": "hi"}).status_code == 200
        assert client.post("/chat", json={"thread_id": key, "message": "hi"}).status_code == 429
        assert client.delete(f"/sessions/{key}").status_code == 200
        assert client.delete(f"/sessions/{key}").status_code == 404
        assert "智能出行助手" in client.get("/").text


def test_failed_graph_retires_session_without_leaking_error():
    class Broken(StubService):
        async def chat(self, *args):
            raise RuntimeError("secret-key-should-not-leak")

    with TestClient(create_app(Settings(_env_file=None), Broken())) as client:
        key = client.post("/sessions").json()["thread_id"]
        response = client.post("/chat", json={"thread_id": key, "message": "hi"})
        assert response.status_code == 502
        assert "secret-key" not in response.text
        assert client.post("/chat", json={"thread_id": key, "message": "hi"}).status_code == 404


def test_timeout_retires_session():
    class Slow(StubService):
        async def chat(self, *args):
            await asyncio.sleep(2)

    with TestClient(create_app(Settings(_env_file=None, request_timeout=1), Slow())) as client:
        key = client.post("/sessions").json()["thread_id"]
        assert client.post("/chat", json={"thread_id": key, "message": "hi"}).status_code == 504
