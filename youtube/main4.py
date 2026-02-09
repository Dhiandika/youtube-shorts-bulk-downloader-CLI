import os
import re
import time
import random
import subprocess
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple

# Optional local modules (imported lazily/safely later)
# import sort
# import cek_resolusi
# import add_costume_hastag

from yt_short_downloader.config import DEFAULT_OUTPUT_DIR, DEFAULT_FILE_FORMAT
from yt_short_downloader.ytdlp_tools import check_yt_dlp_installation
from yt_short_downloader.fetch import get_short_links
from yt_short_downloader.orchestrator import download_videos_with_db
from yt_short_downloader.utils import normalize_upload_date, parse_upload_date
import subprocess

# Store: pakai SQLite yang stabil. Fallback TinyDB jika modul tidak ada.
try:
    from yt_short_downloader.db_sqlite import SqliteStore as Store
except Exception:
    from yt_short_downloader.db import TinyStore as Store


def enrich_missing_upload_dates(entries: List[Dict], max_tasks: int = 25, days: Optional[int] = None) -> int:
    """
    Ambil upload_date untuk sebagian entri yang kosong (yt-dlp extract_flat sering kali null di shorts),
    dengan memanggil yt-dlp --dump-single-json per video.
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
                    # print(f"  [+] {vid} -> upload_date={norm}")

                    # Optimization: Stop if we found a video older than cutoff
                    if cutoff:
                        dt = parse_upload_date(norm)
                        if dt and dt < cutoff:
                            print(f"  [Info] Found video older than {days} days ({norm}). Stopping enrichment.")
                            break
                else:
                    pass # print(f"  [-] {vid} -> upload_date tidak valid: {up!r}")
        except Exception as ex:
            print(f"  [!] Exception saat enrichment {vid}: {ex}")
    print(f"[DEBUG] Enrichment selesai. Berhasil isi tanggal: {filled}")
    return filled


def _show_ascii(s: str) -> str:
    """Sanitasi untuk tampilan console."""
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


def load_channel_links(filepath: str) -> List[str]:
    """Load valid channel links from a text file."""
    if not os.path.exists(filepath):
        return []
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    links = []
    for line in lines:
        line = line.strip()
        if line and not line.startswith('#'):
            links.append(line)
    return links


def reset_database():
    """Hapus database sqlite untuk memulai dari nol."""
    db_path = os.path.join(os.getcwd(), "data", "ytshorts.db")
    if os.path.exists(db_path):
        print(f"\n[WARNING] Anda akan menghapus database: {db_path}")
        print("Semua riwayat unduhan akan hilang! Script akan mengunduh ulang video yang sudah ada.")
        confirm = input("Ketik 'RESET' untuk konfirmasi: ").strip()
        if confirm == 'RESET':
            try:
                os.remove(db_path)
                print("Database berhasil dihapus. Session baru dimulai.")
                # Re-init store check variable if needed, but Store() init handles file creation
            except Exception as e:
                print(f"Gagal menghapus database: {e}")
        else:
            print("Batal reset database.")
    else:
        print("Database belum ada. Tidak perlu reset.")

def ask_scan_days() -> Optional[int]:
    print("\nPilih rentang waktu scan:")
    print("1. 7 Hari terakhir")
    print("2. 30 Hari terakhir")
    print("3. Custom hari")
    print("0. Semua video (tanpa filter)")
    print("9. RESET DATABASE (Hapus Riwayat Unduhan)")
    
    choice = input("Pilih [0-3] atau 9: ").strip()
    
    if choice == "9":
        reset_database()
        return ask_scan_days()
    
    if choice == "1":
        return 7
    if choice == "2":
        return 30
    if choice == "3":
        try:
            d = int(input("Masukkan jumlah hari: ").strip())
            return max(1, d)
        except ValueError:
            print("Input tidak valid, menggunakan default 30 hari.")
            return 30
    if choice == "0":
        return None
    
    print("Pilihan tidak valid, default ke 7 hari.")
    return 7


def ask_quality() -> str:
    print("\nQuality options:")
    print("1. FORCE 1080P (Best Quality) - [DEFAULT]")
    # User request: "buatkan agar force 1080"
    
    choice = input("Enter quality choice (Default: 1): ").strip()
    print(">> SELECTED: FORCE 1080P (Strict Mode)")
    return "best"


def process_channel(channel_url: str, days: Optional[int], quality: str, file_format: str, store: Store, output_directory: str) -> Tuple[int, int, int]:
    print(f"\nProcessing Channel: {channel_url}")
    print("-" * 50)
    
    try:
        all_entries, channel_name = get_short_links(channel_url)
    except Exception as e:
        print(f"Error fetching channel: {e}")
        return 0, 0, 0

    if not all_entries:
        print(f"Skipping {channel_url}: No videos found or failed to fetch.")
        return 0, 0, 0

    # Filter by date
    candidate_entries = filter_entries_by_days(all_entries, days)
    
    # Jika hasil kosong & ada banyak tanpa tanggal -> Auto run enrichment (max 50)
    # Ini logic perbaikan untuk kasus "Tidak ada video dalam 3 hari terakhir" padahal ada tapi upload_date None
    if days is not None and not candidate_entries:
        missing_total = sum(1 for e in all_entries if not parse_upload_date(e.get("upload_date")))
        if missing_total:
            # Kita coba enrich lebih banyak jika mode batch (misal 50)
            print(f"\n[INFO] {missing_total} entries missing date. Auto-enriching top 50 to find recent videos...")
            enrich_missing_upload_dates(all_entries, max_tasks=50, days=days)
            # Re-filter setelah enrichment
            candidate_entries = filter_entries_by_days(all_entries, days)

    if days is not None and not candidate_entries:
        print(f"Tidak ada video dalam {days} hari terakhir untuk channel ini.")
        return 0, 0, 0

    # DB & Dedupe
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
    found_filtered = len(candidate_entries)
    queued_count = len(kept_entries)

    print(f"Channel: {channel_name}")
    print(f"Found: {found_filtered} videos (filtered)")
    print(f"Skipped (Already Downloaded): {skipped_dupe}")
    print(f"Queued for Download: {queued_count}")

    if not kept_entries:
        print("No new videos to download.")
        return found_filtered, skipped_dupe, queued_count

    print(f"Downloading {queued_count} videos...")
    download_videos_with_db(
        video_entries=kept_entries,
        output_path=output_directory,
        channel_name=channel_name,
        quality=quality,
        file_format=file_format,
        channel_key=channel_key,
        store=store,
    )
    return found_filtered, skipped_dupe, queued_count


def count_files(directory: str) -> int:
    """Recursively counting files to track new downloads accurately."""
    total = 0
    for root, dirs, files in os.walk(directory):
        total += len(files)
    return total


def main():
    try:
        print("YouTube Shorts Bulk Downloader - Batch Mode (main4)")
        print("=" * 55)

        if not check_yt_dlp_installation():
            print("Please install yt-dlp and try again.")
            return

        # Load links
        link_file = os.path.join(os.path.dirname(__file__), "short_link.txt")
        links = load_channel_links(link_file)
        
        if not links:
            print(f"Error: No links found in {link_file}")
            print("Please add channel URLs to the file and try again.")
            if not os.path.exists(link_file):
                with open(link_file, 'w') as f:
                    f.write("# Add YouTube Channel Shorts URLs here, one per line\n")
                print(f"Created empty {link_file} for you.")
            return

        print(f"Loaded {len(links)} channels from {link_file}")

        # Global Settings
        days = ask_scan_days()
        
        # STRICT ENFORCEMENT: 1080p & H.264 MP4
        print("\n[INFO] Enforcing Strict 1080p & H.264 MP4 (Anti-403 Mode)")
        quality = "best"
        file_format = "mp4"

        output_directory = os.path.join(os.getcwd(), DEFAULT_OUTPUT_DIR)
        os.makedirs(output_directory, exist_ok=True)
        
        # Stats Initialization
        initial_file_count = count_files(output_directory)
        stats = {
            "channels_processed": 0,
            "total_found": 0,
            "total_skipped": 0,
            "total_queued": 0
        }
        
        # Determine store
        # Gunakan default behavior Store() seperti main3.py
        # Default: os.path.join(os.getcwd(), "data", "ytshorts.db")
        store = Store()
        print(f"Database Path: {store.db_path}")

        print(f"\nStarting Batch Process for {len(links)} channels...")
        print(f"Output Directory: {output_directory}")
        
        start_time = time.time()

        for i, link in enumerate(links, 1):
            print(f"\n[{i}/{len(links)}] processing...")
            try:
                found, skipped, queued = process_channel(link, days, quality, file_format, store, output_directory)
                stats["channels_processed"] += 1
                stats["total_found"] += found
                stats["total_skipped"] += skipped
                stats["total_queued"] += queued
                
                # Jeda antar channel untuk menghindari rate-limit/ban YouTube
                # "terlalu banyak error" bisa jadi karena terlalu agresif
                if i < len(links):
                    sleep_sec = random.randint(10, 20)
                    print(f"Sleeping for {sleep_sec} seconds before next channel...")
                    time.sleep(sleep_sec)
                    
            except Exception as e:
                print(f"Error processing {link}: {e}")
                import traceback
                traceback.print_exc()

        final_file_count = count_files(output_directory)
        
        # Approximate new files (videos + txts + artifacts)
        # Assuming most new files are downloads.
        files_added = max(0, final_file_count - initial_file_count)
        
        duration = time.time() - start_time
        duration_str = str(timedelta(seconds=int(duration)))

        print("\n" + "="*55)
        print("BATCH PROCESSING COMPLETED")
        print("="*55)
        
        print("\nSUMMARY STATISTICS:")
        print(f"Channels Processed : {stats['channels_processed']} / {len(links)}")
        print(f"Total Videos Found : {stats['total_found']}")
        print(f"Total Skipped      : {stats['total_skipped']} (Duplicate/Old)")
        print(f"Total Queued       : {stats['total_queued']}")
        print(f"Files Added (Est.) : {files_added}")
        print(f"Total Duration     : {duration_str}")
        print("-" * 55)

        print("\nStarting Post-Processing Workflow...")
        print("="*55)
        
        # 1. Sort & Rename
        try:
            print("\n[Step 1/3] Sorting and Renaming files...")
            import sort
            sort.rename_files(output_directory, newest_first=True)
        except ImportError:
            print("Module 'sort' not found or failed to import. Skipping Step 1.")
        except Exception as e:
            print(f"Error in sorting: {e}")

        # 2. Check Resolution & Organize
        try:
            print("\n[Step 2/3] Checking Resolution and moving to subfolders...")
            import cek_resolusi
            # Default to reels (9:16)
            cek_resolusi.sort_files_by_resolution(output_directory, target_mode='reels')
        except ImportError as e:
            print(f"Module 'cek_resolusi' (or dependencies like cv2) not found: {e}")
            print("Skipping Step 2 (Resolution Check).")
        except Exception as e:
            print(f"Error in resolution check: {e}")

        # 3. Add Hashtags
        try:
            # cek_resolusi moves valid files to '1080x1920' folder usually
            # If step 2 failed/skipped, we might need to check the root output_directory too
            target_folder = os.path.join(output_directory, "1080x1920") 
            if not os.path.exists(target_folder):
                 # Fallback to root if subfolder doesn't exist
                 target_folder = output_directory
            
            if os.path.exists(target_folder):
                print(f"\n[Step 3/3] Adding Hashtags to files in {target_folder}...")
                import add_costume_hastag
                add_costume_hastag.process_hashtags(target_folder)
            else:
                print(f"\n[Step 3/3] Target folder {target_folder} not found. Skipping hashtags.")
        except ImportError:
             print("Module 'add_costume_hastag' not found. Skipping Step 3.")
        except Exception as e:
            print(f"Error adding hashtags: {e}")

        print("\n" + "="*55)
        print("ALL WORKFLOWS FINISHED SUCCESSFULLY!")
        print("="*55)

    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
    except Exception as e:
        print(f"\nUnexpected global error: {e}")

if __name__ == "__main__":
    main()
