"""TikTok LIVE fetcher — uses TikTok's PUBLIC web endpoints.

No official TikTok API key. No TikTok login. No session cookie.
This reads the same public JSON the TikTok website itself loads.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional

import httpx

from TikTokLive.client.web.web_client import TikTokWebClient
from TikTokLive.client.web.routes.fetch_room_info import FetchRoomInfoRoute
from TikTokLive.client.web.routes.fetch_room_id_api import FetchRoomIdAPIRoute

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _first_url(img: Any) -> str:
    if not img:
        return ""
    if isinstance(img, dict):
        urls = img.get("url_list") or img.get("urlList") or []
        if urls:
            return urls[0]
        if img.get("url"):
            return img["url"]
    if isinstance(img, str):
        return img
    return ""


def _to_int(v: Any, default: int = 0) -> int:
    try:
        return int(float(v))
    except Exception:
        return default


class TikTokFetcher:
    """Thin async wrapper around the public TikTok webcast endpoints."""

    def __init__(self) -> None:
        self.web = TikTokWebClient()
        self.room_info_route = FetchRoomInfoRoute(self.web)

    async def close(self) -> None:
        try:
            await self.web.close()
        except Exception:
            pass

    async def get_live_room_id(self, unique_id: str) -> Optional[str]:
        """Return the room_id if the user is currently LIVE, else None.

        Uses TikTok's public ``/api-live/user/room/`` endpoint. TikTok requires
        ``aid=1988`` (web app id) plus ``sourceType=54``; without them the API
        replies ``params_error``.
        """
        unique_id = unique_id.strip().lstrip("@")
        if not unique_id:
            return None
        url = "https://www.tiktok.com/api-live/user/room/"
        params = {
            "uniqueId": unique_id,
            "sourceType": "54",
            "aid": "1988",
            "app_language": "vi-VN",
            "app_name": "tiktok_web",
            "device_platform": "web_pc",
            "region": "VN",
            "priority_region": "VN",
        }
        headers = {
            "User-Agent": _UA,
            "Referer": f"https://www.tiktok.com/@{unique_id}",
            "Accept": "application/json, text/plain, */*",
        }
        data: Dict[str, Any] = {}
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                r = await client.get(url, params=params, headers=headers)
                if r.status_code == 200:
                    data = r.json()
        except Exception:
            data = {}
        if not data:
            # Fallback to the TikTokLive helper (may work in some regions)
            try:
                data = await FetchRoomIdAPIRoute.fetch_user_room_data(self.web, unique_id)
            except Exception:
                return None
        user = (data.get("data") or {}).get("user") or {}
        rid = user.get("roomId") or user.get("room_id")
        if rid and str(rid) != "0":
            return str(rid)
        return None

    async def get_room_info(self, room_id: str) -> Optional[Dict[str, Any]]:
        try:
            return await self.room_info_route(room_id=int(room_id))
        except Exception:
            return None

    @staticmethod
    def parse_prizes(info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract treasure-box (rương) and goody-bag (túi) events from room info.

        Returns a list of dicts:
            {kind: 'ruong'|'tui', coins, winners, ratio, level, open_ts}
        """
        prizes: List[Dict[str, Any]] = []
        now = int(time.time())

        # --- RƯƠNG / TREASURE BOX -----------------------------------------
        tb = info.get("treasure_box_data") or info.get("treasureBoxData")
        if isinstance(tb, dict) and tb:
            coins = _to_int(tb.get("coins") or tb.get("coin_count") or tb.get("diamond"))
            winners = _to_int(tb.get("can_open") or tb.get("winners") or tb.get("user_count"))
            ts = _to_int(tb.get("timestamp") or tb.get("open_time"))
            open_ts = int(ts / 1000) if ts > 1_000_000_000_000 else ts
            if coins > 0:
                prizes.append({
                    "kind": "ruong",
                    "coins": coins,
                    "winners": winners,
                    "ratio": round(coins / winners, 2) if winners > 0 else 0.0,
                    "level": None,
                    "open_ts": open_ts or (now + 60),
                })

        # --- TÚI / GOODY BAG ----------------------------------------------
        # Goody bags surface either as a top-level goody_bag object or inside
        # treasure_box_data with a business/level marker.
        goody_candidates = []
        for k, v in info.items():
            lk = k.lower()
            if ("goody" in lk or "lucky_bag" in lk or "luckybag" in lk) and isinstance(v, dict):
                goody_candidates.append(v)
        if isinstance(tb, dict):
            if any(x in tb for x in ("level", "goody_bag", "business_type", "bag_level")):
                goody_candidates.append(tb)

        for gb in goody_candidates:
            coins = _to_int(gb.get("coins") or gb.get("coin_count") or gb.get("diamond"))
            winners = _to_int(gb.get("can_open") or gb.get("winners") or gb.get("user_count"))
            level = _to_int(gb.get("level") or gb.get("bag_level"), -1)
            ts = _to_int(gb.get("timestamp") or gb.get("open_time"))
            open_ts = int(ts / 1000) if ts > 1_000_000_000_000 else ts
            if coins > 0:
                prizes.append({
                    "kind": "tui",
                    "coins": coins,
                    "winners": winners,
                    "ratio": round(coins / winners, 2) if winners > 0 else 0.0,
                    "level": level if level >= 0 else None,
                    "open_ts": open_ts or (now + 60),
                })

        # de-dupe
        seen = set()
        uniq = []
        for p in prizes:
            key = (p["kind"], p["coins"], p["winners"], p["open_ts"])
            if key in seen:
                continue
            seen.add(key)
            uniq.append(p)
        return uniq

    @staticmethod
    def room_summary(info: Dict[str, Any], unique_id: str) -> Dict[str, Any]:
        owner = info.get("owner") or {}
        stats = info.get("stats") or {}
        return {
            "room_id": str(info.get("id_str") or info.get("id") or ""),
            "unique_id": owner.get("unique_id") or unique_id,
            "nickname": owner.get("nickname") or owner.get("unique_id") or unique_id,
            "avatar": _first_url(owner.get("avatar_thumb") or owner.get("avatar_medium")),
            "title": info.get("title") or "",
            "viewers": _to_int(info.get("user_count") or stats.get("total_user")),
            "link": f"https://www.tiktok.com/@{owner.get('unique_id') or unique_id}/live",
        }
