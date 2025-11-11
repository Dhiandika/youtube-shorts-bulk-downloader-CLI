# yt_short_downloader/orchestrator.py
from __future__ import annotations

import os
import importlib
from typing import List, Dict
from .db import TinyStore
from .utils import get_existing_index

__all__ = ["download_videos_with_db"]


def _load_download_videos():
    mod = importlib.import_module("yt_short_downloader.downloader")
    fn = getattr(mod, "download_videos", None)
    if fn is None:
        raise ImportError("download_videos not found in downloader module.")
    return fn


def _safe_reserve_indices(
    store: TinyStore,
    output_path: str,
    n_items: int,
    probe: int,
) -> List[int]:
    """
    Tahan-banting untuk berbagai versi TinyStore.reserve_indices:
      - reserve_indices(output_path, count, fallback_probe)
      - reserve_indices(count, output_path, fallback_probe)
      - reserve_indices(output_path, count)   (tanpa probe)
      - reserve_indices(count)                (tanpa path & probe)
    Jika semua gagal: fallback hitung manual dari folder.
    """
    # 1) coba (output_path, count, fallback_probe)
    try:
        return list(store.reserve_indices(output_path, n_items, probe))
    except TypeError:
        pass
    except AttributeError:
        pass

    # 2) coba (count, output_path, fallback_probe)
    try:
        return list(store.reserve_indices(n_items, output_path, probe))
    except TypeError:
        pass
    except AttributeError:
        pass

    # 3) coba (output_path, count)
    try:
        return list(store.reserve_indices(output_path, n_items))
    except TypeError:
        pass
    except AttributeError:
        pass

    # 4) coba (count)
    try:
        return list(store.reserve_indices(n_items))
    except Exception:
        pass

    # 5) FULL FALLBACK: hitung dari isi folder
    start = (get_existing_index(output_path) or 0) + 1
    return [start + i for i in range(n_items)]


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

    probe = get_existing_index(output_path)  # sekadar hint jika store butuh
    indices = _safe_reserve_indices(store, output_path, len(video_entries), probe)

    download_videos = _load_download_videos()

    def _mark_ok(entry: Dict, _idx: int) -> None:
        vid = entry.get("id")
        if vid:
            try:
                store.mark_downloaded(channel_key, vid)
            except Exception:
                # kalau API store berbeda, abaikan silently
                pass

    download_videos(
        video_entries=video_entries,
        output_path=output_path,
        channel_name=channel_name,
        quality=quality,
        file_format=file_format,
        preassigned_indices=indices,
        on_success=_mark_ok,
    )
