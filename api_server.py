import asyncio
import secrets
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from travel_assistant.agent import AgentService
from travel_assistant.config import ROOT, Settings
from travel_assistant.knowledge import KnowledgeBase
from travel_assistant.planner import Planner
from travel_assistant.routes import planning_router
from travel_assistant.storage import Storage


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    thread_id: UUID
    allow_save: bool = False


@dataclass
class Session:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    turns: int = 0


def create_app(settings: Settings | None = None, service=None):
    settings = settings or Settings()
    service = service or AgentService(settings)
    sessions: dict[str, Session] = {}

    @asynccontextmanager
    async def lifespan(app):
        app.state.store = Storage(settings.database_file)
        app.state.knowledge = KnowledgeBase(settings.database_file, settings)
        app.state.planner = Planner(settings, app.state.knowledge)
        await service.start()
        try:
            yield
        finally:
            await service.close()
            sessions.clear()

    app = FastAPI(title="Travel Assistant", version="1.0.0", lifespan=lifespan)

    def authenticate(authorization: str | None = Header(default=None)):
        token = settings.app_api_token.get_secret_value()
        if token and not secrets.compare_digest(authorization or "", f"Bearer {token}"):
            raise HTTPException(401, "访问令牌不正确。")

    dependencies = [Depends(authenticate)]
    app.include_router(planning_router(dependencies, settings))

    @app.get("/health", dependencies=dependencies)
    async def health():
        return {
            "status": "ok",
            "mode": settings.app_mode,
            "tools": [t.name for t in service.tools],
            "warnings": service.warnings,
        }

    @app.post("/sessions", dependencies=dependencies, status_code=201)
    async def new_session():
        if len(sessions) >= settings.max_sessions:
            raise HTTPException(429, "会话数量已达上限，请删除旧会话或重启服务。")
        key = str(uuid4())
        sessions[key] = Session()
        return {"thread_id": key}

    @app.delete("/sessions/{thread_id}", dependencies=dependencies)
    async def delete_session(thread_id: UUID):
        key = str(thread_id)
        session = sessions.get(key)
        if not session:
            raise HTTPException(404, "会话不存在。")
        if session.lock.locked():
            raise HTTPException(409, "当前会话正在处理请求。")
        async with session.lock:
            await service.forget(key)
            sessions.pop(key, None)
        return {"deleted": True}

    @app.post("/chat", dependencies=dependencies)
    async def chat(request: ChatRequest):
        if not request.message.strip():
            raise HTTPException(422, "消息不能为空。")
        key = str(request.thread_id)
        session = sessions.get(key)
        if not session:
            raise HTTPException(404, "会话不存在或服务已重启，请新建会话。")
        if session.lock.locked():
            raise HTTPException(409, "请等待本会话上一条消息处理完成。")
        async with session.lock:
            if session.turns >= settings.max_turns:
                raise HTTPException(429, "当前会话已达轮数上限，请新建会话。")
            session.turns += 1
            try:
                async with asyncio.timeout(settings.request_timeout):
                    result = await service.chat(
                        request.message, key, request.allow_save
                    )
            except Exception as error:
                # Failed/cancelled graphs can contain unfinished tool calls; retire the session.
                await service.forget(key)
                sessions.pop(key, None)
                code = 504 if isinstance(error, TimeoutError) else 502
                raise HTTPException(
                    code, "服务请求失败，会话已重置，请新建会话后重试。"
                ) from None
        return {"thread_id": key, "mode": settings.app_mode, **result}

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(ROOT / "web" / "index.html")

    app.mount("/static", StaticFiles(directory=ROOT / "web"), name="static")
    return app


app = create_app()
