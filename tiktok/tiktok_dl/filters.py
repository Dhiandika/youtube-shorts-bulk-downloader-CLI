# -*- coding: utf-8 -*-
import os
import re
import subprocess
from typing import Iterable, List, Dict, Optional, Tuple

from .db import TikTokDB

HASHTAG_RE = re.compile(r"(#|＃)([0-9A-Za-z_]+)", re.UNICODE)

def _ffprobe_exists() -> bool:
    try:
        subprocess.run(["ffprobe", "-version"],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
        return True
    except Exception:
        return False

def get_video_duration_seconds(filepath: str) -> Optional[int]:
    """
    Ambil durasi (detik) dari file video lokal via ffprobe.
    Return None jika gagal/ffprobe tidak ada.
    """
    if not os.path.exists(filepath):
        return None
    if not _ffprobe_exists():
        return None
    try:
        # Ambil durasi format secara langsung (lebih stabil lintas container)
        cmd = [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", filepath
        ]
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           text=True, timeout=30)
        if r.returncode != 0:
            return None
        val = r.stdout.strip()
        if not val:
            return None
        sec = float(val)
        return int(round(sec))
    except Exception:
        return None

def read_caption(path: Optional[str]) -> str:
    if not path or not os.path.exists(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""

def extract_hashtags(text: str) -> List[str]:
    """
    Ambil hashtag dalam caption (.txt). Mendukung '#' dan '＃' (fullwidth).
    Normalisasi ke lowercase tanpa tanda '#'.
    """
    tags = []
    if not text:
        return tags
    text = text.replace("＃", "#")
    for m in HASHTAG_RE.finditer(text):
        tag = m.group(2).lower()
        if tag:
            tags.append(tag)
    return tags

def contains_required_hashtags(hashtags_found: Iterable[str],
                               required: Iterable[str],
                               mode: str = "all") -> bool:
    """
    mode = "all": semua required harus ada
    mode = "any": minimal salah satu ada
    """
    required_norm = [t.lstrip("#").lower() for t in required if t]
    found_set = set([t.lstrip("#").lower() for t in hashtags_found])
    if not required_norm:
        return True
    if mode == "any":
        return any(t in found_set for t in required_norm)
    # default: all
    return all(t in found_set for t in required_norm)

def list_success_videos(db: TikTokDB) -> List[Dict]:
    """
    Ambil daftar video berstatus 'success' beserta path.
    Return: list of dict {video_id, title, url, uploader_handle, file_path, caption_path}
    """
    cur = db.conn.cursor()
    cur.execute("""
        SELECT video_id, title, url, uploader_handle, file_path, caption_path, status
        FROM videos
        WHERE status = 'success'
    """)
    rows = cur.fetchall()
    out = []
    for r in rows:
        out.append({
            "video_id": r[0],
            "title": r[1],
            "url": r[2],
            "uploader_handle": r[3],
            "file_path": r[4],
            "caption_path": r[5],
            "status": r[6],
        })
    return out

def sort_by_duration(db: TikTokDB, order: str = "asc", limit: Optional[int] = None) -> List[Tuple[Dict, Optional[int]]]:
    """
    Hitung durasi tiap video sukses, lalu urutkan.
    Return list[(record, duration_seconds)]
    """
    recs = list_success_videos(db)
    enriched = []
    for r in recs:
        dur = get_video_duration_seconds(r["file_path"]) if r["file_path"] else None
        enriched.append((r, dur))

    # None durasi ditempatkan di akhir agar tidak ganggu urutan
    enriched.sort(key=lambda x: (x[1] is None, x[1] if x[1] is not None else 0),
                  reverse=(order.lower() == "desc"))
    if limit:
        enriched = enriched[:limit]
    return enriched

def filter_videos(db: TikTokDB,
                  min_duration: Optional[int] = None,
                  max_duration: Optional[int] = None,
                  required_hashtags: Optional[Iterable[str]] = None,
                  hashtag_mode: str = "all",
                  delete_if_fail: bool = False) -> Dict[str, int]:
    """
    Terapkan filter:
      - durasi (detik): harus di dalam [min_duration, max_duration] jika diberikan
      - hashtag: harus memenuhi 'required_hashtags' sesuai 'hashtag_mode'
    Jika delete_if_fail=True → hapus file (video & caption) dan update status='deleted' pada DB
    Return summary dict.
    """
    req_tags = list(required_hashtags or [])
    stats = {"checked": 0, "kept": 0, "deleted": 0, "failed_info": 0}

    for r in list_success_videos(db):
        stats["checked"] += 1

        # 1) cek durasi
        ok_duration = True
        dur = None
        if min_duration is not None or max_duration is not None:
            dur = get_video_duration_seconds(r["file_path"]) if r["file_path"] else None
            if dur is None:
                ok_duration = False  # tidak bisa ambil durasi → anggap gagal kriteria
            else:
                if min_duration is not None and dur < min_duration:
                    ok_duration = False
                if max_duration is not None and dur > max_duration:
                    ok_duration = False

        # 2) cek hashtag
        ok_hashtag = True
        if req_tags:
            cap = read_caption(r["caption_path"])
            found = extract_hashtags(cap)
            ok_hashtag = contains_required_hashtags(found, req_tags, mode=hashtag_mode)

        keep = ok_duration and ok_hashtag

        if keep:
            stats["kept"] += 1
            continue

        # tidak memenuhi kriteria
        if delete_if_fail:
            # hapus file fisik
            fp = r["file_path"]
            cp = r["caption_path"]
            if fp and os.path.exists(fp):
                try:
                    os.remove(fp)
                except Exception:
                    pass
            if cp and os.path.exists(cp):
                try:
                    os.remove(cp)
                except Exception:
                    pass
            # update DB → status deleted, kosongkan path
            db.mark_video_status(
                video_id=r["video_id"],
                url=r["url"],
                title=r["title"] or "",
                uploader_handle=r["uploader_handle"] or "",
                status="deleted",
                file_path=None,
                caption_path=None
            )
            stats["deleted"] += 1
        else:
            stats["failed_info"] += 1  # ditandai gagal kriteria (tidak dihapus)

    return stats
