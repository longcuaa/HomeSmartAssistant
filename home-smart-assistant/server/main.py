"""Diem vao FastAPI cho server Home Smart Assistant (Phase 1).

Endpoint da co:
  POST /command/text   — gui lenh dang van ban (test khong can audio), tra ve intent da phan giai
  GET  /devices        — danh sach thiet bi + trang thai
  GET  /devices/{id}   — mot thiet bi
  GET  /rooms          — danh sach phong
  GET  /rooms/{id}/devices — thiet bi trong mot phong
  GET  /health         — suc khoe server + backend dang dung
  GET  /metrics        — do tre theo tang, ti le trung cache
  DELETE /cache        — xoa cache intent

Cac endpoint audio (/voice), WebSocket (/ws), scene, MQTT thuc thi se them o Phase 2-3.

Chay: uvicorn server.main:app   (tu thu muc goc)
"""
from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from server.config import cfg
from server.core.devices.registry import Registry
from server.core.intent.resolver import Resolver

# Nap registry + resolver mot lan khi khoi dong.
registry = Registry.from_files(
    cfg.resolve_path("data.devices"),
    cfg.resolve_path("data.rooms"),
    cfg.resolve_path("data.scenes"),
)
resolver = Resolver(cfg, registry)

app = FastAPI(title="Home Smart Assistant", version="0.1.0")


class TextCommand(BaseModel):
    text: str
    room: Optional[str] = None      # room_id; uu tien hon bot_id neu ca hai cung co
    bot_id: Optional[str] = None


def _room_of_bot(bot_id):
    for rid, r in registry.rooms.items():
        if r.get("bot_id") == bot_id:
            return rid
    return None


@app.post("/command/text")
def command_text(cmd: TextCommand):
    """Phan giai mot lenh van ban qua 4 tang va tra ve intent (chua thuc thi thiet bi o Phase 1)."""
    room = cmd.room or _room_of_bot(cmd.bot_id)
    intent = resolver.resolve(cmd.text, room)
    return intent.model_dump()


@app.get("/devices")
def list_devices():
    return [_device_view(d) for d in registry.devices.values()]


@app.get("/devices/{device_id}")
def get_device(device_id: str):
    d = registry.get(device_id)
    if not d:
        raise HTTPException(404, f"Khong co thiet bi '{device_id}'")
    return _device_view(d)


@app.get("/rooms")
def list_rooms():
    return [{"id": rid, "name": r.get("name"), "bot_id": r.get("bot_id")}
            for rid, r in registry.rooms.items()]


@app.get("/rooms/{room_id}/devices")
def room_devices(room_id: str):
    if room_id not in registry.rooms:
        raise HTTPException(404, f"Khong co phong '{room_id}'")
    return [_device_view(d) for d in registry.devices.values() if d.room == room_id]


@app.get("/health")
def health():
    return {
        "status": "ok",
        "devices": len(registry.devices),
        "rooms": len(registry.rooms),
        "scenes": len(registry.scenes),
        "cache_backend": resolver.cache.backend,
        "embedding_backend": resolver.embed.backend,
        "llm_model": cfg.get("models.llm.model"),
    }


@app.get("/metrics")
def metrics():
    return resolver.metrics()


@app.delete("/cache")
def clear_cache():
    resolver.cache.clear()
    return {"status": "cleared", "backend": resolver.cache.backend}


def _device_view(d):
    return {"id": d.id, "type": d.type, "name": d.name, "room": d.room,
            "capabilities": d.capabilities, "state": d.state, "mqtt_topic": d.mqtt_topic}
