#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TikTok Bulk/Single Downloader (Fixed Full Caption)
- Caption .txt menggunakan description penuh (tanpa "...")
- Sumber: profil (@handle / URL), hashtag (#tag / URL), atau single video (URL)
- Mendukung cookies-from-browser (chrome/firefox/edge)
- Retry + backoff, multithread, progress bar
"""

import os
import re
import yt_dlp
import subprocess
import threading
from tqdm import tqdm
import time
import traceback
from urllib.parse import urlparse

MAX_RETRIES = 3       # jumlah maksimum percobaan ulang jika gagal
THREADS = 4           # jumlah thread paralel (atur sesuai koneksi/CPU)
DEFAULT_OUTDIR = "tiktok_downloads"

###############################################################################
# Util umum
###############################################################################

def check_yt_dlp_installation():
    """Cek apakah yt-dlp terpasang dan bisa dipanggil"""
    try:
        result = subprocess.run(
            ['yt-dlp', '--version'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            print(f"yt-dlp version: {result.stdout.strip()}")
            return True
        else:
            print("yt-dlp terpasang tapi tidak berjalan dengan benar.")
            return False
    except FileNotFoundError:
        print("yt-dlp tidak ditemukan di PATH.")
        print("Install dengan: pip install -U yt-dlp")
        return False
    except subprocess.TimeoutExpired:
        print("Pengecekan yt-dlp timeout.")
        return False
    except Exception as e:
        print(f"Error cek yt-dlp: {e}")
        return False


def is_tiktok_url(url: str) -> bool:
    try:
        netloc = urlparse(url).netloc.lower()
        return "tiktok.com" in netloc
    except Exception:
        return False


def sanitize_filename(title: str, maxlen=120) -> str:
    # buang non-printable
    title = re.sub(r'[^\x20-\x7E]', '', title)
    # ganti karakter bermasalah
    title = re.sub(r'[<>:"/\\|?*]', '_', title)
    # kompres spasi/underscore
    title = re.sub(r'[\s_]+', '_', title).strip('_')
    # batasi panjang
    if len(title) > maxlen:
        title = title[:maxlen]
    return title or "untitled"


def validate_filename(filename: str) -> bool:
    if re.search(r'[<>:"/\\|?*\x00-\x1F\x7F-\x9F]', filename):
        return False
    if not filename.isascii():
        return False
    if len(filename) > 255:
        return False
    return True


def get_unique_filename(base_path: str, filename: str) -> str:
    path = os.path.join(base_path, filename)
    if not os.path.exists(path):
        return filename
    name, ext = os.path.splitext(filename)
    i = 1
    while True:
        candidate = f"{name}_{i}{ext}"
        if not os.path.exists(os.path.join(base_path, candidate)):
            return candidate
        i += 1


def get_existing_index(output_path: str) -> int:
    files = os.listdir(output_path)
    idxs = [int(f.split(' - ')[0]) for f in files if f.split(' - ')[0].isdigit()]
    return max(idxs, default=0)


def cleanup_partial_downloads(output_path: str, filename_prefix: str):
    try:
        for f in os.listdir(output_path):
            if f.startswith(filename_prefix) and f.endswith('.part'):
                fp = os.path.join(output_path, f)
                try:
                    os.remove(fp)
                    print(f"Cleaned partial: {fp}")
                except Exception as e:
                    print(f"Gagal hapus partial {fp}: {e}")
    except Exception as e:
        print(f"Error cleanup partial: {e}")

###############################################################################
# Listing & Metadata TikTok
###############################################################################

def normalize_input_to_url_list(user_input: str):
    """
    user_input bisa:
    - URL profil: https://www.tiktok.com/@username
    - URL hashtag: https://www.tiktok.com/tag/hashtag
    - URL satu video: https://www.tiktok.com/@user/video/123...
    - Handle saja: @username
    - Tag saja: #hashtag
    """
    user_input = user_input.strip()

    if user_input.startswith('@'):
        return [f"https://www.tiktok.com/{user_input}"]
    if user_input.startswith('#'):
        tag = user_input[1:]
        return [f"https://www.tiktok.com/tag/{tag}"]
    if is_tiktok_url(user_input):
        return [user_input]
    # fallback (anggap ini handle)
    return [f"https://www.tiktok.com/@{user_input}"]


def extract_entries_from_source(src_url: str, max_videos=None, cookies_from_browser=None):
    """
    Ambil daftar entries (tanpa download) dari:
    - profil (playlist entries)
    - hashtag (playlist entries)
    - single video (1 entry)
    Catatan: untuk listing cepat, kita pakai extract_flat untuk profil/hashtag.
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
        entries = []
        if info is None:
            return [], None

        uploader = info.get("uploader") or info.get("channel") or None

        if "entries" in info:
            for e in info["entries"]:
                if not e:
                    continue
                url = e.get("webpage_url") or e.get("url")
                # pada extract_flat, 'url' biasanya sudah absolute untuk TikTok baru
                entries.append({
                    "id": e.get("id"),
                    "title": e.get("title") or e.get("description") or "Untitled",
                    "webpage_url": url,
                    "uploader": e.get("uploader") or uploader or "",
                })
        else:
            # single video
            entries.append({
                "id": info.get("id"),
                "title": info.get("title") or info.get("description") or "Untitled",
                "webpage_url": info.get("webpage_url") or src_url,
                "uploader": info.get("uploader") or uploader or "",
            })

        # sort by upload_date jika ada
        def sort_key(v):
            return v.get("upload_date", "99999999")
        entries = sorted(entries, key=sort_key)

        return entries[:max_videos] if max_videos else entries, uploader
    except Exception as e:
        tb = traceback.format_exc()
        print(f"Gagal mengambil daftar TikTok dari {src_url} : {e}")
        with open("download_errors.log", "a", encoding="utf-8") as log:
            log.write(f"Error fetch list: {src_url}\n{tb}\n")
        return [], None


def fetch_full_metadata(url: str, cookies_from_browser: str = None):
    """Ambil metadata lengkap untuk satu video TikTok (non-flat)."""
    ydl_opts = {
        "quiet": True,
        "skip_download": True,   # jangan unduh, hanya metadata
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
    Gunakan 'description' (caption asli TikTok) bila tersedia agar tidak terpotong.
    Fallback ke 'title' atau 'fulltitle'.
    """
    body = (meta.get("description")
            or meta.get("title")
            or meta.get("fulltitle")
            or "")
    author = meta.get("uploader") or meta.get("channel") or ""
    url = meta.get("webpage_url") or ""
    vid = meta.get("id") or ""

    # tulis apa adanya, tanpa menambah "..."
    lines = [body.strip(), "", f"TikTok: {author}".strip(),
             f"URL: {url}".strip(), f"ID: {vid}".strip()]
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def test_video_accessibility(url: str, cookies_from_browser=None) -> bool:
    try:
        cmd = ['yt-dlp', '--no-download', '--quiet', '--no-warnings', url]
        if cookies_from_browser:
            cmd = ['yt-dlp', '--no-download', '--quiet', '--no-warnings',
                   '--cookies-from-browser', cookies_from_browser, url]

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
            encoding='utf-8',
            errors='replace'
        )
        return result.returncode == 0
    except Exception as e:
        print(f"Error testing {url}: {e}")
        return False


def get_best_available_format_cli(quality_choice: str):
    """
    Map pilihan kualitas ke ekspresi -f yt-dlp.
    Untuk TikTok, biasanya bv*+ba/b ("best video + best audio / best") sudah cukup.
    """
    if quality_choice == 'best':
        return 'bv*+ba/b'
    if quality_choice == 'worst':
        return 'worst'
    # custom (misal "b", "bv*+ba", dsb)
    return quality_choice

###############################################################################
# Download
###############################################################################

def download_one_video(entry: dict, output_path: str, author_name: str,
                       quality: str, file_format: str, index: int,
                       cookies_from_browser: str = None) -> bool:
    url = entry.get("webpage_url")
    title = entry.get("title") or "Untitled"
    uploader = author_name or entry.get("uploader") or "tiktok"
    safe_title = sanitize_filename(title, 80)
    safe_uploader = sanitize_filename(uploader, 40)

    filename = f"{index:02d} - {safe_title} - {safe_uploader}.{file_format.lower()}"
    if not validate_filename(filename):
        filename = f"{index:02d} - video_{entry.get('id','unknown')}.{file_format.lower()}"
    filename = get_unique_filename(output_path, filename)
    filepath = os.path.join(output_path, filename)

    # ======= Ambil METADATA PENUH sebelum buat caption =======
    full = fetch_full_metadata(url, cookies_from_browser)
    if full:
        for key in ("description", "title", "fulltitle", "uploader", "channel", "id", "webpage_url"):
            if full.get(key):
                entry[key] = full.get(key)

    # caption .txt (pakai description penuh)
    caption_name = f"{os.path.splitext(filename)[0]}.txt"
    caption_path = os.path.join(output_path, caption_name)
    try:
        with open(caption_path, 'w', encoding='utf-8') as f:
            f.write(tiktok_caption_text(entry))
    except Exception as e:
        print(f"Gagal membuat caption: {e}")
        with open("download_errors.log", "a", encoding="utf-8") as log:
            log.write(f"Caption fail for {url}: {e}\n")

    cleanup_partial_downloads(output_path, f"{index:02d} - {safe_title}")

    fmt = get_best_available_format_cli(quality)
    cmd_base = [
        'yt-dlp',
        '--merge-output-format', file_format.lower(),
        '--output', filepath,
        '--no-warnings',
        '--quiet',
        '--ignore-errors',
        '--no-check-certificates',
        '--no-playlist',
        '-f', fmt,
        url
    ]
    if cookies_from_browser:
        # sisipkan setelah 'yt-dlp'
        cmd_base.insert(1, '--cookies-from-browser')
        cmd_base.insert(2, cookies_from_browser)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = subprocess.run(
                cmd_base,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
                timeout=600,
                encoding='utf-8',
                errors='replace'
            )

            if not os.path.exists(filepath) or os.path.getsize(filepath) < 1000:
                raise Exception("File terlalu kecil atau hilang, kemungkinan korup.")

            return True

        except subprocess.TimeoutExpired:
            msg = f"Timeout (attempt {attempt}) untuk {url}"
            print(msg)
            with open("download_errors.log", "a", encoding="utf-8") as log:
                log.write(msg + "\n")
            time.sleep(2 ** attempt)

        except subprocess.CalledProcessError as e:
            err = (
                f"Attempt {attempt} gagal untuk {url}\n"
                f"CMD: {' '.join(cmd_base)}\n"
                f"RC: {e.returncode}\n"
                f"STDOUT:\n{e.stdout}\n"
                f"STDERR:\n{e.stderr}\n"
            )
            print(err)
            with open("download_errors.log", "a", encoding="utf-8") as log:
                log.write(err + "\n")

            # Fallback terakhir: filename & format sederhana
            if attempt == MAX_RETRIES:
                simple_name = f"{index:02d} - video_{entry.get('id','unknown')}.{file_format.lower()}"
                simple_path = os.path.join(output_path, simple_name)
                cmd_fallback = [
                    'yt-dlp',
                    '--merge-output-format', file_format.lower(),
                    '--output', simple_path,
                    '--no-warnings',
                    '--quiet',
                    '--ignore-errors',
                    '--no-check-certificates',
                    '--no-playlist',
                    '-f', 'b',
                    url
                ]
                if cookies_from_browser:
                    cmd_fallback.insert(1, '--cookies-from-browser')
                    cmd_fallback.insert(2, cookies_from_browser)

                try:
                    print("Mencoba fallback filename & format sederhana...")
                    r = subprocess.run(
                        cmd_fallback,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        check=True,
                        timeout=600
                    )
                    if os.path.exists(simple_path) and os.path.getsize(simple_path) >= 1000:
                        return True
                except Exception as e2:
                    with open("download_errors.log", "a", encoding="utf-8") as log:
                        log.write(f"Fallback gagal untuk {url} : {e2}\n")

            time.sleep(2 ** attempt)

            # bersihkan file korup jika ada
            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except Exception as ce:
                    print(f"Gagal hapus file korup: {filepath} ({ce})")

        except Exception as e:
            msg = f"Attempt {attempt} error umum {url}: {e}"
            print(msg)
            with open("download_errors.log", "a", encoding="utf-8") as log:
                log.write(msg + "\n")
            time.sleep(2 ** attempt)

    return False


def download_entries(entries, output_path, author_name, quality, file_format, cookies_from_browser=None):
    os.makedirs(output_path, exist_ok=True)
    start_index = get_existing_index(output_path) + 1
    total = len(entries)

    lock = threading.Lock()
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
                quality, file_format, local_index, cookies_from_browser
            )
            if ok:
                with lock:
                    success["count"] += 1
            pbar.update(1)

    pbar = tqdm(total=total, desc="Downloading", unit="video")
    threads = []
    n_threads = min(THREADS, total if total > 0 else 1)
    for _ in range(n_threads):
        t = threading.Thread(target=worker, args=(pbar,))
        t.daemon = True
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    pbar.close()
    return success["count"]

###############################################################################
# Main interaktif
###############################################################################

def main():
    try:
        print("TikTok Bulk/Single Downloader (Full Caption Fix)")
        print("=" * 50)

        # cek yt-dlp
        print("Cek yt-dlp...")
        if not check_yt_dlp_installation():
            print("Silakan install/perbaiki yt-dlp lalu jalankan ulang.")
            return

        print("\nMasukkan sumber:")
        print("- Profil (URL atau @handle), misal: https://www.tiktok.com/@username atau @username")
        print("- Hashtag (URL atau #tag), misal: https://www.tiktok.com/tag/cat atau #cat")
        print("- Satu video (URL), misal: https://www.tiktok.com/@user/video/123456789")
        user_src = input("Input: ").strip()
        if not user_src:
            print("Tidak ada input. Keluar.")
            return

        sources = normalize_input_to_url_list(user_src)

        # Ambil daftar video untuk preview
        max_videos_input = input("Maksimal video (kosong = semua): ").strip()
        try:
            max_videos = int(max_videos_input) if max_videos_input else None
            if max_videos is not None and max_videos < 1:
                max_videos = None
        except:
            max_videos = None

        cookies_browser = input("Gunakan cookies-from-browser? (chrome/firefox/edge/blank=tidak): ").strip().lower()
        if cookies_browser not in ("chrome", "firefox", "edge"):
            cookies_browser = None

        all_entries = []
        author_name = None
        for src in sources:
            entries, uploader = extract_entries_from_source(src, max_videos=max_videos, cookies_from_browser=cookies_browser)
            if entries:
                all_entries.extend(entries)
            if uploader and not author_name:
                author_name = uploader

        if not all_entries:
            print("Tidak ada video yang ditemukan / gagal mengambil daftar.")
            return

        print(f"\nTotal video ditemukan: {len(all_entries)}")
        preview = min(len(all_entries), 10)
        print(f"Preview {preview} video pertama:")
        for i, e in enumerate(all_entries[:preview], 1):
            t = e.get("title", "Untitled")
            if len(t) > 80:
                t = t[:77] + "..."
            print(f"{i}. {t}")

        cont = input("\nLanjutkan? (y/n): ").strip().lower()
        if cont != 'y':
            print("Dibatalkan.")
            return

        print("\nOpsi kualitas:")
        print("1. best  (video+audio terbaik) [default]")
        print("2. worst (kualitas terendah)")
        print("3. custom format string (misal: b atau bv*+ba)")
        q = input("Pilih (1/2/custom): ").strip()
        if q == '2':
            quality = 'worst'
        elif q == '1' or q == '':
            quality = 'best'
        else:
            quality = q  # string custom akan diteruskan ke -f

        fmt = input("Format file (mp4/webm, default: mp4): ").strip().lower()
        if fmt not in ('mp4', 'webm'):
            fmt = 'mp4'

        outdir = os.path.join(os.getcwd(), DEFAULT_OUTDIR)
        os.makedirs(outdir, exist_ok=True)

        print(f"\nAkan mengunduh ke folder: {outdir}")
        print("Catatan: file caption .txt dibuat untuk setiap video, menggunakan description penuh.")
        confirm = input("Mulai download? (y/n): ").strip().lower()
        if confirm != 'y':
            print("Dibatalkan.")
            return

        ok_count = download_entries(
            all_entries, outdir, author_name, quality, fmt, cookies_from_browser=cookies_browser
        )

        print("\nSelesai.")
        print(f"Berhasil: {ok_count}/{len(all_entries)} video.")
        print("Cek 'download_errors.log' jika ada error.")

    except KeyboardInterrupt:
        print("\nDibatalkan oleh pengguna.")
    except Exception as e:
        print(f"\nTerjadi error tak terduga: {e}")
        with open("download_errors.log", "a", encoding="utf-8") as log:
            log.write(f"Unexpected main error: {e}\n")


if __name__ == "__main__":
    main()
