#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
bulk_from_file.py
Unduh video TikTok dari daftar user/URL di users.txt.

Alur per user:
  1. Listing video via yt-dlp (flat-playlist)
  2. Prefilter hashtag (opsional)
  3. Anti-dupe via DB
  4. Download + tulis sidecar .txt
"""

import os
import sys
import json
import time
import signal
import subprocess
from datetime import datetime
from typing import List, Dict, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import re

import yt_dlp

from tiktok_dl.config import DEFAULT_DB, DEFAULT_OUTDIR
from tiktok_dl.utils import check_yt_dlp_installation, normalize_input_to_url_list
from tiktok_dl.db import TikTokDB
from tiktok_dl.filters import extract_hashtags, contains_required_hashtags

class _SilentLogger:
    """Buang semua output dari yt-dlp Python API (termasuk ERROR)."""
    def debug(self, msg): pass
    def info(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass

# ═══════════════════════════════════════════════════════════════
#  ⚙️  KONFIGURASI
# ═══════════════════════════════════════════════════════════════

INPUT_FILE   = "users.txt"    # 1 user/URL per baris
DB_PATH      = DEFAULT_DB
OUTDIR       = DEFAULT_OUTDIR
MAX_PER_USER = None           # None = semua video; angka = batasi per user

# --- Cookie ---
# Default None = tidak perlu cookie (yt-dlp Python API biasanya bisa tanpa cookie)
# Jika dibutuhkan: isi COOKIES_FILE dengan path ke cookies.txt export dari browser
COOKIES_FILE         = None   # "cookies.txt" | None
COOKIES_FROM_BROWSER = None   # "chrome" | "firefox" | "edge" | None

# --- Filter hashtag ---
# Kosongkan list untuk skip filter (unduh semua video)
REQUIRED_TAGS = [
    "#movie", "#chineseshort", "#film", "#drama",
    "#shorts", "#anime", "#edit", "#movieedit",
    "#movieclips", "#clips", "#fyp", "#cartoon", "#tiktok",
]
TAG_MODE           = "any"   # "any" | "all"
MARK_SKIPPED_IN_DB = True

# --- Metadata prefilter ---
METADATA_WORKERS     = 8
META_TOTAL_TIMEOUT_S = 30
META_SOCKET_TIMEOUT  = 15
META_RETRIES         = 2
META_BATCH_SIZE      = 32
META_SLEEP_BETWEEN   = 1.0

# --- Download ---
QUALITY                  = "best"
FORMAT                   = "mp4"
DOWNLOAD_TOTAL_TIMEOUT_S = 180
DOWNLOAD_RETRIES         = 3
CONCURRENT_DOWNLOADS     = 3

# --- Listing ---
LIST_TIMEOUT_S = 60

# --- Backoff ---
BACKOFF_BASE_S   = 2.0
BACKOFF_MAX_S    = 60.0
BACKOFF_FACTOR   = 2.0
BACKOFF_JITTER_S = 0.8

# --- HTTP ---
FORCE_IPV4   = True
HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.tiktok.com/",
    "Accept-Language": "en-US,en;q=0.9",
}

# ═══════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════

def _safe_basename(s: str) -> str:
    for ch in '<>:"/\\|?*\n\r\t':
        s = s.replace(ch, "_")
    return s.strip()

def _write_errlog(msg: str):
    try:
        with open("download_errors.log", "a", encoding="utf-8") as f:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass

def _backoff_sleep(attempt: int, context: str):
    import random
    delay = min(
        BACKOFF_BASE_S * (BACKOFF_FACTOR ** attempt) + random.random() * BACKOFF_JITTER_S,
        BACKOFF_MAX_S
    )
    print(f"[INFO] Backoff ({context}): tunggu {delay:.1f}s ...")
    time.sleep(delay)

def _is_rate_limited(stderr: str) -> bool:
    s = (stderr or "").lower()
    return any(x in s for x in ("http error 429", "too many requests", "verify you're human", "forbidden", "http error 403"))

def _is_network_unstable(stderr: str) -> bool:
    s = (stderr or "").lower()
    return any(x in s for x in ("timed out", "timeout", "connection reset", "network is unreachable"))

def _is_cookie_error(stderr: str) -> bool:
    s = (stderr or "").lower()
    return "could not copy" in s and "cookie" in s

def _normalize_tags(tags: List[str]) -> List[str]:
    seen, res = set(), []
    for t in (tags or []):
        t = (t or "").strip()
        if not t:
            continue
        if not t.startswith("#"):
            t = f"#{t}"
        if t not in seen:
            seen.add(t)
            res.append(t)
    return res

def _resolve_cookie_args(cookies_file: Optional[str], cookies_from_browser: Optional[str]) -> List[str]:
    """
    Resolve argumen cookie untuk yt-dlp.
    Prioritas: file cookies.txt > browser > tidak ada.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))

    if cookies_file:
        path = cookies_file if os.path.isabs(cookies_file) else os.path.join(script_dir, cookies_file)
        if os.path.exists(path):
            return ["--cookies", path]

    if cookies_from_browser:
        return ["--cookies-from-browser", cookies_from_browser]

    return []

