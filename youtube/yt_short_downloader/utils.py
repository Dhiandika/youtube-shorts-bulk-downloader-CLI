import os
import re, unicodedata

__all__ = [
    "get_existing_index",
    "sanitize_filename",
    "create_safe_filename",
    "validate_filename",
    "get_unique_filename",
    "normalize_upload_date",
    "parse_upload_date",
]

def _ascii_only(s: str) -> str:
    if not s:
        return "untitled"
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode("ascii", "ignore")
    s = re.sub(r'[<>:"/\\|?*]', '_', s)
    s = re.sub(r'[_\s]+', '_', s).strip('_ ')
    return s or "untitled"

def get_existing_index(output_path: str) -> int:
    files = os.listdir(output_path)
    indexes = [int(f.split(' - ')[0]) for f in files if f.split(' - ')[0].isdigit()]
    return max(indexes, default=0)



def sanitize_filename(title: str) -> str:
    s = _ascii_only(title)
    return s[:200]



def create_safe_filename(title: str, max_length: int = 100) -> str:
    return _ascii_only(title)[:max_length]


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


def normalize_upload_date(upload_date: str | None) -> str | None:
    """
    - 'YYYYMMDD' -> 'YYYY-MM-DD'
    - 'YYYY-MM-DD' -> tetap
    - selain itu -> None
    """
    if not upload_date:
        return None
    s = str(upload_date).strip()
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    # izinkan sudah yyyy-mm-dd
    try:
        from datetime import datetime
        datetime.strptime(s, "%Y-%m-%d")
        return s
    except Exception:
        return None


def parse_upload_date(upload_date: str | None):
    from datetime import datetime
    iso = normalize_upload_date(upload_date)
    if not iso:
        return None
    try:
        return datetime.strptime(iso, "%Y-%m-%d")
    except Exception:
        return None


