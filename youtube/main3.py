import os
import re
import subprocess
from datetime import datetime, timedelta
from typing import Optional, List, Dict

from yt_short_downloader.config import DEFAULT_OUTPUT_DIR, DEFAULT_FILE_FORMAT
from yt_short_downloader.ytdlp_tools import check_yt_dlp_installation
from yt_short_downloader.fetch import get_short_links
from yt_short_downloader.orchestrator import download_videos_with_db
from yt_short_downloader.utils import normalize_upload_date, parse_upload_date

# Store: pakai SQLite yang stabil. Fallback TinyDB jika modul tidak ada.
try:
    from yt_short_downloader.db_sqlite import SqliteStore as Store
except Exception:
    from yt_short_downloader.db import TinyStore as Store


# ---------- Utilities kecil untuk debug ----------

def _show_ascii(s: str) -> str:
    """Sanitasi untuk tampilan console (hindari emoji/mathematical bold yg bikin charmap error)."""
    import unicodedata
    if s is None:
        return ""
    s = unicodedata.normalize("NFKD", str(s))
    s = s.encode("ascii", "ignore").decode("ascii", "ignore")
    s = re.sub(r"\s+", " ", s).strip()
    return s





def filter_entries_by_days(entries: List[Dict], days: Optional[int]) -> List[Dict]:
    if days is None:
        return entries
    cutoff = datetime.utcnow() - timedelta(days=days)
    kept: List[Dict] = []
    for e in entries:
        dt = parse_upload_date(e.get("upload_date"))
        if dt and dt >= cutoff:
            kept.append(e)
    return kept


def debug_dump_entries(entries: List[Dict], days: Optional[int], limit: int = 12) -> None:
    """Print ringkas untuk memeriksa bagaimana tanggal dibaca & difilter."""
    if days is None:
        print("\n[DEBUG] Mode tanpa filter tanggal.")
    else:
        cutoff = datetime.utcnow() - timedelta(days=days)
        print(f"\n[DEBUG] Cutoff: {cutoff.strftime('%Y-%m-%d')} (UTC)  | window: {days} hari")

    missing = 0
    print("[DEBUG] Contoh entri (maks 12):")
    for i, e in enumerate(entries[:limit], start=1):
        vid = e.get("id")
        title = _show_ascii(e.get("title", "Unknown Title"))
        raw = e.get("upload_date")
        norm = normalize_upload_date(raw)
        parsed = parse_upload_date(raw)
        parsed_s = parsed.strftime("%Y-%m-%d") if parsed else None
        if not parsed:
            missing += 1
        print(f"  {i:02d}. id={vid} | raw={raw} | norm={norm} | parsed={parsed_s} | title={title}")

    total = len(entries)
    total_missing = sum(1 for e in entries if not parse_upload_date(e.get("upload_date")))
    print(f"[DEBUG] Total entries: {total} | tanpa tanggal: {total_missing} | dengan tanggal: {total-total_missing}")


# ---------- Enrichment opsional ----------

def enrich_missing_upload_dates(entries: List[Dict], max_tasks: int = 25, days: Optional[int] = None) -> int:
    """
    Ambil upload_date untuk sebagian kecil (maks 25) entri yang kosong,
    dengan memanggil yt-dlp --dump-single-json per video (shorts).
    Return: berapa banyak yang berhasil dilengkapi.
    """
    filled = 0
    targets = [e for e in entries if not normalize_upload_date(e.get("upload_date"))][:max_tasks]
    if not targets:
        return 0

    cutoff = None
    if days:
        cutoff = datetime.utcnow() - timedelta(days=days)

    print(f"[DEBUG] Enrichment: mencoba melengkapi tanggal untuk {len(targets)} video (maks {max_tasks})...")
    for e in targets:
        vid = e.get("id")
        url = f"https://www.youtube.com/shorts/{vid}"
        try:
            res = subprocess.run(
                ["yt-dlp", url, "--skip-download", "--dump-single-json", "--no-check-certificate",
                 "--restrict-filenames", "--ignore-no-formats-error"],
                capture_output=True, text=True, timeout=45, encoding="utf-8", errors="replace"
            )
            if res.returncode == 0 and res.stdout:
                import json
                data = json.loads(res.stdout)
                up = data.get("upload_date")
                norm = normalize_upload_date(up)
                if norm:
                    e["upload_date"] = norm
                    filled += 1
                    print(f"  [+] {vid} -> upload_date={norm}")

                    # Optimization: Stop if we found a video older than cutoff
                    # Assumption: videos are roughly sorted descending (Newest First)
                    if cutoff:
                        dt = parse_upload_date(norm)
                        if dt and dt < cutoff:
                            print(f"  [Info] Found video older than {days} days ({norm}). Stopping enrichment.")
                            break
                else:
                    print(f"  [-] {vid} -> upload_date tidak valid: {up!r}")
            else:
                print(f"  [!] Gagal dump metadata untuk {vid}: rc={res.returncode}")
        except Exception as ex:
            print(f"  [!] Exception saat enrichment {vid}: {ex}")
    print(f"[DEBUG] Enrichment selesai. Berhasil isi tanggal: {filled}")
    return filled


# ---------- Interaksi kecil ----------