def read_sources_from_file(path: str) -> List[str]:
    sources = []
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            normed = normalize_input_to_url_list(line)
            if normed:
                sources.append(normed[0])
    return sources

def detect_existing_max_seq(outdir: str) -> int:
    if not os.path.isdir(outdir):
        return 0
    pattern = re.compile(r"^(\d{4})\s+-\s+")
    max_seq = 0
    try:
        for name in os.listdir(outdir):
            m = pattern.match(name)
            if m:
                try:
                    max_seq = max(max_seq, int(m.group(1)))
                except ValueError:
                    pass
    except Exception as e:
        _write_errlog(f"DETECT_SEQ_FAIL: {e}")
    return max_seq

# ═══════════════════════════════════════════════════════════════
#  LISTING
# ═══════════════════════════════════════════════════════════════

def _build_list_cmd(src_url: str, cookie_args: List[str]) -> List[str]:
    cmd = [
        "yt-dlp", "-J", "--flat-playlist",
        "--no-warnings", "--no-check-certificates",
        "--user-agent", HTTP_HEADERS["User-Agent"],
        "--referer", HTTP_HEADERS["Referer"],
        "--add-header", f"Accept-Language: {HTTP_HEADERS['Accept-Language']}",
    ]
    if FORCE_IPV4:
        cmd.append("--force-ipv4")
    cmd.extend(cookie_args)
    cmd.append(src_url)
    return cmd

def _parse_listing_output(stdout: str, uploader_fallback: str, max_items: Optional[int]) -> Tuple[List[Dict], str]:
    data = json.loads(stdout)
    uploader = data.get("uploader") or data.get("channel") or uploader_fallback
    entries = []
    for e in (data.get("entries") or []):
        url = e.get("webpage_url") or e.get("url")
        entries.append({
            "id":           e.get("id"),
            "title":        e.get("title") or e.get("description") or "Untitled",
            "webpage_url":  url,
            "uploader":     e.get("uploader") or uploader or "",
            "upload_date":  e.get("upload_date"),
            "description":  e.get("description"),
        })
        if max_items and len(entries) >= max_items:
            break
    entries.sort(key=lambda v: v.get("upload_date") or "99999999")
    return entries, uploader

def list_entries(src_url: str, timeout_s: int, max_items: Optional[int]) -> Tuple[List[Dict], Optional[str]]:
    """
    Listing via yt-dlp Python API (sama dengan meta.py di cli.py — bisa tanpa cookie).
    """
    ydl_opts: dict = {
        "quiet":        True,
        "logger":       _SilentLogger(),
        "ignoreerrors": True,
        "extract_flat": "in_playlist",
        "playlistend":  max_items if max_items else None,
    }
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if COOKIES_FILE:
        path = COOKIES_FILE if os.path.isabs(COOKIES_FILE) else os.path.join(script_dir, COOKIES_FILE)
        if os.path.exists(path):
            ydl_opts["cookiefile"] = path
    elif COOKIES_FROM_BROWSER:
        ydl_opts["cookiesfrombrowser"] = (COOKIES_FROM_BROWSER,)

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(src_url, download=False)
    except Exception as e:
        print(f"[WARN] Listing gagal: {str(e)[:200]}")
        return [], None

    if not info:
        return [], None

    uploader = info.get("uploader") or info.get("channel") or None
    entries  = []

    for e in (info.get("entries") or []):
        if not e:
            continue
        url = e.get("webpage_url") or e.get("url")
        entries.append({
            "id":          e.get("id"),
            "title":       e.get("title") or e.get("description") or "Untitled",
            "webpage_url": url,
            "uploader":    e.get("uploader") or uploader or "",
            "upload_date": e.get("upload_date"),
            "description": e.get("description"),
        })
        if max_items and len(entries) >= max_items:
            break

    entries.sort(key=lambda v: v.get("upload_date") or "99999999")
    return entries, uploader


