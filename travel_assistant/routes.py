"""Persistent trip, revision, export and knowledge API routes."""

import asyncio
import io
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from travel_assistant.exports import export_ics, export_markdown, export_pdf
from travel_assistant.models import (
    DocumentRequest,
    GenerateRequest,
    MealSelectionRequest,
    Plan,
    QuestionRequest,
    RestoreRequest,
    ReviseRequest,
)


def planning_router(dependencies, settings):
    router = APIRouter(dependencies=dependencies)
    capacity = asyncio.Semaphore(4)

    async def work(operation):
        try:
            async with asyncio.timeout(settings.request_timeout):
                async with capacity:
                    return await operation()
        except ValidationError as error:
            raise HTTPException(
                422, "输入信息不完整或格式有误，请检查日期、人数和预算。"
            ) from error
        except KeyError as error:
            raise HTTPException(404, "未找到对应的行程、版本或资料。") from error
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        except TimeoutError as error:
            raise HTTPException(504, "处理超时，请稍后重试。") from error

    async def lookup(request, trip_id):
        try:
            return await run_in_threadpool(request.app.state.store.get, str(trip_id))
        except KeyError as error:
            raise HTTPException(404, "行程不存在。") from error

    def check_version(trip, expected):
        if trip["version"] != expected:
            raise HTTPException(409, "行程已有新版本，请刷新后再修改。")

    async def persist(call, *args):
        # Storage rechecks the version inside its write transaction.
        try:
            return await run_in_threadpool(call, *args)
        except KeyError as error:
            raise HTTPException(404, "行程或版本不存在。") from error
        except ValueError as error:
            raise HTTPException(409, str(error)) from error

    @router.get("/trips")
    async def trips(request: Request):
        return {"trips": await run_in_threadpool(request.app.state.store.list)}

    @router.post("/trips")
    async def create_trip(body: GenerateRequest, request: Request):
        async def execute():
            result = await request.app.state.planner.prepare(
                body.message, body.preferences, body.explicit_fields
            )
            if result["status"] != "ready":
                return result
            plan = Plan.model_validate(result["plan"])
            trip = await run_in_threadpool(
                request.app.state.store.create, plan.model_dump(mode="json")
            )
            return {"status": "ready", "trip": trip}

        return await work(execute)

    @router.get("/trips/{trip_id}")
    async def get_trip(trip_id: UUID, request: Request):
        return await lookup(request, trip_id)

    @router.post("/trips/{trip_id}/revise")
    async def revise_trip(trip_id: UUID, body: ReviseRequest, request: Request):
        async def execute():
            trip = await lookup(request, trip_id)
            check_version(trip, body.base_version)
            plan = await request.app.state.planner.revise(
                Plan.model_validate(trip["plan"]),
                body.message,
                body.day,
            )
            return await persist(
                request.app.state.store.revise,
                str(trip_id),
                plan.model_dump(mode="json"),
                body.base_version,
                body.message,
            )

        return await work(execute)

    @router.get("/trips/{trip_id}/versions")
    async def versions(trip_id: UUID, request: Request):
        await lookup(request, trip_id)
        return {
            "versions": await run_in_threadpool(
                request.app.state.store.versions, str(trip_id)
            )
        }

    @router.post("/trips/{trip_id}/meals/select")
    async def select_meal(trip_id: UUID, body: MealSelectionRequest, request: Request):
        async def execute():
            trip = await lookup(request, trip_id)
            check_version(trip, body.base_version)
            plan = await request.app.state.planner.select_meal(
                Plan.model_validate(trip["plan"]),
                body.day,
                body.slot,
                body.restaurant_id,
            )
            slot_label = "午餐" if body.slot == "lunch" else "晚餐"
            meal = next(
                meal
                for day in plan.days
                if day.day == body.day
                for meal in day.meals
                if meal.slot == body.slot
            )
            return await persist(
                request.app.state.store.revise,
                str(trip_id),
                plan.model_dump(mode="json"),
                body.base_version,
                f"第 {body.day} 天{slot_label}更换为{meal.restaurant.name}",
            )

        return await work(execute)

    @router.post("/trips/{trip_id}/restore")
    async def restore(trip_id: UUID, body: RestoreRequest, request: Request):
        return await persist(
            request.app.state.store.restore,
            str(trip_id),
            body.version,
            body.base_version,
        )

    @router.delete("/trips/{trip_id}")
    async def delete_trip(trip_id: UUID, request: Request):
        await persist(request.app.state.store.delete, str(trip_id))
        return {"deleted": True}

    @router.get("/trips/{trip_id}/export")
    async def export(
        trip_id: UUID, request: Request, format: Literal["md", "pdf", "ics"] = "md"
    ):
        trip = await lookup(request, trip_id)
        plan = Plan.model_validate(trip["plan"])
        if format == "pdf":
            content = await run_in_threadpool(export_pdf, plan)
            media = "application/pdf"
        elif format == "ics":
            content = await run_in_threadpool(export_ics, plan, str(trip_id))
            media = "text/calendar"
        else:
            content = await run_in_threadpool(export_markdown, plan)
            media = "text/markdown"
        filename = quote(f"{plan.title}-v{trip['version']}.{format}", safe="")
        return Response(
            content,
            media_type=media,
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
        )

    @router.get("/knowledge/documents")
    async def documents(request: Request):
        return {
            "documents": await run_in_threadpool(
                request.app.state.knowledge.list_documents
            )
        }

    @router.post("/knowledge/documents", status_code=201)
    async def add_document(body: DocumentRequest, request: Request):
        return await work(
            lambda: run_in_threadpool(
                request.app.state.knowledge.add_document,
                body.title,
                body.content,
                body.source_url,
            )
        )

    @router.post("/knowledge/upload", status_code=201)
    async def upload_document(request: Request, file: Annotated[UploadFile, File()]):
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in {".txt", ".md", ".pdf"}:
            raise HTTPException(422, "支持 TXT、Markdown 和 PDF 文件。")
        try:
            raw = await file.read(5 * 1024 * 1024 + 1)
        finally:
            await file.close()
        if len(raw) > 5 * 1024 * 1024:
            raise HTTPException(413, "文件大小须在 5 MB 以内。")

        def decode():
            if suffix == ".pdf":
                from pypdf import PdfReader

                reader = PdfReader(io.BytesIO(raw))
                if len(reader.pages) > 60:
                    raise ValueError("PDF 页数须在 60 页以内。")
                return "\n\n".join(page.extract_text() or "" for page in reader.pages)
            return raw.decode("utf-8-sig")

        try:
            content = await run_in_threadpool(decode)
            body = DocumentRequest(
                title=Path(file.filename).stem[:120], content=content
            )
        except Exception as error:
            raise HTTPException(
                422,
                "无法读取文件，请使用 UTF-8 文本或含文字层的 PDF（20–200000 字符、最多 60 页）。",
            ) from error
        return await add_document(body, request)

    @router.delete("/knowledge/documents/{document_id}")
    async def delete_document(document_id: str, request: Request):
        if len(document_id) > 100:
            raise HTTPException(422, "资料编号无效。")
        await work(
            lambda: run_in_threadpool(
                request.app.state.knowledge.delete_document, document_id
            )
        )
        return {"deleted": True}

    @router.post("/knowledge/ask")
    async def ask(body: QuestionRequest, request: Request):
        return await work(lambda: request.app.state.knowledge.answer(body.question))

    return router
