"""Automatic Telegram notifier for the admin.

Sends a message to the configured Telegram bot/chat the moment a qualifying
rương/túi is detected. No manual entry — fully automatic.
"""
from __future__ import annotations

import httpx
from typing import Any, Dict, Optional

from . import db


def _fmt_prize(det: Dict[str, Any], room: Dict[str, Any]) -> str:
    kind = "🎁 RƯƠNG" if det["kind"] == "ruong" else "👜 TÚI"
    lines = [
        f"{kind} MỚI — {det.get('nickname') or det.get('unique_id')}",
        f"👤 @{det.get('unique_id')}",
        f"🪙 {det['coins']:,} xu  ·  👥 {det.get('winners') or '?'} suất  ·  ⚖️ ratio {det.get('ratio')}",
    ]
    if det.get("level") is not None:
        lines.append(f"🏷️ Level {det['level']}")
    if det.get("open_ts"):
        import datetime
        t = datetime.datetime.fromtimestamp(det["open_ts"]).strftime("%H:%M:%S")
        lines.append(f"⏰ Mở lúc {t}")
    if room.get("viewers"):
        lines.append(f"👀 {room['viewers']:,} người xem")
    lines.append(f"🔗 {det.get('link')}")
    return "\n".join(lines)


async def notify_admin(det: Dict[str, Any], room: Dict[str, Any]) -> bool:
    s = db.get_settings()
    if s.get("telegram_enabled") != "1":
        return False
    token = (s.get("telegram_token") or "").strip()
    chat = (s.get("telegram_chat") or "").strip()
    if not token or not chat:
        return False
    text = _fmt_prize(det, room)
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(url, json={
                "chat_id": chat,
                "text": text,
                "disable_web_page_preview": False,
            })
        if r.status_code == 200 and r.json().get("ok"):
            db.mark_notified(det["id"])
            db.add_log("info", f"Đã gửi Telegram: {det['kind']} {det['coins']}xu @{det.get('unique_id')}")
            return True
        db.add_log("error", f"Telegram lỗi {r.status_code}: {r.text[:200]}")
    except Exception as e:
        db.add_log("error", f"Telegram exception: {e}")
    return False


async def send_test(token: str, chat: str) -> Dict[str, Any]:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(url, json={
            "chat_id": chat,
            "text": "✅ RươngTúi Live — kết nối Telegram thành công!\nThông báo rương/túi sẽ tự động gửi về đây.",
        })
    try:
        j = r.json()
    except Exception:
        j = {"ok": False, "raw": r.text[:200]}
    return {"status": r.status_code, **j}
