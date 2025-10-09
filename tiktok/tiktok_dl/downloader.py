import os
import subprocess
import time
from urllib.parse import urlparse
from tqdm import tqdm

from .config import MAX_RETRIES, THREADS
from .utils import (
    sanitize_filename, validate_filename, get_unique_filename,
    get_existing_index, cleanup_partial_downloads
)
from .db import TikTokDB
from .meta import fetch_full_metadata, tiktok_caption_text

def _guess_handle_from_url(url: str):
    try:
        parts = urlparse(url).path.split("/")
        if len(parts) > 1 and parts[1].startswith("@"):
            return parts[1]  # @handle
    except:
        pass
    return None

def get_best_available_format_cli(quality_choice: str):
    if quality_choice == "best":
        return "bv*+ba/b"
    if quality_choice == "worst":
        return "worst"
    return quality_choice  # custom

def download_one_video(entry: dict, output_path: str, author_name: str,
                       quality: str, file_format: str, index: int,
                       cookies_from_browser: str, db: TikTokDB) -> bool:
    url = entry.get("webpage_url")
    title = entry.get("title") or "Untitled"
    uploader = author_name or entry.get("uploader") or "tiktok"

    handle_guess = _guess_handle_from_url(url)
    handle = handle_guess or (uploader if str(uploader).startswith("@") else None)

    # DB: user
    db.upsert_user(handle or uploader, display_name=uploader)

    # metadata penuh
    full = fetch_full_metadata(url, cookies_from_browser)
    if full:
        for key in ("description", "title", "fulltitle", "uploader", "channel", "id", "webpage_url"):
            if full.get(key):
                entry[key] = full.get(key)

    video_id = entry.get("id") or (full.get("id") if full else None) or ""
    if not video_id:
        video_id = f"unknown_{int(time.time())}"

    # anti duplikasi
    if db.is_video_known(video_id):
        return True

    db.mark_video_status(video_id, url, title, handle or uploader, "queued")
    db.ensure_user_video_link(handle or uploader, video_id)

    safe_title = sanitize_filename(entry.get("title") or "Untitled", 80)
    safe_uploader = sanitize_filename(uploader, 40)

    filename = f"{index:02d} - {safe_title} - {safe_uploader}.{file_format.lower()}"
    if not validate_filename(filename):
        filename = f"{index:02d} - video_{video_id}.{file_format.lower()}"
    filename = get_unique_filename(output_path, filename)
    filepath = os.path.join(output_path, filename)

    # caption
    caption_name = f"{os.path.splitext(filename)[0]}.txt"
    caption_path = os.path.join(output_path, caption_name)
    try:
        with open(caption_path, "w", encoding="utf-8") as f:
            f.write(tiktok_caption_text(entry))
    except Exception as e:
        caption_path = None
        with open("download_errors.log", "a", encoding="utf-8") as log:
            log.write(f"Caption fail for {url}: {e}\n")

    cleanup_partial_downloads(output_path, f"{index:02d} - {safe_title}")

    fmt = get_best_available_format_cli(quality)
    cmd = [
        "yt-dlp",
        "--merge-output-format", file_format.lower(),
        "--output", filepath,
        "--no-warnings",
        "--quiet",
        "--ignore-errors",
        "--no-check-certificates",
        "--no-playlist",
        "-f", fmt,
        url
    ]
    if cookies_from_browser:
        cmd[1:1] = ["--cookies-from-browser", cookies_from_browser]

    db.mark_video_status(video_id, url, entry.get("title") or title,
                         handle or uploader, "downloading", filepath, caption_path)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
                timeout=600,
                encoding="utf-8",
                errors="replace"
            )
            if not os.path.exists(filepath) or os.path.getsize(filepath) < 1000:
                raise Exception("File terlalu kecil / hilang (mungkin korup).")

            db.mark_video_status(video_id, url, entry.get("title") or title,
                                 handle or uploader, "success", filepath, caption_path)
            return True

        except subprocess.TimeoutExpired:
            with open("download_errors.log", "a", encoding="utf-8") as log:
                log.write(f"Timeout (attempt {attempt}) {url}\n")
            time.sleep(2 ** attempt)

        except subprocess.CalledProcessError as e:
            with open("download_errors.log", "a", encoding="utf-8") as log:
                log.write(
                    f"Attempt {attempt} gagal {url}\nCMD: {' '.join(cmd)}\n"
                    f"RC: {e.returncode}\nSTDOUT:\n{e.stdout}\nSTDERR:\n{e.stderr}\n"
                )
            if attempt == MAX_RETRIES:
                db.mark_video_status(video_id, url, entry.get("title") or title,
                                     handle or uploader, "failed",
                                     filepath if os.path.exists(filepath) else None,
                                     caption_path)
            time.sleep(2 ** attempt)
            if os.path.exists(filepath):
                try: os.remove(filepath)
                except Exception: pass

        except Exception as e:
            with open("download_errors.log", "a", encoding="utf-8") as log:
                log.write(f"Attempt {attempt} error umum {url}: {e}\n")
            if attempt == MAX_RETRIES:
                db.mark_video_status(video_id, url, entry.get("title") or title,
                                     handle or uploader, "failed",
                                     filepath if os.path.exists(filepath) else None,
                                     caption_path)
            time.sleep(2 ** attempt)

    return False

def download_entries(entries, output_path, author_name, quality, file_format,
                     cookies_from_browser, db: TikTokDB):
    os.makedirs(output_path, exist_ok=True)
    start_index = get_existing_index(output_path) + 1
    total = len(entries)

    from threading import Lock, Thread
    lock = Lock()
    idx = {"value": 0}
    success = {"count": 0}

    def worker(pbar: tqdm):
        while True:
            with lock:
                if idx["value"] >= total:
                    return
                i = idx["value"]
                idx["value"] += 1
            entry = entries[i]
            local_index = start_index + i
            ok = download_one_video(
                entry, output_path, author_name,
                quality, file_format, local_index, cookies_from_browser, db
            )
            if ok:
                with lock:
                    success["count"] += 1
            pbar.update(1)

    pbar = tqdm(total=total, desc="Downloading", unit="video")
    threads = []
    n_threads = min(THREADS, total if total > 0 else 1)
    for _ in range(n_threads):
        t = Thread(target=worker, args=(pbar,), daemon=True)
        t.start()
        threads.append(t)

    for t in threads:
        t.join()
    pbar.close()
    return success["count"]
