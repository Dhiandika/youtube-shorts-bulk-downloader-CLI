#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
bulk_from_file.py (sequential-per-user, anti-stuck & hardened, numbered filenames, resume numbering)

Alur per sumber (URL/user):
  1) Listing via yt-dlp (JSON, timeout, header, fallback cookies, backoff)
  2) Prefilter metadata/hashtag via yt-dlp CLI per video (timeout keras, batched)
  3) Anti-dupe per subset
  4) Langsung download subset itu via yt-dlp CLI (timeout keras, retry, cookies, header, IPv4, backoff)
     → SELALU tulis .txt di samping video:
         "<no> - <title> [<id>].mp4"
         "<no> - <title> [<id>].txt"
         TXT berisi: URL, ID, Title, Caption
  5) Lanjut ke sumber berikutnya

Penomoran:
  - Saat start, script akan scan OUTDIR mencari file yang match:
      ^\d{4}\s+-\s+
    → ambil nomor terbesar, lanjutkan dari nomor tersebut + 1.
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

# ====== suite modules ======
from tiktok_dl.config import DEFAULT_DB, DEFAULT_OUTDIR
from tiktok_dl.utils import check_yt_dlp_installation, normalize_input_to_url_list
from tiktok_dl.db import TikTokDB
from tiktok_dl.filters import extract_hashtags, contains_required_hashtags
# ===========================

# =======================
# KONFIGURASI SEDERHANA
# =======================
INPUT_FILE            = "users.txt"     # 1 user/URL per baris
DB_PATH               = DEFAULT_DB
OUTDIR                = DEFAULT_OUTDIR
COOKIES_FROM_BROWSER  = "chrome"        # None | "chrome" | "firefox" | "edge"
MAX_PER_USER          = None            # None = semua; atau batasi mis. 100

# Fallback listing → cookies
ENABLE_FALLBACK_COOKIES  = True
FALLBACK_COOKIES_BROWSER = "chrome"

# Header HTTP realistis
HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.tiktok.com/",
    "Accept-Language": "en-US,en;q=0.9",
}

FORCE_IPV4 = True  # stabilitas koneksi (opsional)

# Filter hashtag (kosong/invalid akan diabaikan otomatis)
REQUIRED_TAGS        = ['#movie',' #chineseshort ', '#film   ','#drama','',' #shorts','#anime',' #edit','#movieedit','#movieclips ','#clips',' #fyp','  #cartoon','#fyp','#tiktok']
TAG_MODE             = "any"            # "all" | "any"
MARK_SKIPPED_IN_DB   = True

# Prefilter metadata/hashtag
METADATA_WORKERS     = 8                # threads per batch
USE_CLI_FOR_META     = True             # CLI lebih tahan hang
META_TOTAL_TIMEOUT_S = 30               # timeout keras per video (detik)
META_SOCKET_TIMEOUT  = 15               # socket timeout internal yt-dlp
META_RETRIES         = 2                # extractor retries
META_BATCH_SIZE      = 32               # batch size metadata
META_SLEEP_BETWEEN   = 1.0              # jeda antar batch (detik)

# Unduhan
QUALITY                   = "best"
FORMAT                    = "mp4"
DOWNLOAD_TOTAL_TIMEOUT_S  = 180
DOWNLOAD_RETRIES          = 3
CONCURRENT_DOWNLOADS      = 3           # worker download per user

# Listing
LIST_TIMEOUT_S       = 60               # timeout per user listing

# Backoff (listing/meta/download saat 429/403/network)
BACKOFF_BASE_S       = 2.0
BACKOFF_MAX_S        = 60.0
BACKOFF_FACTOR       = 2.0
BACKOFF_JITTER_S     = 0.8

# ======================
# Util & Helper
# ======================
def _safe_basename(s: str) -> str:
    bad = '<>:"/\\|?*\n\r\t'
    for ch in bad:
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
    delay = min(BACKOFF_BASE_S * (BACKOFF_FACTOR ** attempt) + random.random() * BACKOFF_JITTER_S, BACKOFF_MAX_S)
    print(f"[INFO] Backoff {context}: sleep {delay:.1f}s (attempt={attempt})")
    time.sleep(delay)

def _looks_rate_limited(stderr: str) -> bool:
    s = (stderr or "").lower()
    return ("http error 429" in s) or ("too many requests" in s) or ("verify you're human" in s) or ("forbidden" in s) or ("http error 403" in s)

