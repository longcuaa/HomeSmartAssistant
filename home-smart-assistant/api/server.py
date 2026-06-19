"""API cho Home Smart Assistant.

Chay: uvicorn api.server:app  (tu thu muc goc, o production khong dung --reload)

Khi chay, mot bo lich nen tu cap nhat tai lieu tu cac nguon trong sources.txt moi
sang. Neu sources.txt trong thi viec cap nhat se duoc bo qua, nen tinh nang nay la
tuy chon, chi hoat dong khi ban them nguon.
"""
import asyncio
import json
from contextlib import asynccontextmanager
from typing import Optional, List
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app import butler, scheduler, vector_store

_sched = None


@asynccontextmanager
async def lifespan(app):
    global _sched
    _sched = scheduler.start_background()
    yield
    if _sched:
        _sched.shutdown()


app = FastAPI(title="Home Smart Assistant API", lifespan=lifespan)


class ChatIn(BaseModel):
    message: str
    history: Optional[List[dict]] = None


@app.get("/health")
def health():
    return {"status": "ok", "chunks": vector_store.count()}


@app.post("/chat")
def chat(inp: ChatIn):
    """Tro chuyen voi quan gia, dieu khien thiet bi va tra cuu tai lieu."""
    reply, history = butler.chat(inp.message, inp.history)
    return {"reply": reply, "history": history}


@app.post("/chat/stream")
async def chat_stream(inp: ChatIn):
    """Tro chuyen dang stream, tra ve Server-Sent Events tung token cho client web/mobile."""
    async def event_source():
        gen = butler.chat_stream(inp.message, inp.history)
        loop = asyncio.get_event_loop()
        sentinel = object()

        def _next():
            try:
                return next(gen)
            except StopIteration:
                return sentinel

        while True:
            # Keo tung token tu generator dong bo trong executor, tranh block event loop.
            token = await loop.run_in_executor(None, _next)
            if token is sentinel:
                break
            yield f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(event_source(), media_type="text/event-stream")


@app.post("/update")
def update():
    """Chay ngay viec cap nhat tai lieu tu cac nguon bao, dung de kiem tra lich."""
    scheduler.daily_update()
    return {"status": "done", "chunks": vector_store.count()}
