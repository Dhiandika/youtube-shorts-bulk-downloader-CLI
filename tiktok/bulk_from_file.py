#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
bulk_from_file.py  (FAST streaming, hashtag-first)
- Baca file users.txt (1 user/URL per baris)
- Listing via `yt-dlp -J --flat-playlist` dengan timeout (anti-stuck)
- Untuk setiap video: fetch metadata penuh (socket_timeout), cek hashtag → skip cepat bila tidak cocok
- Anti-dupe via SQLite DB, opsi tandai skipped
- Download hanya untuk video yang lolos filter
"""

import os
import json
import subprocess
from typing import List, Dict, Tuple, Optional

from concurrent.futures import ThreadPoolExecutor, as_completed
from tiktok_dl.config import DEFAULT_DB, DEFAULT_OUTDIR
from tiktok_dl.utils import check_yt_dlp_installation, normalize_input_to_url_list
from tiktok_dl.db import TikTokDB
from tiktok_dl.filters import extract_hashtags, contains_required_hashtags
from tiktok_dl.downloader import download_entries

# =======================
# KONFIGURASI SEDERHANA
# =======================
INPUT_FILE          = "users.txt"          # file txt: 1 user/URL per baris (boleh @handle atau URL profil)
DB_PATH             = DEFAULT_DB
OUTDIR              = DEFAULT_OUTDIR
COOKIES_FROM_BROWSER= None                 # None | "chrome" | "firefox" | "edge"
MAX_PER_USER        = None                 # None = semua; atau batasi mis. 100

# Filter hashtag (kosongkan untuk nonaktif)
REQUIRED_TAGS       = ['#hololiveclips',' #hololivememes', '#hololiveshitpost','#kobokanaeru','#airaniiofifteen',' #vestiazeta','#kaelakovalskia',' #kanade','#ichijouririka','#shorts','#clips','#moricalliope',' #samekosaba','']                   # contoh: ["#fyp", "#hololive"]
TAG_MODE            = "any"                # "all" = semua wajib ada, "any" = minimal satu
MARK_SKIPPED_IN_DB  = True                 # tandai video yang tidak lolos hashtag sebagai 'skipped_hashtag' di DB
METADATA_WORKERS     = 8   # jumlah thread untuk prefilter metadata/hashtag

# Opsi unduhan
QUALITY             = "best"               # ekspresi -f yt-dlp: "best" | "worst" | "bv*+ba" | ...
FORMAT              = "mp4"                # "mp4" | "webm"

# Timeouts & retries
LIST_TIMEOUT_S      = 60                   # timeout listing per user (detik)
META_SOCKET_TIMEOUT = 15                   # socket timeout saat fetch metadata penuh (detik)
META_RETRIES        = 2                    # retries fetch metadata penuh

DRY_RUN             = False                # True = tidak mengunduh, hanya ringkasan


# ======================================
# UTIL: baca sumber dari file .txt
# ======================================
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


# ======================================================
# LIST ENTRIES CEPAT: via CLI `yt-dlp -J --flat-playlist`
# ======================================================
def list_entries_via_cli(src_url: str,
                         cookies_from_browser: Optional[str],
                         timeout_s: int,
                         max_items: Optional[int]) -> Tuple[List[Dict], Optional[str]]:
    """
    Listing seluruh video dari profil/URL menggunakan CLI JSON output.
    Mengembalikan (entries, uploader_name)
    """
    cmd = ["yt-dlp", "-J", "--flat-playlist", "--no-warnings", "--no-check-certificates", src_url]
    if cookies_from_browser:
        cmd[1:1] = ["--cookies-from-browser", cookies_from_browser]
    try:
        r = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_s,
            encoding="utf-8",
            errors="replace"
        )
    except subprocess.TimeoutExpired:
        print(f"[WARN] Listing timeout untuk: {src_url}")
        return [], None
    except Exception as e:
        print(f"[WARN] Listing gagal untuk {src_url}: {e}")
        return [], None

    if r.returncode != 0 or not r.stdout.strip():
        # TikTok kadang butuh cookies agar bisa mengembalikan playlist
        if r.stderr:
            print(f"[WARN] yt-dlp listing stderr:\n{r.stderr[:500]}")
        return [], None

    try:
        data = json.loads(r.stdout)
    except Exception as e:
        print(f"[WARN] Gagal parse JSON listing: {e}")
        return [], None

    uploader = data.get("uploader") or data.get("channel")
    entries = []
    for e in (data.get("entries") or []):
        url = e.get("webpage_url") or e.get("url")
        entries.append({
            "id": e.get("id"),
            "title": e.get("title") or e.get("description") or "Untitled",
            "webpage_url": url,
            "uploader": e.get("uploader") or uploader or "",
        })
        if max_items and len(entries) >= max_items:
            break

    # Sort by upload_date if available (flat sometimes has it)
    entries.sort(key=lambda v: v.get("upload_date", "99999999"))
    return entries, uploader


# ======================================================
# FETCH METADATA PENUH (caption lengkap) DENGAN TIMEOUT
# ======================================================
def fetch_full_metadata_quick(url: str,
                              cookies_from_browser: Optional[str]) -> Optional[Dict]:
    """
    Gunakan Python API tapi pakai socket_timeout + extractor_retries untuk mencegah "stuck".
    """
    import yt_dlp
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "socket_timeout": META_SOCKET_TIMEOUT,
        "extractor_retries": META_RETRIES,
    }
    if cookies_from_browser:
        ydl_opts["cookiesfrombrowser"] = (cookies_from_browser,)

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        return info
    except Exception as e:
        # Tidak fatal: kita cukup skip video ini
        return None


# ==========================================
# PREFILTER: cek hashtag → skip cepat
# ==========================================
def prefilter_streaming(entries, required_tags, mode, cookies_from_browser, db, mark_skipped):
    """
    Versi paralel: ambil metadata penuh & cek hashtag secara multithreaded.
    """
    if not required_tags:
        return entries

    kept = []
    required = [t.strip() for t in required_tags if t.strip()]
    total = len(entries)
    print(f"\nPrefilter hashtag (mode={mode}) untuk {total} video (workers={METADATA_WORKERS}) ...")

    def work(e):
        url = e.get("webpage_url")
        meta = fetch_full_metadata_quick(url, cookies_from_browser) or {}
        merged = dict(e)
        for k in ("description", "title", "fulltitle", "uploader", "channel", "id", "webpage_url"):
            if meta.get(k):
                merged[k] = meta.get(k)
        caption = (merged.get("description") or merged.get("title") or "")
        found = extract_hashtags(caption)
        ok = contains_required_hashtags(found, required, mode=mode)
        return ok, merged

    done = 0
    with ThreadPoolExecutor(max_workers=METADATA_WORKERS) as ex:
        futures = [ex.submit(work, e) for e in entries]
        for fut in as_completed(futures):
            ok, merged = fut.result()
            if ok:
                kept.append(merged)
            else:
                if mark_skipped and merged.get("id"):
                    db.mark_video_status(
                        video_id=merged["id"],
                        url=merged.get("webpage_url") or "",
                        title=merged.get("title") or "",
                        uploader_handle=(merged.get("uploader") or ""),
                        status="skipped_hashtag",
                        file_path=None,
                        caption_path=None
                    )
            done += 1
            if done % 25 == 0 or done == total:
                print(f"  progress: {done}/{total} (kept: {len(kept)})")

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


# =========================
# MAIN (tanpa arg CLI lain)
# =========================
def main():
    print("Cek yt-dlp...")
    if not check_yt_dlp_installation():
        return

    if not os.path.exists(INPUT_FILE):
        print(f"File input tidak ditemukan: {INPUT_FILE}")
        return

    db = TikTokDB(DB_PATH)

    try:
        sources = read_sources_from_file(INPUT_FILE)
        if not sources:
            print("Tidak ada sumber valid di file input.")
            return
        print(f"Sumber terbaca: {len(sources)}")

        all_entries: List[Dict] = []
        per_user_count: Dict[str, int] = {}
        # === STREAMING PER USER: listing dengan timeout, lalu langsung proses ===
        for s_idx, src in enumerate(sources, 1):
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
            per_user_count[uploader or entries[0].get("uploader") or "unknown"] = len(entries)
            print(f"  ditemukan {len(entries)} video")

            # Prefilter hashtag per-user (langsung cek caption → skip jika tak cocok)
            if REQUIRED_TAGS:
                entries = prefilter_streaming(
                entries=entries,
                required_tags=REQUIRED_TAGS,
                mode=TAG_MODE,
                cookies_from_browser=COOKIES_FROM_BROWSER,
                db=db,
                mark_skipped=MARK_SKIPPED_IN_DB
            )
                if not entries:
                    print("  semua video user ini tidak lolos hashtag → lanjut user berikutnya")
                    continue

            # kumpulkan untuk diunduh (nanti anti-dupe global)
            all_entries.extend(entries)

        if not all_entries:
            print("\nTidak ada video yang siap diunduh.")
            return

        # Anti-dupe global berdasar DB
        all_entries, dupes = drop_known_videos(all_entries, db)
        print(f"\nAnti-dupe: dilewati {dupes} video yang sudah tercatat di DB.")
        if not all_entries:
            print("Tidak ada video yang perlu diunduh setelah anti-dupe.")
            return

        # DRY RUN?
        if DRY_RUN:
            print("\n[D R Y - R U N] 20 video pertama yang akan diunduh:")
            for i, e in enumerate(all_entries[:20], 1):
                print(f"{i}. {(e.get('title') or 'Untitled')[:70]} | {e.get('webpage_url')}")
            print(f"Total siap diunduh: {len(all_entries)} (dry-run, tidak mengunduh)")
            return

        # Download
        os.makedirs(OUTDIR, exist_ok=True)
        print(f"\nMengunduh {len(all_entries)} video ke folder: {OUTDIR}")
        ok = download_entries(
            all_entries,
            OUTDIR,
            author_name=None,
            quality=QUALITY,
            file_format=FORMAT,
            cookies_from_browser=COOKIES_FROM_BROWSER,
            db=db
        )

        print("\nSelesai.")
        print(f"Berhasil: {ok}/{len(all_entries)} video.")
        print(f"Database: {DB_PATH}")
        print("Cek 'download_errors.log' jika ada error.")

    finally:
        db.close()


if __name__ == "__main__":
    main()