def ask_time_window_days() -> Optional[int]:
    print("\nPilih jendela waktu:")
    print("1. 7 hari terakhir")
    print("2. 30 hari terakhir")
    print("3. Custom (hari)")
    print("0. Semua video (tanpa filter)")
    choice = input("Pilih [0-3]: ").strip()
    if choice == "1":
        return 7
    if choice == "2":
        return 30
    if choice == "3":
        try:
            d = int(input("Masukkan jumlah hari: ").strip())
            return max(1, d)
        except Exception:
            print("Input invalid, pakai default 30 hari.")
            return 30
    return None


def ask_quality() -> str:
    print("\nQuality options:")
    print("1. FORCE 1080P (Best Quality) - [DEFAULT]")
    print("2. 1080p High Definition (Same as option 1)")
    
    # Kita hanya beri ilusi pilihan, padahal isinya sama-sama "best" 
    # yang sudah di-tweak di downloader.py untuk STRICT 1080P.
    
    choice = input("Enter quality choice (Default: 1): ").strip()
    print(">> SELECTED: FORCE 1080P (Strict Mode)")
    return "best"


# ---------- Main ----------

def main():
    try:
        print("YouTube Shorts Downloader (DEBUG Date Filter)")
        print("=" * 52)

        print("Checking yt-dlp installation...")
        if not check_yt_dlp_installation():
            print("Please install yt-dlp and try again.")
            return

        channel_url = input("\nEnter the YouTube channel URL: ").strip()
        if not channel_url:
            print("No URL provided. Exiting.")
            return

        days = ask_time_window_days()

        print("\nFetching video list...")
        all_entries, channel_name = get_short_links(channel_url)
        if not all_entries:
            print("No videos found or failed to fetch links.")
            return

        # DEBUG dump awal
        debug_dump_entries(all_entries, days, limit=12)

        # Filter awal
        candidate_entries = filter_entries_by_days(all_entries, days)

        # Jika hasil kosong & ada banyak tanpa tanggal -> Auto run enrichment (max 50)
        if days is not None and not candidate_entries:
            missing_total = sum(1 for e in all_entries if not parse_upload_date(e.get("upload_date")))
            if missing_total:
                print(f"\n[INFO] {missing_total} entries missing date. Auto-enriching top 300 to find recent videos...")
                enrich_missing_upload_dates(all_entries, max_tasks=300, days=days)
                
                print("\n[DEBUG] Dump ulang setelah enrichment:")
                debug_dump_entries(all_entries, days, limit=12)
                candidate_entries = filter_entries_by_days(all_entries, days)

        if days is not None and not candidate_entries:
            print(f"\nTidak ada video dalam {days} hari terakhir untuk channel ini.")
            return

        # DB & dedupe
        store = Store()
        channel_key = channel_url.split("/about")[0]
        store.upsert_channel(channel_key=channel_key, name=channel_name, url=channel_key)

        kept_entries: List[Dict] = []
        for e in candidate_entries:
            vid = e.get("id")
            title = e.get("title", "Unknown Title")
            up = normalize_upload_date(e.get("upload_date"))
            store.upsert_video(channel_key=channel_key, video_id=vid, title=title, upload_date=up)
            if not store.is_downloaded(channel_key, vid):
                kept_entries.append(e)

        skipped_dupe = len(candidate_entries) - len(kept_entries)
        print(f"\nChannel: {channel_name}")
        if days is None:
            print(f"Total video (tanpa filter tanggal): {len(candidate_entries)}")
        else:
            print(f"Total video (dalam {days} hari): {len(candidate_entries)}")
        print(f"Sudah pernah diunduh (skip dupe): {skipped_dupe}")
        print(f"Akan diunduh sekarang: {len(kept_entries)}")

        if not kept_entries:
            print("Tidak ada video baru sesuai filter & dedupe.")
            return

        preview_count = min(len(kept_entries), 10)
        print(f"\nPreview {preview_count} video yang akan diunduh:")
        for i, entry in enumerate(kept_entries[:preview_count], start=1):
            title = entry.get("title", "Unknown Title")
            if len(title) > 80:
                title = title[:77] + "..."
            print(f"{i}. {_show_ascii(title)}")

        confirm = input("\nProceed with download? (y/n): ").strip().lower()
        if confirm != "y":
            print("Canceled.")
            return

        # STRICT ENFORCEMENT: 1080p & H.264 MP4
        print("\n[INFO] Enforcing Strict 1080p & H.264 MP4 (Anti-403 Mode)")
        quality = "best"
        file_format = "mp4"

        output_directory = os.path.join(os.getcwd(), DEFAULT_OUTPUT_DIR)
        os.makedirs(output_directory, exist_ok=True)

        print(f"\nStarting download in {output_directory}...")
        print("Note: Caption files will be created for all videos, even if download fails.")
        download_videos_with_db(
            video_entries=kept_entries,
            output_path=output_directory,
            channel_name=channel_name,
            quality=quality,
            file_format=file_format,
            channel_key=channel_key,
            store=store,
        )

        print("\nDownload process completed!")
        print(f"Check the '{DEFAULT_OUTPUT_DIR}' folder for downloaded videos and caption files.")
        print("Any errors were logged to 'download_errors.log'")

    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")
        try:
            with open("download_errors.log", "a", encoding="utf-8") as log_file:
                log_file.write(f"Unexpected error in main_date_filter_debug: {e}\n")
        except Exception:
            pass
        print("Check 'download_errors.log' for details.")


if __name__ == "__main__":
    main()
