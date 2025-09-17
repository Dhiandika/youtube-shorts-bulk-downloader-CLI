from tinydb import TinyDB, Query
from threading import Lock
from datetime import datetime
from typing import Optional

class TinyStore:
    def __init__(self, path: str = 'data/db.json'):
        import os
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.db = TinyDB(path, ensure_ascii=False, indent=2)
        self._lock = Lock()
        # Tables
        self.t_channels = self.db.table('channels')
        self.t_videos = self.db.table('videos')

    # ---- helpers
    @staticmethod
    def _now_iso() -> str:
        return datetime.utcnow().isoformat() + 'Z'

    # ---- channels
    def upsert_channel(self, channel_key: str, name: Optional[str], url: str):
        with self._lock:
            Channel = Query()
            existing = self.t_channels.get(Channel.key == channel_key)
            doc = {
                'key': channel_key,
                'name': name,
                'url': url,
                'updated_at': self._now_iso(),
            }
            if existing:
                self.t_channels.update(doc, Channel.key == channel_key)
            else:
                doc['created_at'] = self._now_iso()
                self.t_channels.insert(doc)

    # ---- videos
    def upsert_video(self, channel_key: str, video_id: str, title: str, upload_date: Optional[str]):
        if not video_id:
            return
        with self._lock:
            Video = Query()
            existing = self.t_videos.get((Video.channel_key == channel_key) & (Video.video_id == video_id))
            payload = {
                'channel_key': channel_key,
                'video_id': video_id,
                'title': title,
                'upload_date': upload_date,
                'updated_at': self._now_iso(),
            }
            if existing:
                self.t_videos.update(payload, (Video.channel_key == channel_key) & (Video.video_id == video_id))
            else:
                payload.update({'downloaded': False, 'downloaded_at': None, 'created_at': self._now_iso()})
                self.t_videos.insert(payload)

    def mark_downloaded(self, channel_key: str, video_id: str):
        with self._lock:
            Video = Query()
            self.t_videos.update(
                {'downloaded': True, 'downloaded_at': self._now_iso()},
                (Video.channel_key == channel_key) & (Video.video_id == video_id)
            )

    def is_downloaded(self, channel_key: str, video_id: str) -> bool:
        Video = Query()
        doc = self.t_videos.get((Video.channel_key == channel_key) & (Video.video_id == video_id))
        return bool(doc and doc.get('downloaded'))