def _looks_network_unstable(stderr: str) -> bool:
    s = (stderr or "").lower()
    return ("timed out" in s) or ("timeout" in s) or ("connection reset" in s) or ("network is unreachable" in s)

def _normalize_required_tags(tags: List[str]) -> List[str]:
    out = []
    for t in tags or []:
        t2 = (t or "").strip()
        if not t2:
            continue
        if not t2.startswith("#"):
            t2 = f"#{t2}"
        out.append(t2)
    seen, res = set(), []
    for t in out:
        if t not in seen:
            seen.add(t)
            res.append(t)
    return res

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
    """
    Scan OUTDIR dan cari prefix file yang match:
      ^NNNN - ...
    Ambil NNNN terbesar. Jika tidak ada, return 0.
    """
    if not os.path.isdir(outdir):
        return 0

    pattern = re.compile(r"^(\d{4})\s+-\s+")
    max_seq = 0

    try:
        for name in os.listdir(outdir):
            m = pattern.match(name)
            if not m:
                continue
            try:
                num = int(m.group(1))
                if num > max_seq:
                    max_seq = num
            except ValueError:
                continue
    except Exception as e:
        _write_errlog(f"DETECT_SEQ_FAIL: {e}")
        return max_seq

    return max_seq

# ======================================================
# LIST ENTRIES: via CLI `yt-dlp -J --flat-playlist` + backoff
# ======================================================
def list_entries_via_cli(src_url: str,
                         cookies_from_browser: Optional[str],
                         timeout_s: int,
                         max_items: Optional[int]) -> Tuple[List[Dict], Optional[str]]:
    def _run_listing(cookies_from_browser_opt: Optional[str]) -> Tuple[List[Dict], Optional[str], str]:
        cmd = [
            "yt-dlp", "-J", "--flat-playlist",
            "--no-warnings", "--no-check-certificates",
            "--user-agent", HTTP_HEADERS["User-Agent"],
            "--referer", HTTP_HEADERS["Referer"],
            "--add-header", f"Accept-Language: {HTTP_HEADERS['Accept-Language']}",
            src_url
        ]
        if FORCE_IPV4:
            cmd.insert(1, "--force-ipv4")
        if cookies_from_browser_opt:
            cmd[1:1] = ["--cookies-from-browser", cookies_from_browser_opt]
        try:
            r = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, timeout=timeout_s, encoding="utf-8", errors="replace"
            )
        except subprocess.TimeoutExpired:
            return [], None, "timeout"
        except Exception as e:
            return [], None, f"exc:{e}"

        if r.returncode != 0 or not r.stdout.strip():
            return [], None, (r.stderr or "")

        try:
            data = json.loads(r.stdout)
        except Exception as e:
            return [], None, f"parse:{e}"

        uploader = data.get("uploader") or data.get("channel")
        entries: List[Dict] = []
        for e in (data.get("entries") or []):
            url = e.get("webpage_url") or e.get("url")
            entries.append({
                "id": e.get("id"),
                "title": e.get("title") or e.get("description") or "Untitled",
                "webpage_url": url,
                "uploader": e.get("uploader") or uploader or "",
                "upload_date": e.get("upload_date"),
                "description": e.get("description"),
            })
            if max_items and len(entries) >= max_items:
                break
        entries.sort(key=lambda v: v.get("upload_date") or "99999999")
        return entries, uploader, ""

    attempts = 0
    while attempts < 4:
        entries, uploader, err = _run_listing(cookies_from_browser)
        if entries:
            return entries, uploader
        if ENABLE_FALLBACK_COOKIES and not cookies_from_browser and FALLBACK_COOKIES_BROWSER:
            print("[INFO] Listing tanpa cookie kosong/gagal. Retry pakai cookies dari browser...")
            entries, uploader, err = _run_listing(FALLBACK_COOKIES_BROWSER)
            if entries:
                return entries, uploader
        if _looks_rate_limited(err) or _looks_network_unstable(err):
            _backoff_sleep(attempts, "listing")
            attempts += 1
            continue
        if err:
            snippet = err[:300].replace("\n", " ")
            print(f"[WARN] Listing gagal: {snippet}")
        return [], None
    return [], None

