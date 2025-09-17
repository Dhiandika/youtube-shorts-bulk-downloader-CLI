import os
import re
from datetime import datetime, timedelta
from typing import Optional

__all__ = [
    "get_existing_index",
    "sanitize_filename",
    "create_safe_filename",
    "validate_filename",
    "get_unique_filename",
    # date helpers
    "normalize_upload_date",
    "parse_upload_date",
    "filter_by_age",
]


def get_existing_index(output_path: str) -> int:
    files = os.listdir(output_path)
    indexes = [int(f.split(' - ')[0]) for f in files if f.split(' - ')[0].isdigit()]
    return max(indexes, default=0)


def sanitize_filename(title: str) -> str:
    # Remove emoji dan karakter non-ASCII bermasalah
    title = re.sub(r'[^\x00-\x7F]+', '', title)
    # Ganti karakter yang bermasalah di filesystem
    title = re.sub(r'[<>:"/\\|?*]', '_', title)
    # Rapatkan underscore
    title = re.sub(r'_+', '_', title)
    # Trim
    title = title.strip(' _')
    # Batas panjang
    if len(title) > 200:
        title = title[:200]
    return title or "untitled"


def create_safe_filename(title: str, max_length: int = 100) -> str:
    # Hapus semua non-ASCII (termasuk emoji)
    safe_title = re.sub(r'[^\x20-\x7E]', '', title)
    safe_title = re.sub(r'[<>:"/\\|?*]', '_', safe_title)
    safe_title = re.sub(r'[\s_]+', '_', safe_title)
    safe_title = safe_title.strip('_')
    if len(safe_title) > max_length:
        safe_title = safe_title[:max_length]
    return safe_title or "untitled"


def validate_filename(filename: str) -> bool:
    if re.search(r'[<>:"/\\|?*\x00-\x1F\x7F-\x9F]', filename):
        return False
    if not filename.isascii():
        return False
    if len(filename) > 255:
        return False
    return True


def get_unique_filename(base_path: str, filename: str) -> str:
    candidate = os.path.join(base_path, filename)
    if not os.path.exists(candidate):
        return filename
    name, ext = os.path.splitext(filename)
    counter = 1
    while True:
        new_filename = f"{name}_{counter}{ext}"
        if not os.path.exists(os.path.join(base_path, new_filename)):
            return new_filename
        counter += 1


# ======== Date helpers ========

def normalize_upload_date(upload_date: Optional[str]) -> Optional[str]:
    """Terima format 'YYYYMMDD' atau 'YYYY-MM-DD' -> kembalikan 'YYYY-MM-DD' atau None."""
    if not upload_date:
        return None
    s = str(upload_date)
    if len(s) == 8 and s.isdigit():
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return s
    except Exception:
        return None


def parse_upload_date(upload_date: Optional[str]) -> Optional[datetime]:
    iso = normalize_upload_date(upload_date)
    if not iso:
        return None
    try:
        return datetime.strptime(iso, "%Y-%m-%d")
    except Exception:
        return None


def filter_by_age(entries: list[dict], days: int) -> list[dict]:
    """
    Saring entries berdasarkan "days" terakhir (UTC).
    Entry tanpa upload_date dibiarkan lolos; enrichment opsional di caller.
    """
    cutoff = datetime.utcnow() - timedelta(days=days)
    kept: list[dict] = []
    for e in entries:
        dt = parse_upload_date(e.get('upload_date'))
        if dt is None or dt >= cutoff:
            kept.append(e)
    return kept
