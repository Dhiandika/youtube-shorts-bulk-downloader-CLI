import threading
from typing import List, Dict
from .downloader import download_video

# Orkestrator: tidak mengubah fungsi `download_video`, hanya membungkusnya

def _wrap_download(entry: Dict, output_path: str, channel_name: str, quality: str, file_format: str,
                   index: int, channel_key: str, store) -> None:
    ok = download_video(
        entry['id'], entry.get('title', 'Unknown Title'), output_path,
        channel_name, quality, file_format, index
    )
    if ok:
        store.mark_downloaded(channel_key, entry['id'])


def download_videos_with_db(video_entries: List[Dict], output_path: str, channel_name: str,
                            quality: str, file_format: str, channel_key: str, store) -> None:
    threads: list[threading.Thread] = []
    # Penomoran urut sederhana; index tidak mengambil existing index dari folder.
    for i, entry in enumerate(video_entries, start=1):
        t = threading.Thread(
            target=_wrap_download,
            args=(entry, output_path, channel_name, quality, file_format, i, channel_key, store)
        )
        t.start()
        threads.append(t)
    for t in threads:
        t.join()