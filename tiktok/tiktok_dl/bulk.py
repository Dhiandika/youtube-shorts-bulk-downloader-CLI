# -*- coding: utf-8 -*-
from __future__ import annotations
import os
from typing import List, Dict, Iterable, Tuple, Optional

from .meta import extract_entries_from_source, fetch_full_metadata
from .utils import normalize_input_to_url_list
from .filters import extract_hashtags, contains_required_hashtags
from .db import TikTokDB

def read_sources_from_file(path: str) -> List[str]:
    """
    Baca file .txt yang berisi daftar profil/handle/URL TikTok.
    - Abaikan baris kosong dan baris yang diawali '#'
    - Mendukung: URL profil (https://www.tiktok.com/@user), handle (@user),
                 atau URL video (walau disarankan profil)
    """
    sources = []
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            # normalize (list) tapi ambil elemen pertama karena 1 input → 1 sumber
            normed = normalize_input_to_url_list(line)
            if normed:
                sources.append(normed[0])
    return sources

def collect_entries_for_users(
    sources: List[str],
    max_per_user: Optional[int] = None,
    cookies_from_browser: Optional[str] = None
) -> Tuple[List[Dict], Dict[str, int]]:
    """
    Untuk tiap sumber (profil), ambil daftar video (entries).
    Return:
      - all_entries: list of entry dict {id, title, webpage_url, uploader}
      - per_user_count: mapping uploader → jumlah video yang ditemukan (setelah batas max_per_user)
    """
    all_entries: List[Dict] = []
    per_user_count: Dict[str, int] = {}

    for src in sources:
        entries, uploader = extract_entries_from_source(
            src, max_videos=max_per_user, cookies_from_browser=cookies_from_browser
        )
        if not entries:
            continue
        # uploader bisa None jika extractor tidak memberikan
        # tetap lanjut, uploader di tiap entry mungkin ada
        all_entries.extend(entries)
        key = uploader or (entries[0].get("uploader") or "unknown")
        per_user_count[key] = per_user_count.get(key, 0) + len(entries)

    return all_entries, per_user_count

def _hashtag_ok_for_entry(
    entry: Dict,
    required_tags: Iterable[str],
    mode: str,
    cookies_from_browser: Optional[str] = None
) -> Tuple[bool, Dict]:
    """
    Ambil metadata penuh (non-flat) untuk memastikan description/caption,
    lalu cek hashtag sesuai rule. Mengembalikan (ok, merged_meta).
    """
    url = entry.get("webpage_url")
    full = fetch_full_metadata(url, cookies_from_browser=cookies_from_browser) or {}
    # merge penting ke entry agar downstream dapat caption lengkap
    merged = dict(entry)
    for k in ("description", "title", "fulltitle", "uploader", "channel", "id", "webpage_url"):
        if full.get(k):
            merged[k] = full.get(k)

    caption = merged.get("description") or merged.get("title") or ""
    found = extract_hashtags(caption)
    ok = contains_required_hashtags(found, required_tags, mode=mode)
    return ok, merged

def prefilter_by_hashtags(
    entries: List[Dict],
    required_tags: Iterable[str],
    mode: str = "all",
    cookies_from_browser: Optional[str] = None,
    db: Optional[TikTokDB] = None,
    mark_skipped: bool = False
) -> List[Dict]:
    """
    Prefilter daftar entries dengan memeriksa caption/description menggunakan hash-tag rule.
    - Jika db & mark_skipped=True, video yang tidak lolos ditandai di DB (status='skipped_hashtag').
    - Entry yang lolos akan berisi field 'description' dari metadata penuh.
    """
    required = [t.strip() for t in required_tags if t and t.strip()]
    if not required:
        return entries  # tidak ada rule → lewati

    kept: List[Dict] = []
    for e in entries:
        ok, merged = _hashtag_ok_for_entry(e, required, mode, cookies_from_browser)
        vid = merged.get("id")
        if ok:
            kept.append(merged)
        else:
            if db and mark_skipped and vid:
                # tandai di DB agar historinya terekam
                db.mark_video_status(
                    video_id=vid,
                    url=merged.get("webpage_url") or "",
                    title=merged.get("title") or "",
                    uploader_handle=(merged.get("uploader") or ""),
                    status="skipped_hashtag",
                    file_path=None,
                    caption_path=None
                )
    return kept

def drop_known_videos(entries: List[Dict], db: TikTokDB) -> Tuple[List[Dict], int]:
    """
    Buang video yang sudah pernah tercatat (UNIQUE video_id) di DB.
    Return (filtered_entries, dupes_skipped)
    """
    out = []
    dupes = 0
    for e in entries:
        vid = e.get("id")
        if vid and db.is_video_known(vid):
            dupes += 1
            continue
        out.append(e)
    return out, dupes
