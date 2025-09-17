from __future__ import annotations  # ← harus di paling atas



import threading
from typing import List, Dict, Optional
from .downloader import download_video
import os
from .utils import get_existing_index
from .db import TinyStore
from yt_short_downloader.downloader import download_videos
from yt_short_downloader.utils import get_existing_index
from yt_short_downloader.db import TinyStore

__all__ = ["download_videos_with_db"]

# Orkestrator: tidak mengubah fungsi `download_video`, hanya membungkusnya

def download_videos_with_db(
    video_entries: List[Dict],
    output_path: str,
    channel_name: str,
    quality: str,
    file_format: str,
    channel_key: str,
    store: TinyStore,
) -> None:
    os.makedirs(output_path, exist_ok=True)

    probe = get_existing_index(output_path)
    indices = store.reserve_indices(output_path, count=len(video_entries), fallback_probe=probe)

    # callback: tandai sukses di DB
    def _mark_ok(entry: Dict, _idx: int):
        vid = entry.get("id")
        if vid:
            store.mark_downloaded(channel_key, vid)

    download_videos(
        video_entries=video_entries,
        output_path=output_path,
        channel_name=channel_name,
        quality=quality,
        file_format=file_format,
        preassigned_indices=indices,
        on_success=_mark_ok,   # ⬅️ penting
    )


