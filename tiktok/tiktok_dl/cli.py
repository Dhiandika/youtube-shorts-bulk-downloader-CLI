import os

from .config import DEFAULT_OUTDIR, DEFAULT_DB
from .utils import check_yt_dlp_installation
from .db import TikTokDB
from .meta import extract_entries_from_source, normalize_input_to_url_list
from .downloader import download_entries

def main():
    try:
        print("TikTok Bulk/Single Downloader (Modular, DB + Full Caption)")
        print("=" * 60)

        # cek yt-dlp
        print("Cek yt-dlp...")
        if not check_yt_dlp_installation():
            print("Silakan install/perbaiki yt-dlp lalu jalankan ulang.")
            return

        # DB
        db_path = input(f"Path database SQLite (default: {DEFAULT_DB}): ").strip() or DEFAULT_DB
        db = TikTokDB(db_path)

        print("\nMasukkan sumber:")
        print("- Profil (URL atau @handle), misal: https://www.tiktok.com/@username atau @username")
        print("- Hashtag (URL atau #tag), misal: https://www.tiktok.com/tag/cat atau #cat")
        print("- Satu video (URL), misal: https://www.tiktok.com/@user/video/123456789")
        user_src = input("Input: ").strip()
        if not user_src:
            print("Tidak ada input. Keluar.")
            db.close()
            return

        sources = normalize_input_to_url_list(user_src)

        # listing
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

        all_entries, author_name = [], None
        for src in sources:
            entries, uploader = extract_entries_from_source(src, max_videos=max_videos, cookies_from_browser=cookies_browser)
            if entries:
                all_entries.extend(entries)
            if uploader and not author_name:
                author_name = uploader

        if not all_entries:
            print("Tidak ada video yang ditemukan / gagal mengambil daftar.")
            db.close()
            return

        # filter dupe awal (berdasarkan video_id yang sudah ada di DB)
        filtered, dupes = [], 0
        for e in all_entries:
            vid = e.get("id")
            if vid and db.is_video_known(vid):
                dupes += 1
                continue
            filtered.append(e)
        all_entries = filtered

        if not all_entries:
            print("Semua video yang ditemukan sudah tercatat di database. Tidak ada yang perlu diunduh.")
            db.close()
            return

        print(f"\nTotal video untuk diproses: {len(all_entries)} (terlewati dupe: {dupes})")
        preview = min(len(all_entries), 10)
        print(f"Preview {preview} video pertama:")
        for i, e in enumerate(all_entries[:preview], 1):
            t = e.get("title", "Untitled")
            if len(t) > 80:
                t = t[:77] + "..."
            print(f"{i}. {t}")

        cont = input("\nLanjutkan? (y/n): ").strip().lower()
        if cont != "y":
            print("Dibatalkan.")
            db.close()
            return

        print("\nOpsi kualitas:")
        print("1. best  (video+audio terbaik) [default]")
        print("2. worst (kualitas terendah)")
        print("3. custom format string (misal: b atau bv*+ba)")
        q = input("Pilih (1/2/custom): ").strip()
        if q == "2":
            quality = "worst"
        elif q == "1" or q == "":
            quality = "best"
        else:
            quality = q

        fmt = input("Format file (mp4/webm, default: mp4): ").strip().lower()
        if fmt not in ("mp4", "webm"):
            fmt = "mp4"

        outdir = os.path.join(os.getcwd(), DEFAULT_OUTDIR)
        os.makedirs(outdir, exist_ok=True)

        print(f"\nAkan mengunduh ke folder: {outdir}")
        print("Catatan: file caption .txt dibuat untuk setiap video (description penuh).")
        confirm = input("Mulai download? (y/n): ").strip().lower()
        if confirm != "y":
            print("Dibatalkan.")
            db.close()
            return

        ok_count = download_entries(
            all_entries, outdir, author_name, quality, fmt,
            cookies_from_browser=cookies_browser, db=db
        )

        print("\nSelesai.")
        print(f"Berhasil: {ok_count}/{len(all_entries)} video.")
        print(f"Database: {db_path}")
        print("Cek 'download_errors.log' jika ada error.")
        db.close()

    except KeyboardInterrupt:
        print("\nDibatalkan oleh pengguna.")
    except Exception as e:
        print(f"\nTerjadi error tak terduga: {e}")
        with open("download_errors.log", "a", encoding="utf-8") as log:
            log.write(f"Unexpected main error: {e}\n")