# ═══════════════════════════════════════════════════════════════
#  METADATA FETCH (untuk prefilter hashtag)
# ═══════════════════════════════════════════════════════════════

def fetch_metadata_cli(url: str) -> Optional[Dict]:
    """
    Fetch metadata via subprocess (isolated — tidak bisa crash main process).
    Subprocess yt-dlp dijalankan per video, aman untuk parallel workers.
    """
    cmd = [
        "yt-dlp", "-J",
        "--no-check-certificates",
        "--socket-timeout", str(META_SOCKET_TIMEOUT),
        "--extractor-retries", str(META_RETRIES),
        "--no-warnings",
        "--quiet",
    ]
    if FORCE_IPV4:
        cmd.append("--force-ipv4")
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if COOKIES_FILE:
        path = COOKIES_FILE if os.path.isabs(COOKIES_FILE) else os.path.join(script_dir, COOKIES_FILE)
        if os.path.exists(path):
            cmd.extend(["--cookies", path])
    elif COOKIES_FROM_BROWSER:
        cmd.extend(["--cookies-from-browser", COOKIES_FROM_BROWSER])
    cmd.append(url)

    for attempt in range(2):
        try:
            r = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,  # buang semua error output
                text=True,
                timeout=META_TOTAL_TIMEOUT_S,
                encoding="utf-8",
                errors="replace",
            )
            if r.returncode == 0 and r.stdout.strip():
                return json.loads(r.stdout)
        except subprocess.TimeoutExpired:
            if attempt < 1:
                continue
        except BaseException:
            pass
    return None

# ═══════════════════════════════════════════════════════════════
#  PREFILTER HASHTAG
# ═══════════════════════════════════════════════════════════════

def prefilter_by_hashtag(entries: List[Dict], required_tags: List[str],
                          mode: str, db: TikTokDB, mark_skipped: bool) -> List[Dict]:
    required = _normalize_tags(required_tags)
    if not required:
        return entries

    total = len(entries)
    print(f"\nPrefilter hashtag [{mode.upper()}] untuk {total} video (workers={METADATA_WORKERS}) ...")

    def check(e):
        url  = e.get("webpage_url")
        meta = fetch_metadata_cli(url)
        merged = dict(e)
        if meta:
            for k in ("description", "title", "fulltitle", "uploader", "channel", "id", "webpage_url"):
                if meta.get(k):
                    merged[k] = meta[k]
        caption = merged.get("description") or merged.get("title") or ""
        found   = extract_hashtags(caption)
        ok      = contains_required_hashtags(found, required, mode=mode)
        return ok, merged

    kept = []
    done = 0
    for start in range(0, total, META_BATCH_SIZE):
        batch = entries[start:start + META_BATCH_SIZE]
        with ThreadPoolExecutor(max_workers=METADATA_WORKERS) as ex:
            futures = [ex.submit(check, e) for e in batch]
            for fut in as_completed(futures):
                try:
                    ok, merged = fut.result()
                except BaseException:
                    ok, merged = False, {}
                if ok:
                    kept.append(merged)
                elif mark_skipped and merged.get("id"):
                    try:
                        db.mark_video_status(
                            video_id=merged["id"], url=merged.get("webpage_url") or "",
                            title=merged.get("title") or "", uploader_handle="",
                            status="skipped_hashtag", file_path=None, caption_path=None
                        )
                    except Exception:
                        pass
                done += 1
                if done % 25 == 0 or done == total:
                    print(f"  prefilter: {done}/{total} (lolos: {len(kept)})")
        if META_SLEEP_BETWEEN and (start + META_BATCH_SIZE) < total:
            time.sleep(META_SLEEP_BETWEEN)

    print(f"Video lolos hashtag: {len(kept)}/{total}")
    return kept

