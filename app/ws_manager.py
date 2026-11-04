"""Real-time WebSocket listener manager.

For each tracked LIVE room we open a TikTok LIVE WebSocket (public webcast,
no login) and listen for EnvelopeEvent — the message that carries rương
(treasure box) and túi (goody bag) data: coins, winners, open time.

Runs each connection in its own daemon thread (the TikTokLive client owns its
own event loop), and forwards detections to the main asyncio loop for
persistence + Telegram notification.
"""
from __future__ import annotations

import asyncio
import threading
import time
from typing import Any, Dict, List, Optional

from TikTokLive import TikTokLiveClient
from TikTokLive.events import ConnectEvent, DisconnectEvent, EnvelopeEvent

from . import db

_main_loop: Optional[asyncio.AbstractEventLoop] = None


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _main_loop
    _main_loop = loop


def _num(x: Any) -> int:
    try:
        return int(x)
    except Exception:
        return 0


def parse_envelope(e: EnvelopeEvent) -> Optional[Dict[str, Any]]:
    """Extract prize data from an EnvelopeEvent (rương / túi)."""
    now = int(time.time())

    # 1) treasure-box variant (rương) — some protocol versions carry this
    tb = getattr(e, "treasure_box_data", None)
    if tb is not None:
        coins = _num(getattr(tb, "coins", 0))
        winners = _num(getattr(tb, "can_open", 0))
        ts = _num(getattr(tb, "timestamp", 0))
        open_ts = int(ts / 1000) if ts > 1_000_000_000_000 else ts
        if coins > 0:
            return {
                "kind": "ruong", "coins": coins, "winners": winners,
                "ratio": round(coins / winners, 2) if winners > 0 else 0.0,
                "level": None, "open_ts": open_ts or now + 60,
                "business_type": 0,
            }

    # 2) red-envelope / goody-bag variant (túi)
    ei = getattr(e, "envelope_info", None)
    if ei is not None:
        coins = _num(getattr(ei, "diamond_count", 0))
        winners = _num(getattr(ei, "people_count", 0))
        open_ts = _num(getattr(ei, "unpack_at", 0)) or (now + 60)
        bt = _num(getattr(ei, "business_type", 0))
        # SUPER_FAN_BOX (19) behaves like a treasure box
        kind = "ruong" if bt == 19 else "tui"
        if coins > 0:
            return {
                "kind": kind, "coins": coins, "winners": winners,
                "ratio": round(coins / winners, 2) if winners > 0 else 0.0,
                "level": None, "open_ts": open_ts,
                "business_type": bt,
            }
    return None


class WSManager:
    def __init__(self) -> None:
        self._threads: Dict[str, threading.Thread] = {}
        self._stop: Dict[str, bool] = {}
        self.max_ws = 12

    def active_count(self) -> int:
        return sum(1 for t in self._threads.values() if t.is_alive())

    def sync(self, rooms: List[Dict[str, Any]], max_ws: int) -> None:
        """Start listeners for new rooms (cap = max_ws, highest viewers first)."""
        self.max_ws = max_ws
        rooms = sorted(rooms, key=lambda r: r.get("viewers", 0), reverse=True)[:max_ws]
        target_ids = set()
        for room in rooms:
            rid = str(room.get("room_id"))
            target_ids.add(rid)
            t = self._threads.get(rid)
            if t is None or not t.is_alive():
                self._stop[rid] = False
                th = threading.Thread(
                    target=self._worker, args=(room,), daemon=True,
                    name=f"ws-{rid}",
                )
                self._threads[rid] = th
                th.start()
        # prune finished
        for rid in list(self._threads.keys()):
            if rid not in target_ids and not self._threads[rid].is_alive():
                self._threads.pop(rid, None)
                self._stop.pop(rid, None)

    def _worker(self, room: Dict[str, Any]) -> None:
        uid = room.get("unique_id")
        rid = str(room.get("room_id"))
        client = TikTokLiveClient(unique_id="@" + uid)

        @client.on(ConnectEvent)
        def _on_connect(e):
            db.add_log("info", f"WS kết nối @{uid} (room {rid})")

        @client.on(EnvelopeEvent)
        def _on_env(e):
            prize = parse_envelope(e)
            if not prize:
                return
            did = db.add_detection(prize, room)
            if not did:
                return
            det = {
                "id": did, "kind": prize["kind"], "coins": prize["coins"],
                "winners": prize["winners"], "ratio": prize["ratio"],
                "level": prize.get("level"), "open_ts": prize["open_ts"],
                "unique_id": uid, "nickname": room.get("nickname"),
                "link": room.get("link"),
            }
            db.add_log("info", f"WS phát hiện {prize['kind']} {prize['coins']}xu @{uid}")
            if _main_loop and not _main_loop.is_closed():
                from .notify import notify_admin
                asyncio.run_coroutine_threadsafe(notify_admin(det, room), _main_loop)

        try:
            client.run(fetch_live_check=False, room_id=int(rid))
        except Exception as ex:
            db.add_log("warn", f"WS @{uid} dừng: {type(ex).__name__}")
        finally:
            db.add_log("info", f"WS đóng @{uid}")


ws_manager = WSManager()
