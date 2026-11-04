"""Real-time scanner loop.

Discovers LIVE rooms from the configured seed accounts (public endpoints),
polls each live room's info, detects rương (treasure box) / túi (goody bag),
stores them, and fires automatic Telegram alerts.
"""
from __future__ import annotations

import asyncio
import os
import time
from typing import Dict, List, Set

from . import db
from .notify import notify_admin
from .tiktok import TikTokFetcher
from .ws_manager import set_main_loop, ws_manager

SEEDS_FILE = os.path.join(os.path.dirname(__file__), "..", "seeds.txt")


def _load_seed_file() -> List[str]:
    if not os.path.exists(SEEDS_FILE):
        return []
    out = []
    with open(SEEDS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                out.append(line.lstrip("@"))
    return out


def _parse_seeds(raw: str) -> List[str]:
    parts: List[str] = []
    for chunk in raw.replace(";", ",").replace("\n", ",").split(","):
        c = chunk.strip().lstrip("@")
        if c:
            parts.append(c)
    # merge with seed file
    merged = list(dict.fromkeys(parts + _load_seed_file()))
    return merged


class Scanner:
    def __init__(self) -> None:
        self.fetcher = TikTokFetcher()
        self._task: asyncio.Task | None = None
        self.running = False
        self.last_cycle: int = 0
        self.last_discover: int = 0
        self.live_map: Dict[str, str] = {}   # unique_id -> room_id
        self.cycle_count = 0
        self.sem = asyncio.Semaphore(8)

    async def start(self) -> None:
        if self.running:
            return
        self.running = True
        try:
            set_main_loop(asyncio.get_running_loop())
        except RuntimeError:
            pass
        self._task = asyncio.create_task(self._loop())
        db.add_log("info", "Scanner started")

    async def stop(self) -> None:
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except Exception:
                pass
        await self.fetcher.close()
        db.add_log("info", "Scanner stopped")

    # ------------------------------------------------------------------
    async def _discover(self, seeds: List[str], max_rooms: int) -> None:
        seeds = seeds[:max_rooms]
        found: Dict[str, str] = {}
        results = await asyncio.gather(*[self.fetcher.get_live_room_id(u) for u in seeds])
        for u, rid in zip(seeds, results):
            if rid:
                found[u] = rid
        # mark rooms no longer live as offline
        gone = [rid for u, rid in self.live_map.items() if u not in found]
        if gone:
            db.mark_offline(gone)
        self.live_map = found
        self.last_discover = int(time.time())
        db.add_log("info", f"Quét {len(seeds)} kênh → {len(found)} đang LIVE")

    async def _poll_room(self, unique_id: str, room_id: str, settings: Dict[str, str]) -> None:
        async with self.sem:
            info = await self.fetcher.get_room_info(room_id)
        if not info:
            return
        summary = self.fetcher.room_summary(info, unique_id)
        summary["room_id"] = room_id
        db.upsert_room(summary)

        prizes = self.fetcher.parse_prizes(info)
        if not prizes:
            return

        min_coins = int(settings.get("min_coins", "0") or 0)
        min_ratio = float(settings.get("min_ratio", "0") or 0)
        min_viewers = int(settings.get("min_viewers", "0") or 0)
        allowed_types = set((settings.get("types") or "ruong,tui").split(","))
        allowed_levels = set()
        for x in (settings.get("levels") or "").split(","):
            x = x.strip()
            if x.isdigit():
                allowed_levels.add(int(x))

        if summary.get("viewers", 0) < min_viewers:
            return

        for p in prizes:
            if p["kind"] not in allowed_types:
                continue
            if p["coins"] < min_coins:
                continue
            if p["ratio"] < min_ratio:
                continue
            if p["kind"] == "tui" and p.get("level") is not None and allowed_levels:
                if p["level"] not in allowed_levels:
                    continue
            did = db.add_detection(p, summary)
            if did:
                det = {
                    "id": did, "kind": p["kind"], "coins": p["coins"],
                    "winners": p["winners"], "ratio": p["ratio"], "level": p.get("level"),
                    "open_ts": p["open_ts"], "unique_id": summary.get("unique_id"),
                    "nickname": summary.get("nickname"), "link": summary.get("link"),
                }
                db.add_log("info", f"Phát hiện {p['kind']} {p['coins']}xu @{summary.get('unique_id')}")
                asyncio.create_task(notify_admin(det, summary))

    async def _loop(self) -> None:
        while self.running:
            try:
                settings = db.get_settings()
                seeds = _parse_seeds(settings.get("seeds", ""))
                max_rooms = int(settings.get("max_rooms", "300") or 300)
                poll_interval = max(5, int(settings.get("poll_interval", "20") or 20))
                discover_interval = max(30, int(settings.get("discover_interval", "90") or 90))

                now = int(time.time())
                if not self.live_map or now - self.last_discover >= discover_interval:
                    if seeds:
                        await self._discover(seeds, max_rooms)
                    else:
                        db.add_log("warn", "Chưa có seed kênh nào. Thêm kênh ở trang Admin.")

                # poll all currently-live rooms (viewers, title, room-info chests)
                if self.live_map:
                    await asyncio.gather(*[
                        self._poll_room(u, rid, settings) for u, rid in self.live_map.items()
                    ])

                # real-time WebSocket listeners for envelope (rương/túi) events
                try:
                    rooms = db.live_rooms(max_rooms)
                    ws_manager.sync(rooms, int(settings.get("max_ws", "12") or 12))
                except Exception as e:
                    db.add_log("warn", f"WS sync lỗi: {e}")

                self.last_cycle = int(time.time())
                self.cycle_count += 1
                await asyncio.sleep(poll_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                db.add_log("error", f"Scanner loop error: {e}")
                await asyncio.sleep(10)


scanner = Scanner()