# ═══════════════════════════════════════════════════════════════
#  ANTI-DUPE
# ═══════════════════════════════════════════════════════════════

def drop_known_videos(entries: List[Dict], db: TikTokDB) -> Tuple[List[Dict], int]:
    out, dupes = [], 0
    for e in entries:
        if e.get("id") and db.is_video_known(e["id"]):
            dupes += 1
        else:
            out.append(e)
    return out, dupes

# ═══════════════════════════════════════════════════════════════
#  DOWNLOAD
# ═══════════════════════════════════════════════════════════════

def _write_sidecar_txt(txt_path: str, url: str, vid: Optional[str],
                        title: Optional[str], caption: Optional[str]):
    content = "\n".join([
        f"URL: {url or ''}",
        f"ID: {vid or ''}",
        f"Title: {title or ''}",
        "",
        "Caption:",
        caption or "",
    ])
    os.makedirs(os.path.dirname(txt_path), exist_ok=True)
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(content)

def _download_fallback_gallerydl(url: str, vid: str, title: str,
                                  caption: Optional[str], seq: int,
                                  db: TikTokDB) -> bool:
    """
    Fallback download via gallery-dl jika yt-dlp gagal.
    gallery-dl support TikTok secara native dan independen dari yt-dlp.
    """
    safe_title = _safe_basename(title or "Untitled")
    # gallery-dl simpan ke subfolder sesuai struktur URL, jadi kita pakai tmpdir dulu
    import tempfile, glob as _glob
    tmp_dir = tempfile.mkdtemp(prefix="gdl_tiktok_")

    cmd = [
        "gallery-dl",
        "--dest", tmp_dir,
        "--no-mtime",
        "-q",
        url,
    ]
    try:
        r = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=DOWNLOAD_TOTAL_TIMEOUT_S,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        _write_errlog(f"GALLERY_DL_NOT_FOUND: install dengan 'pip install gallery-dl'")
        return False
    except subprocess.TimeoutExpired:
        _write_errlog(f"GALLERY_DL_TIMEOUT {vid} {url}")
        return False
    except Exception as e:
        _write_errlog(f"GALLERY_DL_EXC {vid}: {e}")
        return False

    # Cari file video di tmp_dir (recursive)
    found_files = []
    for ext in ("*.mp4", "*.webm", "*.mkv", "*.mov"):
        found_files.extend(_glob.glob(os.path.join(tmp_dir, "**", ext), recursive=True))

    if not found_files:
        _write_errlog(f"GALLERY_DL_NO_FILE {vid} rc={r.returncode} {r.stderr[:200]}")
        return False

    src = found_files[0]
    _, ext = os.path.splitext(src)
    out_name = f"{seq:04d} - {safe_title} [{vid}]{ext}"
    os.makedirs(OUTDIR, exist_ok=True)
    final_path = os.path.join(OUTDIR, out_name)

    try:
        import shutil
        shutil.move(src, final_path)
    except Exception as e:
        _write_errlog(f"GALLERY_DL_MOVE_FAIL {vid}: {e}")
        return False

    # Tulis sidecar .txt
    txt_path = os.path.join(OUTDIR, f"{seq:04d} - {safe_title} [{vid}].txt")
    try:
        _write_sidecar_txt(txt_path, url, vid, title, caption or "")
    except Exception as ce:
        _write_errlog(f"GALLERY_DL_CAPTION_FAIL {vid}: {ce}")

    try:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    except Exception:
        pass

    try:
        db.mark_video_status(
            video_id=vid, url=url, title=title or "Untitled",
            uploader_handle="", status="success",
            file_path=final_path, caption_path=txt_path
        )
    except Exception:
        pass

    return True


