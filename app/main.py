"""FastAPI application: API + static frontend + admin."""
from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, List

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import db
from .notify import send_test
from .scanner import scanner
from .tiktok import TikTokFetcher

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(BASE, "web")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    db.add_log("info", "Server khởi động")
    await scanner.start()
    yield
    await scanner.stop()


app = FastAPI(title="RươngTúi Live Scanner", lifespan=lifespan)
app.mount("/assets", StaticFiles(directory=os.path.join(WEB, "assets")), name="assets")


# ----------------------------- public API -----------------------------
@app.get("/api/live")
def api_live(type: str = "all", min_coins: int = 0, min_ratio: float = 0.0,
             limit: int = 100) -> Dict[str, Any]:
    now = int(time.time())
    rooms = {r["room_id"]: r for r in db.live_rooms(1000)}
    items: List[Dict[str, Any]] = []
    for det in db.recent_detections(400):
        # active window: event still upcoming or detected < 15 min ago
        if det["detected_at"] < now - 900:
            continue
        if det["open_ts"] < now - 120:
            continue
        if type != "all" and det["kind"] != type:
            continue
        if det["coins"] < min_coins:
            continue
        if (det["ratio"] or 0) < min_ratio:
            continue
        room = rooms.get(det["room_id"], {})
        items.append({
            "id": det["id"],
            "room_id": det["room_id"],
            "unique_id": det["unique_id"],
            "nickname": det["nickname"],
            "avatar": det.get("avatar") or room.get("avatar"),
            "title": room.get("title", ""),
            "viewers": room.get("viewers", 0),
            "kind": det["kind"],
            "coins": det["coins"],
            "winners": det["winners"],
            "ratio": det["ratio"],
            "level": det.get("level"),
            "open_ts": det["open_ts"],
            "countdown": max(0, det["open_ts"] - now),
            "link": det.get("link"),
            "detected_at": det["detected_at"],
        })
    items.sort(key=lambda x: x["open_ts"])
    return {"items": items[:limit], "stats": db.stats(), "now": now}


@app.get("/api/stats")
def api_stats() -> Dict[str, Any]:
    return db.stats()


# ----------------------------- admin auth -----------------------------
def _check_admin(pw: str | None) -> None:
    if not pw or pw != db.get_settings().get("admin_password"):
        raise HTTPException(status_code=401, detail="Sai mật khẩu admin")


@app.post("/api/admin/login")
async def admin_login(request: Request) -> Dict[str, Any]:
    body = await request.json()
    if body.get("password") != db.get_settings().get("admin_password"):
        raise HTTPException(status_code=401, detail="Sai mật khẩu")
    return {"ok": True}


@app.get("/api/admin/settings")
def admin_settings(x_admin_pass: str | None = Header(default=None)) -> Dict[str, Any]:
    _check_admin(x_admin_pass)
    s = db.get_settings()
    s.pop("admin_password", None)
    return s


@app.post("/api/admin/settings")
async def admin_save(request: Request, x_admin_pass: str | None = Header(default=None)) -> Dict[str, Any]:
    _check_admin(x_admin_pass)
    body = await request.json()
    allowed = {"min_coins", "min_ratio", "min_viewers", "types", "levels",
               "poll_interval", "discover_interval", "max_rooms", "max_ws",
               "telegram_token", "telegram_chat", "telegram_enabled",
               "site_name", "seeds", "admin_password"}
    values = {k: v for k, v in body.items() if k in allowed and v is not None}
    if "admin_password" in values and not str(values["admin_password"]).strip():
        values.pop("admin_password")
    db.set_settings(values)
    db.add_log("info", "Admin cập nhật cấu hình")
    return {"ok": True}


@app.get("/api/admin/logs")
def admin_logs(x_admin_pass: str | None = Header(default=None), limit: int = 200) -> List[Dict[str, Any]]:
    _check_admin(x_admin_pass)
    return db.recent_logs(limit)


@app.get("/api/admin/status")
def admin_status(x_admin_pass: str | None = Header(default=None)) -> Dict[str, Any]:
    _check_admin(x_admin_pass)
    return {
        "running": scanner.running,
        "cycle_count": scanner.cycle_count,
        "last_cycle": scanner.last_cycle,
        "last_discover": scanner.last_discover,
        "live_tracked": len(scanner.live_map),
        "stats": db.stats(),
        "now": int(time.time()),
    }


@app.post("/api/admin/scanner")
async def admin_scanner(request: Request, x_admin_pass: str | None = Header(default=None)) -> Dict[str, Any]:
    _check_admin(x_admin_pass)
    body = await request.json()
    action = body.get("action")
    if action == "start":
        await scanner.start()
    elif action == "stop":
        await scanner.stop()
    return {"ok": True, "running": scanner.running}


@app.post("/api/admin/check-channel")
async def admin_check_channel(request: Request, x_admin_pass: str | None = Header(default=None)) -> Dict[str, Any]:
    """Resolve a TikTok link/username and report whether it is LIVE right now."""
    _check_admin(x_admin_pass)
    body = await request.json()
    raw = (body.get("value") or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="Nhập username hoặc link TikTok")
    from .scanner import normalize_seed

    username = normalize_seed(raw)
    if not username:
        raise HTTPException(status_code=400, detail="Không đọc được username từ nội dung đã nhập")
    room_id = await scanner.fetcher.get_live_room_id(username)
    if not room_id:
        return {"ok": True, "username": username, "live": False, "message": "Kênh này hiện KHÔNG phát LIVE"}
    info = await scanner.fetcher.get_room_info(room_id)
    if not info:
        return {"ok": True, "username": username, "live": True, "room_id": room_id,
                "message": "Đang LIVE nhưng không đọc được thông tin phòng"}
    summary = TikTokFetcher.room_summary(info, username)
    prizes = TikTokFetcher.parse_prizes(info)
    return {
        "ok": True,
        "username": username,
        "live": True,
        "room_id": room_id,
        "title": summary.get("title"),
        "viewers": summary.get("viewers"),
        "prizes": prizes,
        "message": "Đang LIVE" + (f" — có {len(prizes)} rương/túi" if prizes else " — chưa có rương/túi"),
    }


@app.post("/api/admin/test-telegram")
async def admin_test_telegram(request: Request, x_admin_pass: str | None = Header(default=None)) -> Dict[str, Any]:
    _check_admin(x_admin_pass)
    body = await request.json()
    token = body.get("token") or db.get_settings().get("telegram_token")
    chat = body.get("chat") or db.get_settings().get("telegram_chat")
    if not token or not chat:
        raise HTTPException(status_code=400, detail="Thiếu token hoặc chat id")
    res = await send_test(token, chat)
    return res


# ----------------------------- pages -----------------------------
@app.get("/")
def index() -> FileResponse:
    return FileResponse(os.path.join(WEB, "index.html"))


@app.get("/admin")
def admin_page() -> FileResponse:
    return FileResponse(os.path.join(WEB, "admin.html"))


@app.get("/health")
def health() -> Dict[str, Any]:
    return {"ok": True, "time": int(time.time())}