# ======================================================
# FETCH METADATA via CLI (timeout keras, anti-stuck) + backoff
# ======================================================
def fetch_full_metadata_cli(url: str, cookies_from_browser: Optional[str]) -> Optional[Dict]:
    cmd = [
        "yt-dlp", "-J", "--no-check-certificates",
        "--socket-timeout", str(META_SOCKET_TIMEOUT),
        "--extractor-retries", str(META_RETRIES),
        "--user-agent", HTTP_HEADERS["User-Agent"],
        "--referer", HTTP_HEADERS["Referer"],
        "--add-header", f"Accept-Language: {HTTP_HEADERS['Accept-Language']}",
        url,
    ]
    if FORCE_IPV4:
        cmd.insert(1, "--force-ipv4")
    if cookies_from_browser:
        cmd[1:1] = ["--cookies-from-browser", cookies_from_browser]

    for attempt in range(3):
        try:
            r = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, timeout=META_TOTAL_TIMEOUT_S, encoding="utf-8", errors="replace"
            )
        except subprocess.TimeoutExpired:
            if attempt < 2:
                _backoff_sleep(attempt, "meta-timeout")
                continue
            return None
        except Exception as e:
            _write_errlog(f"META_EXC {url} {type(e).__name__}: {e}")
            return None

        if r.returncode == 0 and r.stdout.strip():
            try:
                return json.loads(r.stdout)
            except Exception as e:
                _write_errlog(f"META_PARSE {url}: {e}")
                return None
        else:
            if _looks_rate_limited(r.stderr) or _looks_network_unstable(r.stderr):
                if attempt < 2:
                    _backoff_sleep(attempt, "meta")
                    continue
            _write_errlog(f"META_FAIL {url}\nSTDERR:\n{(r.stderr or '')[:600]}")
            return None
    return None

# ======================================================
# PREFILTER: cek hashtag → skip cepat (batched)
# ======================================================
def prefilter_streaming(entries, required_tags, mode, cookies_from_browser, db, mark_skipped):
    required = _normalize_required_tags(required_tags)
    if not required:
        return entries

    kept = []
    total = len(entries)
    print(f"\nPrefilter hashtag (mode={mode}) untuk {total} video (workers={METADATA_WORKERS}) ...")

    def work(e):
        url = e.get("webpage_url")
        meta = fetch_full_metadata_cli(url, cookies_from_browser) if USE_CLI_FOR_META else None
        merged = dict(e)
        if meta:
            for k in ("description", "title", "fulltitle", "uploader", "channel", "id", "webpage_url"):
                if meta.get(k):
                    merged[k] = meta.get(k)
            caption = (merged.get("description") or merged.get("title") or "")
            found = extract_hashtags(caption)
            ok = contains_required_hashtags(found, required, mode=mode)
        else:
            ok = False
        return ok, merged

    done = 0
    for start in range(0, total, META_BATCH_SIZE):
        batch = entries[start:start + META_BATCH_SIZE]
        with ThreadPoolExecutor(max_workers=METADATA_WORKERS) as ex:
            futures = [ex.submit(work, e) for e in batch]
            for fut in as_completed(futures):
                try:
                    ok, merged = fut.result()
                except Exception:
                    ok, merged = False, {}
                if ok:
                    kept.append(merged)
                else:
                    if mark_skipped and merged.get("id"):
                        try:
                            db.mark_video_status(
                                video_id=merged["id"],
                                url=merged.get("webpage_url") or "",
                                title=merged.get("title") or "",
                                uploader_handle=(merged.get("uploader") or ""),
                                status="skipped_hashtag",
                                file_path=None,
                                caption_path=None
                            )
                        except Exception:
                            pass
                done += 1
                if done % 25 == 0 or done == total:
                    print(f"  progress: {done}/{total} (kept: {len(kept)})")
        if META_SLEEP_BETWEEN and (start + META_BATCH_SIZE) < total:
            time.sleep(META_SLEEP_BETWEEN)

    print(f"Video lolos hashtag: {len(kept)}")
    return kept

# ==========================================
# ANTI-DUPE via DB
# ==========================================
def drop_known_videos(entries: List[Dict], db: TikTokDB) -> Tuple[List[Dict], int]:
    out, dupes = [], 0
    for e in entries:
        vid = e.get("id")
        if vid and db.is_video_known(vid):
            dupes += 1
            continue
        out.append(e)
    return out, dupes

# ======================================================
# Downloader CLI per video (timeout, retry, cookies) + TXT SELALU + PENOMORAN
# ======================================================
def _build_output_template(seq: int, title: str, vid: str) -> str:
    safe_title = _safe_basename(title or "Untitled")
    return os.path.join(OUTDIR, f"{seq:04d} - {safe_title} [{vid}].%(ext)s")