def _download_one(url: str, vid: str, title: str, caption: Optional[str],
                  seq: int, db: TikTokDB) -> bool:
    safe_title = _safe_basename(title or "Untitled")
    out_tpl    = os.path.join(OUTDIR, f"{seq:04d} - {safe_title} [{vid}].%(ext)s")
    cookie_args = _resolve_cookie_args(COOKIES_FILE, COOKIES_FROM_BROWSER)

    cmd = [
        "yt-dlp",
        "--no-check-certificates", "--no-playlist", "--no-warnings",
        "--retries", str(DOWNLOAD_RETRIES),
        "--fragment-retries", str(DOWNLOAD_RETRIES),
        "--socket-timeout", str(META_SOCKET_TIMEOUT),
        "--extractor-retries", str(META_RETRIES),
        "--user-agent", HTTP_HEADERS["User-Agent"],
        "--referer", HTTP_HEADERS["Referer"],
        "--add-header", f"Accept-Language: {HTTP_HEADERS['Accept-Language']}",
        "-f", QUALITY,
        "--merge-output-format", FORMAT,
        "-o", out_tpl,
        "--print", "after_move:filepath",
    ]
    if FORCE_IPV4:
        cmd.append("--force-ipv4")
    cmd.extend(cookie_args)
    cmd.append(url)

    if vid:
        try:
            db.mark_video_status(
                video_id=vid, url=url, title=title or "Untitled",
                uploader_handle="", status="downloading", file_path=None, caption_path=None
            )
        except Exception:
            pass

    ytdlp_ok = False
    for attempt in range(DOWNLOAD_RETRIES + 1):
        try:
            r = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, timeout=DOWNLOAD_TOTAL_TIMEOUT_S, encoding="utf-8", errors="replace"
            )
            if r.returncode == 0:
                lines     = [ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip()]
                final     = lines[-1] if lines else ""
                txt_path  = (os.path.splitext(final)[0] + ".txt") if final \
                            else os.path.join(OUTDIR, f"{seq:04d} - {safe_title} [{vid}].txt")
                try:
                    _write_sidecar_txt(txt_path, url, vid, title, caption or "")
                except Exception as ce:
                    _write_errlog(f"CAPTION_WRITE_FAIL {vid}: {ce}")

                try:
                    db.mark_video_status(
                        video_id=vid, url=url, title=title or "Untitled",
                        uploader_handle="", status="success",
                        file_path=None, caption_path=txt_path
                    )
                except Exception:
                    pass
                return True

            err = r.stderr or ""
            if _is_rate_limited(err) or _is_network_unstable(err):
                if attempt < DOWNLOAD_RETRIES:
                    _backoff_sleep(attempt, "download")
                    continue
            _write_errlog(f"DOWNLOAD_FAIL {vid} {url}\n{err[:600]}")
            break

        except subprocess.TimeoutExpired:
            if attempt < DOWNLOAD_RETRIES:
                _backoff_sleep(attempt, "download-timeout")
                continue
            _write_errlog(f"TIMEOUT {vid} {url}")
            break
        except Exception as e:
            _write_errlog(f"EXC {vid} {url}: {e}")
            break

    # Fallback: coba gallery-dl
    print(f"  [FALLBACK] yt-dlp gagal → coba gallery-dl: {vid}")
    if _download_fallback_gallerydl(url, vid, title, caption, seq, db):
        return True

    if vid:
        try:
            db.mark_video_status(
                video_id=vid, url=url, title=title or "Untitled",
                uploader_handle="", status="failed", file_path=None, caption_path=None
            )
        except Exception:
            pass
    return False


