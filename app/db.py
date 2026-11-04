"""SQLite persistence layer."""
from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import Any, Dict, List, Optional

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "..", "data.db"))

DEFAULT_SETTINGS: Dict[str, str] = {
    "min_coins": "0",
    "min_ratio": "0",
    "min_viewers": "0",
    "types": "ruong,tui",
    "levels": "0,1,2,3,4,5,6,7,8,9,10",
    "poll_interval": "20",
    "discover_interval": "90",
    "max_rooms": "300",
    "max_ws": "12",
    "telegram_token": "",
    "telegram_chat": "",
    "telegram_enabled": "0",
    "admin_password": "admin123",
    "site_name": "RươngTúi Live",
    "seeds": "",
}


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    conn = _conn()
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY, value TEXT NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS rooms (
        room_id TEXT PRIMARY KEY,
        unique_id TEXT, nickname TEXT, avatar TEXT, title TEXT,
        viewers INTEGER DEFAULT 0, is_live INTEGER DEFAULT 1,
        first_seen INTEGER, last_seen INTEGER, link TEXT, raw TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS detections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        room_id TEXT, unique_id TEXT, nickname TEXT, avatar TEXT,
        kind TEXT, coins INTEGER, winners INTEGER, ratio REAL,
        level INTEGER, open_ts INTEGER, detected_at INTEGER,
        link TEXT, notified INTEGER DEFAULT 0)""")
    c.execute("""CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts INTEGER, level TEXT, message TEXT)""")
    conn.commit()
    # seed defaults
    for k, v in DEFAULT_SETTINGS.items():
        c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k, v))
    conn.commit()
    conn.close()


def get_settings() -> Dict[str, str]:
    conn = _conn()
    rows = conn.execute("SELECT key,value FROM settings").fetchall()
    conn.close()
    out = dict(DEFAULT_SETTINGS)
    for r in rows:
        out[r["key"]] = r["value"]
    # Environment overrides (useful on PaaS where the disk is ephemeral)
    env_map = {
        "TELEGRAM_TOKEN": "telegram_token",
        "TELEGRAM_CHAT": "telegram_chat",
        "TELEGRAM_ENABLED": "telegram_enabled",
        "ADMIN_PASSWORD": "admin_password",
        "SITE_NAME": "site_name",
        "SEEDS": "seeds",
    }
    for env_key, setting_key in env_map.items():
        val = os.environ.get(env_key)
        if val:
            out[setting_key] = val
    return out


def set_settings(values: Dict[str, Any]) -> None:
    conn = _conn()
    for k, v in values.items():
        conn.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (k, str(v)),
        )
    conn.commit()
    conn.close()


def upsert_room(summary: Dict[str, Any]) -> None:
    now = int(time.time())
    conn = _conn()
    conn.execute(
        """INSERT INTO rooms(room_id,unique_id,nickname,avatar,title,viewers,is_live,first_seen,last_seen,link,raw)
           VALUES(?,?,?,?,?,?,1,?,?,?,?)
           ON CONFLICT(room_id) DO UPDATE SET
             nickname=excluded.nickname, avatar=excluded.avatar, title=excluded.title,
             viewers=excluded.viewers, is_live=1, last_seen=excluded.last_seen, link=excluded.link""",
        (summary.get("room_id"), summary.get("unique_id"), summary.get("nickname"),
         summary.get("avatar"), summary.get("title"), summary.get("viewers", 0),
         now, now, summary.get("link"), json.dumps(summary, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()


def mark_offline(room_ids: List[str]) -> None:
    if not room_ids:
        return
    conn = _conn()
    q = ",".join("?" for _ in room_ids)
    conn.execute(f"UPDATE rooms SET is_live=0 WHERE room_id IN ({q})", room_ids)
    conn.commit()
    conn.close()


def add_detection(prize: Dict[str, Any], room: Dict[str, Any]) -> Optional[int]:
    """Insert a detection if this exact event was not already recorded. Returns id or None."""
    conn = _conn()
    now = int(time.time())
    # de-dupe: same room + kind + coins + open_ts within last 30 min
    row = conn.execute(
        """SELECT id FROM detections WHERE room_id=? AND kind=? AND coins=? AND open_ts=?
           AND detected_at > ? LIMIT 1""",
        (room["room_id"], prize["kind"], prize["coins"], prize["open_ts"], now - 1800),
    ).fetchone()
    if row:
        conn.close()
        return None
    cur = conn.execute(
        """INSERT INTO detections(room_id,unique_id,nickname,avatar,kind,coins,winners,ratio,level,open_ts,detected_at,link)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        (room["room_id"], room.get("unique_id"), room.get("nickname"), room.get("avatar"),
         prize["kind"], prize["coins"], prize["winners"], prize["ratio"], prize.get("level"),
         prize["open_ts"], now, room.get("link")),
    )
    conn.commit()
    did = cur.lastrowid
    conn.close()
    return did


def mark_notified(detection_id: int) -> None:
    conn = _conn()
    conn.execute("UPDATE detections SET notified=1 WHERE id=?", (detection_id,))
    conn.commit()
    conn.close()


def recent_detections(limit: int = 100) -> List[Dict[str, Any]]:
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM detections ORDER BY detected_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def live_rooms(limit: int = 300) -> List[Dict[str, Any]]:
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM rooms WHERE is_live=1 ORDER BY viewers DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_log(level: str, message: str) -> None:
    conn = _conn()
    conn.execute("INSERT INTO logs(ts,level,message) VALUES(?,?,?)",
                 (int(time.time()), level, message))
    # keep last 2000
    conn.execute("DELETE FROM logs WHERE id NOT IN (SELECT id FROM logs ORDER BY id DESC LIMIT 2000)")
    conn.commit()
    conn.close()


def recent_logs(limit: int = 200) -> List[Dict[str, Any]]:
    conn = _conn()
    rows = conn.execute("SELECT * FROM logs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def stats() -> Dict[str, Any]:
    conn = _conn()
    now = int(time.time())
    live = conn.execute("SELECT COUNT(*) c FROM rooms WHERE is_live=1").fetchone()["c"]
    today = conn.execute("SELECT COUNT(*) c FROM detections WHERE detected_at>?", (now - 86400,)).fetchone()["c"]
    total = conn.execute("SELECT COUNT(*) c FROM detections").fetchone()["c"]
    conn.close()
    return {"live": live, "detections_24h": today, "detections_total": total}
