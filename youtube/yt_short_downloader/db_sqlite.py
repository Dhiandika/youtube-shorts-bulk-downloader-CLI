# yt_short_downloader/db_sqlite.py
import os
import sqlite3
import threading
from datetime import datetime
from typing import Optional, List

_DB_LOCK = threading.Lock()

class SqliteStore:
    def __init__(self, path: Optional[str] = None):
        base = path or os.path.join(os.getcwd(), "data", "ytshorts.db")
        os.makedirs(os.path.dirname(base), exist_ok=True)
        self.db_path = base
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS channels (
                    key TEXT PRIMARY KEY,
                    name TEXT,
                    url  TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS videos (
                    key TEXT PRIMARY KEY,
                    channel_key TEXT,
                    video_id TEXT,
                    title TEXT,
                    upload_date TEXT,
                    downloaded INTEGER DEFAULT 0,
                    created_at TEXT,
                    updated_at TEXT,
                    downloaded_at TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS counters (
                    key TEXT PRIMARY KEY,
                    last_index INTEGER,
                    updated_at TEXT
                )
            """)

    # ---------- channel ----------
    def upsert_channel(self, channel_key: str, name: str, url: str) -> None:
        now = datetime.utcnow().isoformat() + "Z"
        with _DB_LOCK, sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO channels(key,name,url,created_at,updated_at)
                VALUES(?,?,?,?,?)
                ON CONFLICT(key) DO UPDATE SET name=excluded.name,
                    url=excluded.url, updated_at=excluded.updated_at
            """, (channel_key, name, url, now, now))

    # ---------- video ----------
    def upsert_video(self, channel_key: str, video_id: str, title: str, upload_date: Optional[str]) -> None:
        now = datetime.utcnow().isoformat() + "Z"
        key = f"{channel_key}::{video_id}"
        with _DB_LOCK, sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO videos(key,channel_key,video_id,title,upload_date,downloaded,created_at,updated_at,downloaded_at)
                VALUES(?,?,?,?,?,0,?,?,NULL)
                ON CONFLICT(key) DO UPDATE SET title=excluded.title,
                    upload_date=excluded.upload_date, updated_at=excluded.updated_at
            """, (key, channel_key, video_id, title, upload_date, now, now))

    def mark_downloaded(self, channel_key: str, video_id: str) -> None:
        key = f"{channel_key}::{video_id}"
        now = datetime.utcnow().isoformat() + "Z"
        with _DB_LOCK, sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE videos SET downloaded=1, downloaded_at=?, updated_at=? WHERE key=?",
                         (now, now, key))

    def is_downloaded(self, channel_key: str, video_id: str) -> bool:
        key = f"{channel_key}::{video_id}"
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute("SELECT downloaded FROM videos WHERE key=?", (key,))
            row = cur.fetchone()
            return bool(row and row[0])

    # ---------- folder counters (atomic reserve) ----------
    def _folder_key(self, folder_path: str) -> str:
        return f"folder::{os.path.abspath(folder_path)}"

    def get_last_index(self, folder_path: str) -> int:
        key = self._folder_key(folder_path)
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute("SELECT last_index FROM counters WHERE key=?", (key,))
            row = cur.fetchone()
            return int(row[0]) if row and row[0] is not None else 0

    def set_last_index(self, folder_path: str, last_index: int) -> None:
        key = self._folder_key(folder_path)
        now = datetime.utcnow().isoformat() + "Z"
        with _DB_LOCK, sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO counters(key,last_index,updated_at)
                VALUES(?,?,?)
                ON CONFLICT(key) DO UPDATE SET last_index=excluded.last_index,
                    updated_at=excluded.updated_at
            """, (key, int(last_index), now))

    def reserve_indices(self, folder_path: str, count: int, fallback_probe: int = 0) -> list[int]:
        """
        Atomic: BEGIN IMMEDIATE agar tidak ada race antar thread.
        """
        key = self._folder_key(folder_path)
        with _DB_LOCK, sqlite3.connect(self.db_path, isolation_level=None) as conn:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.execute("SELECT last_index FROM counters WHERE key=?", (key,))
            row = cur.fetchone()
            base = max(int(row[0]) if row and row[0] is not None else 0, int(fallback_probe))
            start = base + 1
            end   = base + count
            now   = datetime.utcnow().isoformat() + "Z"
            conn.execute("""
                INSERT INTO counters(key,last_index,updated_at)
                VALUES(?,?,?)
                ON CONFLICT(key) DO UPDATE SET last_index=?, updated_at=?
            """, (key, end, now, end, now))
            conn.execute("COMMIT")
        return list(range(start, end + 1))
