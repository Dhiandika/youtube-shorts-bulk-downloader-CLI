import sqlite3
from datetime import datetime
import threading

from .config import DEFAULT_DB

DB_LOCK = threading.Lock()

class TikTokDB:
    def __init__(self, db_path=DEFAULT_DB):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA synchronous=NORMAL;")
        self.init_schema()

    def init_schema(self):
        with self.conn:
            self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                handle TEXT UNIQUE,
                display_name TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT UNIQUE,
                url TEXT,
                title TEXT,
                uploader_handle TEXT,
                status TEXT,
                file_path TEXT,
                caption_path TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS user_videos (
                uploader_handle TEXT,
                video_id TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (uploader_handle, video_id)
            );

            CREATE INDEX IF NOT EXISTS idx_videos_status ON videos(status);
            CREATE INDEX IF NOT EXISTS idx_videos_uploader ON videos(uploader_handle);
            """)

    def upsert_user(self, handle: str, display_name: str = None):
        if not handle:
            return
        with DB_LOCK, self.conn:
            self.conn.execute("""
                INSERT INTO users(handle, display_name)
                VALUES(?, ?)
                ON CONFLICT(handle) DO UPDATE SET
                    display_name=COALESCE(excluded.display_name, users.display_name)
            """, (handle, display_name))

    def ensure_user_video_link(self, handle: str, video_id: str):
        if not handle or not video_id:
            return
        with DB_LOCK, self.conn:
            self.conn.execute("""
                INSERT OR IGNORE INTO user_videos(uploader_handle, video_id)
                VALUES(?, ?)
            """, (handle, video_id))

    def is_video_known(self, video_id: str) -> bool:
        cur = self.conn.cursor()
        cur.execute("SELECT 1 FROM videos WHERE video_id = ?", (video_id,))
        return cur.fetchone() is not None

    def mark_video_status(self, video_id: str, url: str, title: str,
                          uploader_handle: str, status: str,
                          file_path: str = None, caption_path: str = None):
        now = datetime.utcnow().isoformat(timespec="seconds")
        with DB_LOCK, self.conn:
            self.conn.execute("""
                INSERT INTO videos(video_id, url, title, uploader_handle, status, file_path, caption_path, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(video_id) DO UPDATE SET
                    url=excluded.url,
                    title=excluded.title,
                    uploader_handle=excluded.uploader_handle,
                    status=excluded.status,
                    file_path=COALESCE(excluded.file_path, videos.file_path),
                    caption_path=COALESCE(excluded.caption_path, videos.caption_path),
                    updated_at=excluded.updated_at
            """, (video_id, url, title, uploader_handle, status, file_path, caption_path, now, now))

    def close(self):
        try:
            self.conn.close()
        except:
            pass