def _fallback_caption_path(seq: int, title: str, vid: str) -> str:
    safe_title = _safe_basename(title or "Untitled")
    return os.path.join(OUTDIR, f"{seq:04d} - {safe_title} [{vid}].txt")

def _write_sidecar_txt(txt_path: str, url: str, vid: Optional[str], title: Optional[str], caption: Optional[str]):
    content_lines = [
        f"URL: {url or ''}",
        f"ID: {vid or ''}",
        f"Title: {title or ''}",
        "",
        "Caption:",
        caption or ""
    ]
    os.makedirs(os.path.dirname(txt_path), exist_ok=True)
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(content_lines))

def _download_one(url: str, vid: str, title: str, caption: Optional[str],
                  seq: int, db: TikTokDB, cookies_from_browser: Optional[str]) -> bool:
    out_tpl = _build_output_template(seq, title, vid)
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
        url
    ]
    if FORCE_IPV4:
        cmd.insert(1, "--force-ipv4")
    if cookies_from_browser:
        cmd[1:1] = ["--cookies-from-browser", cookies_from_browser]

    # status: downloading
    if vid:
        try:
            db.mark_video_status(
                video_id=vid, url=url, title=title or "Untitled",
                uploader_handle="", status="downloading", file_path=None, caption_path=None
            )
        except Exception:
            pass

    for attempt in range(DOWNLOAD_RETRIES + 1):
        try:
            r = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, timeout=DOWNLOAD_TOTAL_TIMEOUT_S, encoding="utf-8", errors="replace"
            )
            if r.returncode == 0:
                final_path = ""
                if r.stdout:
                    lines = [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
                    if lines:
                        final_path = lines[-1]

                if final_path:
                    base, _ = os.path.splitext(final_path)
                    txt_path = base + ".txt"
                else:
                    txt_path = _fallback_caption_path(seq, title, vid)

                try:
                    _write_sidecar_txt(txt_path, url, vid, title, caption or "")
                    try:
                        db.mark_video_status(
                            video_id=vid, url=url, title=title or "Untitled",
                            uploader_handle="", status="success",
                            file_path=None, caption_path=txt_path
                        )
                    except Exception:
                        pass
                except Exception as ce:
                    _write_errlog(f"CAPTION_WRITE_FAIL {vid} {url}: {ce}")
                    try:
                        db.mark_video_status(
                            video_id=vid, url=url, title=title or "Untitled",
                            uploader_handle="", status="success",
                            file_path=None, caption_path=None
                        )
                    except Exception:
                        pass
                return True

            err = (r.stderr or "")
            if _looks_rate_limited(err) or _looks_network_unstable(err):
                if attempt < DOWNLOAD_RETRIES:
                    _backoff_sleep(attempt, "download")
                    continue
            _write_errlog(f"DOWNLOAD_FAIL {vid} {url}\nSTDERR:\n{err[:600]}")
            break

        except subprocess.TimeoutExpired:
            if attempt < DOWNLOAD_RETRIES:
                _backoff_sleep(attempt, "download-timeout")
                continue
            _write_errlog(f"TIMEOUT {vid} {url}")
            break
        except Exception as e:
            _write_errlog(f"EXC {vid} {url} {type(e).__name__}: {e}")
            break

    if vid:
        try:
            db.mark_video_status(
                video_id=vid, url=url, title=title or "Untitled",
                uploader_handle="", status="failed",
                file_path=None, caption_path=None
            )
        except Exception:
            pass
    return False

def download_entries_cli(entries: List[Dict],
                         cookies_from_browser: Optional[str],
                         db: TikTokDB,
                         concurrent_downloads: int = CONCURRENT_DOWNLOADS) -> int:
    success = 0
    total = len(entries)
    if total == 0:
        return 0
    print(f"[INFO] Mulai download subset: {total} video, concurrency={concurrent_downloads}")

    def task(e):
        url = e.get("webpage_url") or e.get("url")
        vid = e.get("id")
        title = e.get("title") or "Untitled"
        caption = e.get("description") or e.get("fulltitle") or ""
        seq = e.get("seq", 0)
        return _download_one(url, vid, title, caption, seq, db, cookies_from_browser)

    done = 0
    report_step = max(5, total // 10)
    with ThreadPoolExecutor(max_workers=concurrent_downloads) as ex:
        futures = [ex.submit(task, e) for e in entries]
        for fut in as_completed(futures):
            try:
                if fut.result():
                    success += 1
            except Exception:
                pass
            done += 1
            if done % report_step == 0 or done == total:
                print(f"  download progress (subset): {done}/{total} (ok: {success})")
    return success

# =========================
# MAIN (sequential-per-user)
# =========================
_SHOULD_STOP = False
def _sigint_handler(signum, frame):
    global _SHOULD_STOP
    _SHOULD_STOP = True
    print("\n[WARN] Dihentikan oleh pengguna. Menyelesaikan batch berjalan...")

def main():
    signal.signal(signal.SIGINT, _sigint_handler)

    print("Cek yt-dlp...")
    if not check_yt_dlp_installation():
        print("[ERROR] yt-dlp tidak ditemukan. Install: pip install -U yt-dlp")
        return

    try:
        ver = subprocess.run(["yt-dlp", "--version"], capture_output=True, text=True, timeout=10)
        if ver.returncode == 0 and ver.stdout.strip():
            print(f"yt-dlp version: {ver.stdout.strip()}")
    except Exception:
        pass

    if not os.path.exists(INPUT_FILE):
        print(f"[ERROR] File input tidak ditemukan: {INPUT_FILE}")
        return

    os.makedirs(OUTDIR, exist_ok=True)
    # DETEKSI NOMOR TERAKHIR YANG SUDAH ADA
    existing_max = detect_existing_max_seq(OUTDIR)
    if existing_max > 0:
        print(f"[INFO] Nomor file terakhir di '{OUTDIR}': {existing_max:04d}")
    else:
        print(f"[INFO] Tidak ditemukan file bernomor di '{OUTDIR}', mulai dari 0001.")

    db = TikTokDB(DB_PATH)

    grand_listed = 0
    grand_kept = 0
    grand_downloaded = 0
    seq_counter = existing_max + 1   # penomoran global lanjut dari yang sudah ada

    try:
        sources = read_sources_from_file(INPUT_FILE)
        if not sources:
            print("[ERROR] Tidak ada sumber valid di file input.")
            return
        print(f"Sumber terbaca: {len(sources)}")

        for s_idx, src in enumerate(sources, 1):
            if _SHOULD_STOP:
                break

            print(f"\n[{s_idx}/{len(sources)}] Listing user: {src}")
            entries, uploader = list_entries_via_cli(
                src_url=src,
                cookies_from_browser=COOKIES_FROM_BROWSER,
                timeout_s=LIST_TIMEOUT_S,
                max_items=MAX_PER_USER
            )
            if not entries:
                print("  (tidak ada entri / listing gagal)")
                continue

            per_user = len(entries)
            grand_listed += per_user
            print(f"  ditemukan {per_user} video")

            # Prefilter hashtag untuk user ini
            if REQUIRED_TAGS:
                kept = prefilter_streaming(
                    entries=entries,
                    required_tags=REQUIRED_TAGS,
                    mode=TAG_MODE,
                    cookies_from_browser=COOKIES_FROM_BROWSER,
                    db=db,
                    mark_skipped=MARK_SKIPPED_IN_DB
                )
            else:
                kept = entries

            if not kept:
                print("  semua video user ini tidak lolos hashtag → lanjut user berikutnya")
                continue

            grand_kept += len(kept)

            # Anti-dupe untuk subset user ini
            kept, dupes = drop_known_videos(kept, db)
            if dupes:
                print(f"  anti-dupe: skip {dupes} video sudah tercatat di DB")
            if not kept:
                print("  tidak ada video baru untuk diunduh pada user ini")
                continue

            # Tambahkan nomor urut global (supaya nama file 0001, 0002, dst)
            for e in kept:
                e["seq"] = seq_counter
                seq_counter += 1

            # Langsung unduh subset ini
            print(f"  mulai unduh {len(kept)} video untuk user ini → {OUTDIR}")
            ok = download_entries_cli(
                kept,
                cookies_from_browser=COOKIES_FROM_BROWSER,
                db=db,
                concurrent_downloads=CONCURRENT_DOWNLOADS
            )
            grand_downloaded += ok
            print(f"  selesai user ini: ok {ok}/{len(kept)}")

            # jeda kecil antar user untuk redam rate-limit
            time.sleep(0.5)

        print("\nSelesai semua sumber.")
        print(f"Rekap total: listed={grand_listed}, lolos_hashtag={grand_kept}, downloaded={grand_downloaded}")
        print(f"Database: {DB_PATH}")
        print("Cek 'download_errors.log' jika ada error.")

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
        print(f"[FATAL] {type(e).__name__}: {e}")
        sys.exit(1)
