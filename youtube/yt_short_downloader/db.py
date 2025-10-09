from __future__ import annotations
import os
import json
from datetime import datetime
from typing import Optional

from tinydb import TinyDB, Query
from tinydb.storages import JSONStorage

DB_PATH = os.path.join(os.getcwd(), "data/ytshorts_db.json")


class Utf8JSONStorage(JSONStorage):
    def __init__(self, path, create_dirs=False, encoding="utf-8", **kwargs):
        kwargs.setdefault("ensure_ascii", False)
        super().__init__(path, create_dirs=create_dirs, encoding=encoding, **kwargs)


class TinyStore:
    def __init__(self, path: Optional[str] = None):
        self.path = path or DB_PATH
        self.db = TinyDB(self.path, storage=Utf8JSONStorage)
        self.channels = self.db.table("channels")
        self.videos = self.db.table("videos")
        self.counters = self.db.table("counters")

    # ---------- channel ----------
    def upsert_channel(self, channel_key: str, name: str, url: str) -> None:
        Channel = Query()
        now = datetime.utcnow().isoformat() + "Z"
        existing = self.channels.get(Channel.key == channel_key)
        if existing:
            self.channels.update({"name": name, "url": url, "updated_at": now}, Channel.key == channel_key)
        else:
            self.channels.insert({"key": channel_key, "name": name, "url": url, "created_at": now, "updated_at": now})

    # ---------- video ----------
    def upsert_video(self, channel_key: str, video_id: str, title: str, upload_date: Optional[str]) -> None:
        Video = Query()
        now = datetime.utcnow().isoformat() + "Z"
        key = f"{channel_key}::{video_id}"
        payload = {
            "key": key,
            "channel_key": channel_key,
            "video_id": video_id,
            "title": title,
            "upload_date": upload_date,
            "updated_at": now,
        }
        if self.videos.get(Video.key == key):
            self.videos.update(payload, Video.key == key)
        else:
            payload.update({"created_at": now, "downloaded": False, "downloaded_at": None})
            self.videos.insert(payload)

    def mark_downloaded(self, channel_key: str, video_id: str) -> None:
        Video = Query()
        key = f"{channel_key}::{video_id}"
        now = datetime.utcnow().isoformat() + "Z"
        self.videos.update({"downloaded": True, "downloaded_at": now, "updated_at": now}, Video.key == key)

    def is_downloaded(self, channel_key: str, video_id: str) -> bool:
        Video = Query()
        key = f"{channel_key}::{video_id}"
        doc = self.videos.get(Video.key == key)
        return bool(doc and doc.get("downloaded"))

    # ---------- folder counters ----------
    def _folder_key(self, folder_path: str) -> str:
        return f"folder::{os.path.abspath(folder_path)}"

    def get_last_index(self, folder_path: str) -> int:
        C = Query()
        key = self._folder_key(folder_path)
        doc = self.counters.get(C.key == key)
        return int(doc.get("last_index", 0)) if doc else 0

    def set_last_index(self, folder_path: str, last_index: int) -> None:
        C = Query()
        key = self._folder_key(folder_path)
        now = datetime.utcnow().isoformat() + "Z"
        payload = {"key": key, "last_index": int(last_index), "updated_at": now}
        if self.counters.get(C.key == key):
            self.counters.update(payload, C.key == key)
        else:
            self.counters.insert(payload)

    def reserve_indices(self, folder_path: str, count: int, fallback_probe: int = 0) -> list[int]:
        """
        Pre-allocate 'count' indices secara atomik sederhana:
        - Ambil last_index dari DB
        - Ambil juga probe dari isi folder (opsional) untuk sinkron ulang jika ada file tambahan
        - Pakai maksimum dari keduanya
        - Simpan kembali last_index baru
        """
        base = max(self.get_last_index(folder_path), int(fallback_probe))
        start = base + 1
        end = base + count
        self.set_last_index(folder_path, end)
        return list(range(start, end + 1))
