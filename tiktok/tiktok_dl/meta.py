import yt_dlp
import traceback

from .utils import is_tiktok_url
from .utils import normalize_input_to_url_list as normalize
# dipakai di cli
normalize_input_to_url_list = normalize

def extract_entries_from_source(src_url: str, max_videos=None, cookies_from_browser=None):
    """
    Listing cepat dengan extract_flat untuk profil/hashtag; non-flat untuk single video.
    """
    is_single = "/video/" in src_url
    ydl_opts = {
        "quiet": True,
        "extract_flat": False if is_single else "in_playlist",
        "playlistend": max_videos if max_videos else None,
    }
    if cookies_from_browser:
        ydl_opts["cookiesfrombrowser"] = (cookies_from_browser,)

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(src_url, download=False)
        entries, uploader = [], (info.get("uploader") or info.get("channel") or None)

        if "entries" in info:
            for e in info["entries"] or []:
                if not e:
                    continue
                url = e.get("webpage_url") or e.get("url")
                entries.append({
                    "id": e.get("id"),
                    "title": e.get("title") or e.get("description") or "Untitled",
                    "webpage_url": url,
                    "uploader": e.get("uploader") or uploader or "",
                })
        else:
            entries.append({
                "id": info.get("id"),
                "title": info.get("title") or info.get("description") or "Untitled",
                "webpage_url": info.get("webpage_url") or src_url,
                "uploader": info.get("uploader") or uploader or "",
            })

        # sort by upload_date jika ada
        entries = sorted(entries, key=lambda v: v.get("upload_date", "99999999"))
        return entries[:max_videos] if max_videos else entries, uploader

    except Exception as e:
        tb = traceback.format_exc()
        print(f"Gagal ambil daftar TikTok dari {src_url} : {e}")
        with open("download_errors.log", "a", encoding="utf-8") as log:
            log.write(f"Error fetch list: {src_url}\n{tb}\n")
        return [], None

def fetch_full_metadata(url: str, cookies_from_browser: str = None):
    """Ambil metadata lengkap untuk satu video TikTok (non-flat)."""
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
    }
    if cookies_from_browser:
        ydl_opts["cookiesfrombrowser"] = (cookies_from_browser,)

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        return info
    except Exception as e:
        with open("download_errors.log", "a", encoding="utf-8") as log:
            log.write(f"fetch_full_metadata fail for {url}: {e}\n")
        return None

def tiktok_caption_text(meta: dict) -> str:
    """
    Pakai 'description' (caption asli) agar tidak terpotong; fallback title/fulltitle.
    """
    body = (meta.get("description")
            or meta.get("title")
            or meta.get("fulltitle")
            or "")
    author = meta.get("uploader") or meta.get("channel") or ""
    url = meta.get("webpage_url") or ""
    vid = meta.get("id") or ""

    lines = [body.strip(), "", f"TikTok: {author}".strip(),
             f"URL: {url}".strip(), f"ID: {vid}".strip()]
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)