def download_entries(entries: List[Dict], db: TikTokDB) -> int:
    total   = len(entries)
    success = 0
    if total == 0:
        return 0

    print(f"[INFO] Download {total} video (concurrency={CONCURRENT_DOWNLOADS}) → {OUTDIR}")
    step = max(5, total // 10)

    def task(e):
        return _download_one(
            url     = e.get("webpage_url") or e.get("url"),
            vid     = e.get("id"),
            title   = e.get("title") or "Untitled",
            caption = e.get("description") or e.get("fulltitle") or "",
            seq     = e.get("seq", 0),
            db      = db,
        )

    done = 0
    with ThreadPoolExecutor(max_workers=CONCURRENT_DOWNLOADS) as ex:
        futures = [ex.submit(task, e) for e in entries]
        for fut in as_completed(futures):
            try:
                if fut.result():
                    success += 1
            except Exception:
                pass
            done += 1
            if done % step == 0 or done == total:
                print(f"  progress: {done}/{total} (ok: {success})")
    return success

# ═══════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════

_SHOULD_STOP = False

def _sigint_handler(signum, frame):
    global _SHOULD_STOP
    _SHOULD_STOP = True
    print("\n[WARN] Dihentikan pengguna. Menyelesaikan batch berjalan...")

def main():
    signal.signal(signal.SIGINT, _sigint_handler)

    if not check_yt_dlp_installation():
        print("[ERROR] yt-dlp tidak ditemukan. Install: pip install -U yt-dlp")
        return

    try:
        ver = subprocess.run(["yt-dlp", "--version"], capture_output=True, text=True, timeout=10)
        if ver.returncode == 0:
            print(f"yt-dlp v{ver.stdout.strip()}")
    except Exception:
        pass

    if not os.path.exists(INPUT_FILE):
        print(f"[ERROR] {INPUT_FILE} tidak ditemukan.")
        return

    os.makedirs(OUTDIR, exist_ok=True)
    existing_max = detect_existing_max_seq(OUTDIR)
    seq_counter  = existing_max + 1
    print(f"[INFO] Lanjut penomoran dari: {seq_counter:04d}")

    db = TikTokDB(DB_PATH)

    # ── Opsi Reset DB ─────────────────────────────────────────────
    print(f"\nDB: {DB_PATH}")
    print("Reset DB? (opsional — berguna jika ingin re-download semua)")
    print("  1. Reset VIDEO saja (hapus riwayat download, user tetap)")
    print("  2. Reset SEMUA (video + users)")
    print("  3. Lanjut tanpa reset [default]")
    db_choice = input("Pilih (1/2/3 atau Enter): ").strip()
    if db_choice == "1":
        confirm = input("  ⚠️  Hapus semua record VIDEO di DB? (ketik 'ya'): ").strip().lower()
        if confirm == "ya":
            db.reset_videos()
            print("  ✅ Record video dihapus. DB siap dari awal.\n")
        else:
            print("  Dibatalkan.\n")
    elif db_choice == "2":
        confirm = input("  ⚠️  Hapus SEMUA data DB? (ketik 'ya'): ").strip().lower()
        if confirm == "ya":
            db.reset_all()
            print("  ✅ Semua data DB dihapus.\n")
        else:
            print("  Dibatalkan.\n")
    # ──────────────────────────────────────────────────────────────

    grand_listed = grand_kept = grand_downloaded = 0

    try:
        sources = read_sources_from_file(INPUT_FILE)
        if not sources:
            print("[ERROR] Tidak ada sumber valid di file input.")
            return
        print(f"Total sumber: {len(sources)}\n")

        for s_idx, src in enumerate(sources, 1):
            if _SHOULD_STOP:
                break

            print(f"[{s_idx}/{len(sources)}] Listing: {src}")
            entries, uploader = list_entries(src, LIST_TIMEOUT_S, MAX_PER_USER)

            if not entries:
                print("  → tidak ada entri / listing gagal\n")
                continue

            grand_listed += len(entries)
            print(f"  → {len(entries)} video ditemukan" + (f" (uploader: {uploader})" if uploader else ""))

            if REQUIRED_TAGS:
                entries = prefilter_by_hashtag(entries, REQUIRED_TAGS, TAG_MODE, db, MARK_SKIPPED_IN_DB)
            if not entries:
                print("  → tidak ada video lolos filter hashtag\n")
                continue

            grand_kept += len(entries)

            entries, dupes = drop_known_videos(entries, db)
            if dupes:
                print(f"  → skip {dupes} video sudah diketahui di DB")
            if not entries:
                print("  → tidak ada video baru\n")
                continue

            for e in entries:
                e["seq"] = seq_counter
                seq_counter += 1

            ok = download_entries(entries, db)
            grand_downloaded += ok
            print(f"  → selesai: {ok}/{len(entries)} berhasil\n")
            time.sleep(0.5)

        print("=" * 50)
        print("Selesai semua sumber.")
        print(f"  Listed     : {grand_listed}")
        print(f"  Lolos filter: {grand_kept}")
        print(f"  Downloaded  : {grand_downloaded}")
        print(f"  DB          : {DB_PATH}")

    finally:
        try:
            db.close()
        except Exception:
            pass

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        _write_errlog(f"FATAL {type(e).__name__}: {e}")
        print(f"[FATAL] {e}")
        sys.exit(1)
