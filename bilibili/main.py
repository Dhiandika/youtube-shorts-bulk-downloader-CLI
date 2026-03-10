import os
import sys
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add the directory containing this script to sys.path to ensure 'utils' can be imported
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import yt_dlp

from utils.logger import logger
from utils.config import (
    CHANNELS_FILE, SCANNED_VIDEOS_FILE, COOKIES_FILE, 
    ERROR_VIDEOS_FILE, REPORT_FILE, MAX_WORKERS, COOLDOWN_SECONDS
)
from utils.cookie_parser import get_cookie_file
from utils.downloader import process_video, download_plan_b_rescue, download_plan_c_rescue, is_video_in_archive
from utils.bili_api import get_bilibili_channel_videos_fallback
from utils.caption_tool import run_caption_customizer
from utils.scheduler import get_last_scan_date, update_last_scan_date

def get_channel_videos(channel_url):
    """
    Extracts video URLs from a given Bilibili channel/user URL.
    """
    logger.info(f"Scanning channel: {channel_url}")
    video_urls = []
    
    ydl_opts = {
        'extract_flat': 'in_playlist',
        'quiet': True,
        'no_warnings': True,
    }
    
    # Cookie Logic
    cookie_path = get_cookie_file()
    if cookie_path:
        ydl_opts['cookiefile'] = cookie_path
    else:
        logger.warning(f"No valid cookies provided! Continuing without cookies... (May trigger Error 352)")

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(channel_url, download=False)
            
            if info and 'entries' in info:
                for entry in info['entries']:
                    if entry.get('url'):
                        video_urls.append(entry['url'])
                    elif entry.get('id'):
                        # Construct Bilibili URL if only ID is available
                        video_urls.append(f"https://www.bilibili.com/video/{entry['id']}")
            else:
                logger.warning(f"No entries found for {channel_url}")
                
        logger.info(f"Found {len(video_urls)} videos in channel {channel_url} using yt-dlp.")
        
        channel_name = channel_url
        if info:
            channel_name = info.get('uploader') or info.get('title') or channel_url

        # If yt-dlp fails to extract videos (Error 352 or silent fail), trigger fallback
        if not video_urls:
            logger.warning(f"yt-dlp extracted no videos for {channel_url}. Attempting fallback API scraper...")
            channel_name, video_urls = get_bilibili_channel_videos_fallback(channel_url)

        return channel_name, video_urls

    except Exception as e:
        logger.error(f"Failed to scan channel {channel_url} with yt-dlp: {str(e)}")
        logger.info(f"Server Block or Error detected! Auto-falling back to native bilibili-api-python scanner...")
        return get_bilibili_channel_videos_fallback(channel_url)

def scan_channels():
    if not os.path.exists(CHANNELS_FILE):
        logger.error(f"Channels file not found at {CHANNELS_FILE}")
        return
        
    channels_to_scan = []
    with open(CHANNELS_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                channels_to_scan.append(line)

    if not channels_to_scan:
        logger.warning("No channels to scan in channels.txt.")
        return

    logger.info(f"Starting concurrent scan for {len(channels_to_scan)} channels using {MAX_WORKERS} workers...")
    all_scanned_data = []
    total_videos = 0
    
    def _scan_worker(channel_url):
        time.sleep(COOLDOWN_SECONDS) # Cooldown before starting work
        c_name, urls = get_channel_videos(channel_url)
        urls = list(dict.fromkeys(urls)) # remove duplicates
        
        # Pre-emptively filter out videos already in downloaded archive
        original_count = len(urls)
        urls = [u for u in urls if not is_video_in_archive(u)]
        if len(urls) < original_count:
            logger.info(f"Filtered {original_count - len(urls)} already downloaded videos from {c_name} scan results.")
            
        return c_name, urls

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_url = {executor.submit(_scan_worker, url): url for url in channels_to_scan}
        for future in as_completed(future_to_url):
            try:
                channel_name, urls = future.result()
                if urls:
                    all_scanned_data.append((channel_name, urls))
                    total_videos += len(urls)
            except Exception as e:
                logger.error(f"Scan worker failed: {e}")
            
    if all_scanned_data:
        with open(SCANNED_VIDEOS_FILE, 'w', encoding='utf-8') as f:
            for channel_name, urls in all_scanned_data:
                f.write(f"\n# === [ {channel_name} ] ===\n")
                for url in urls:
                    f.write(f"{url}\n")
        logger.info(f"Successfully saved {total_videos} video URLs to {SCANNED_VIDEOS_FILE}")
    else:
        logger.info("No videos found during scan.")

def download_scanned():
    if not os.path.exists(SCANNED_VIDEOS_FILE):
        logger.error(f"Scanned videos file not found at {SCANNED_VIDEOS_FILE}. Please run scan first.")
        return
        
    video_urls = []
    # Read mapped data so we know which video belongs to which channel
    # This helps Smart Scheduler set the correct DateAfter
    video_channel_map = {}
    current_channel = None
    with open(SCANNED_VIDEOS_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line.startswith('# === [') and line.endswith('] ==='):
                current_channel = line.replace('# === [', '').replace('] ===', '').strip()
            elif line and not line.startswith('#'):
                video_urls.append(line)
                if current_channel:
                    video_channel_map[line] = current_channel
                
    if not video_urls:
        logger.warning(f"No URLs found in {SCANNED_VIDEOS_FILE}.")
        return

    print("\n" + "="*40)
    print(" OPSI PENGUNDUHAN BATCH")
    print("="*40)
    print("[1] Download Semua Video dari Hasil Scan")
    print("[2] Download x Hari Terakhir (Custom Date)")
    print("[3] Update Cerdas (Smart Scheduler)")
    print("    -> Mengecek kapan terakhir channel diunduh, dan hanya mendownload video baru.")
    
    dl_choice = input("Pilih mode (1/2/3): ").strip()
    date_after = None
    use_smart_scheduler = False
    
    if dl_choice == '2':
        days_str = input("Masukkan jumlah hari ke belakang (contoh: 3): ").strip()
        try:
            days = int(days_str)
            if days > 0:
                # yt-dlp format is simply "today-xday"
                date_after = f"today-{days}days"
                logger.info(f"Custom date filter applied: Videos uploaded {days} days ago or newer.")
            else:
                print("Jumlah hari tidak valid, jatuh kembali ke Download Semua.")
        except ValueError:
            print("Input bukan angka, jatuh kembali ke Download Semua.")
            
    elif dl_choice == '3':
        logger.info("Smart Scheduler mode activated.")
        use_smart_scheduler = True
        
    logger.info(f"Starting concurrent download for {len(video_urls)} videos using {MAX_WORKERS} workers...")
    
    # Reset report file
    if os.path.exists(REPORT_FILE):
        os.remove(REPORT_FILE)
        
    failed_urls = []
    success_urls = []
    skipped_urls = []
    blacklisted_urls = []
    
    def _dl_worker(url, d_after, use_scheduler):
        time.sleep(COOLDOWN_SECONDS) # Add safe delay
        
        # If smart scheduler is strictly requested, we must find the channel URL that corresponds to this video.
        # However, video URLs don't explicitly contain the channel info natively before yt-dlp extracts info.
        # If smart scheduler is strictly requested, we have to look up the uploader ID. 
        # But wait, we can't efficiently map video URL -> channel URL without an API call, unless we pass down the channel context from scan...
        # Wait, SCANNED_VIDEOS_FILE has the channel name in the `# === [ Channel Name ] ===` headers!
        # This design needs the channel name mapping to video url.
        final_date_after = d_after
        channel_name = video_channel_map.get(url)
        
        if use_scheduler and channel_name:
            # We strictly use the Channel Name as the key in the JSON database for convenience
            last_date = get_last_scan_date(channel_name)
            if last_date:
                final_date_after = last_date
                logger.debug(f"Smart Scheduler: Using date {last_date} for {url} (Channel: {channel_name})")
                
        status = process_video(url, final_date_after)
        
        # Auto-Fallback logic for scanned videos
        if status == "error":
            logger.info(f"Main extractor (yt-dlp) failed for {url}. Auto-falling back to Plan C (BBDown)...")
            status = download_plan_c_rescue(url)
            if status == "error":
                logger.warning(f"Plan C (BBDown) failed for {url}. Auto-falling back to Plan B (you-get) as last resort...")
                status = download_plan_b_rescue(url)
                
        return url, status, channel_name

    # Print base report structure once
    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        f.write("=== BILIBILI LIVE DOWNLOAD REPORT ===\n")
        f.write("Status updates progressively...\n\n")

    def _update_live_report():
        # Rewrites the report live
        with open(REPORT_FILE, 'w', encoding='utf-8') as f:
            f.write("=== BILIBILI LIVE DOWNLOAD REPORT ===\n\n")
            f.write(f"Total Processed: {len(success_urls) + len(skipped_urls) + len(failed_urls) + len(blacklisted_urls)} / {len(video_urls)}\n")
            f.write(f"Successful: {len(success_urls)}\n")
            f.write(f"Skipped (Date Filter): {len(skipped_urls)}\n")
            f.write(f"Failed: {len(failed_urls)}\n\n")
            f.write(f"Untuk melihat daftar tautan video yang gagal (Error), silakan buka file: {os.path.basename(ERROR_VIDEOS_FILE)}\n")
                
    def _append_to_error_file(url):
        # We check for existence so we don't write duplicates if ran multiple times
        existing = []
        if os.path.exists(ERROR_VIDEOS_FILE):
            with open(ERROR_VIDEOS_FILE, 'r', encoding='utf-8') as f:
                existing = [line.strip() for line in f if line.strip()]
        if url not in existing:
            with open(ERROR_VIDEOS_FILE, 'a', encoding='utf-8') as f:
                f.write(f"{url}\n")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_url = {executor.submit(_dl_worker, url, date_after, use_smart_scheduler): url for url in video_urls}
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                ret_url, status, ret_channel = future.result()
                if status == "success":
                    logger.info(f"Finished processing: {ret_url}")
                    success_urls.append(ret_url)
                    if use_smart_scheduler and ret_channel:
                        update_last_scan_date(ret_channel)
                elif status == "skipped_duration":
                    logger.info(f"Skipped due to duration constraints: {ret_url}")
                    skipped_urls.append(ret_url)
                elif status == "skipped_date":
                    logger.info(f"Skipped due to date filter: {ret_url}")
                    skipped_urls.append(ret_url)
                elif status == "blacklisted_duration":
                    logger.info(f"Permanently blacklisted natively due to duration constraints: {ret_url}")
                    blacklisted_urls.append(ret_url)
                else:
                    logger.error(f"Failed to process: {ret_url}. Directly saving to error file.")
                    failed_urls.append(ret_url)
                    _append_to_error_file(ret_url)
            except Exception as e:
                logger.error(f"Download worker crashed for {url}: {e}")
                failed_urls.append(url)
                _append_to_error_file(url)
                
            # Live write the report after every single completion
            _update_live_report()
            
    logger.info("All downloads completed.")
    
    if failed_urls:
        logger.info("Memulai Tahap 2: Mencoba ulang otomatis video yang gagal di Tahap 1...")
        retry_failed_downloads(is_auto_stage_2=True)

def retry_failed_downloads(is_auto_stage_2=False):
    if not os.path.exists(ERROR_VIDEOS_FILE):
        logger.info(f"No error file found at {ERROR_VIDEOS_FILE}. Nothing to retry.")
        return
        
    error_urls = []
    with open(ERROR_VIDEOS_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            url = line.strip()
            if url:
                error_urls.append(url)
                
    if not error_urls:
        logger.info(f"No failed URLs found in {ERROR_VIDEOS_FILE}.")
        return

    use_plan_b = False
    use_plan_c = False
    if not is_auto_stage_2:
        print("\n" + "="*40)
        print(" OPSI RETRY (Coba Ulang)")
        print("="*40)
        print("[1] Retry Normal (Sistem Utama yt-dlp)")
        print("    -> Untuk error koneksi sementara putus.")
        print("[2] Darurat: Gunakan Plan C (Sistem BBDown - REKOMENDASI TERBAIK)")
        print("    -> Cepat, akurat, dan sangat tahan banting untuk Bilibili.")
        print("[3] Darurat: Gunakan Plan B (Sistem you-get)")
        print("    -> Scraping kasar, opsi terakhir jika semuanya gagal.")
        
        r_choice = input("Pilih mode (1/2/3): ").strip()
        if r_choice == '2':
            use_plan_c = True
            logger.info("Plan C (BBDown Rescue) activated for Retries.")
        elif r_choice == '3':
            use_plan_b = True
            logger.info("Plan B (you-get Rescue) activated for Retries.")

    logger.info(f"Starting retry for {len(error_urls)} failed videos...")
    
    still_failed_urls = []
    success_urls = []
    skipped_urls = []
    
    for url in error_urls:
        if use_plan_c:
            status = download_plan_c_rescue(url)
        elif use_plan_b:
            status = download_plan_b_rescue(url)
        else:
            status = process_video(url)
        if status == "success":
            logger.info(f"Successfully retried and downloaded: {url}")
            success_urls.append(url)
        elif status == "skipped_duration":
            logger.info(f"Retry skipped due to max duration config: {url}")
            skipped_urls.append(url)
        elif status == "blacklisted_duration":
            logger.info(f"Retry inherently blocked: Video is permanently blacklisted for oversize: {url}")
            # Do NOT add to still_failed_urls so it is removed from ERROR_VIDEOS_FILE.
            pass
        else:
            if is_auto_stage_2:
                logger.error(f"ERROR TAHAP 2 (Persistent Failure) untuk: {url}")
            else:
                logger.error(f"Retry failed again for: {url}")
            still_failed_urls.append(url)
            
    # Always rewrite the error file with what's still failing (plus duration skips if they're fundamentally unsupported)
    # Actually, we should probably remove skipped items from the error list since they aren't "errors".
    if still_failed_urls:
        with open(ERROR_VIDEOS_FILE, 'w', encoding='utf-8') as f:
            for url in still_failed_urls:
                f.write(f"{url}\n")
        logger.warning(f"{len(still_failed_urls)} videos still failed and remain in {ERROR_VIDEOS_FILE}")
    else:
        open(ERROR_VIDEOS_FILE, 'w').close()
        logger.info(f"All retries resolved! (Success: {len(success_urls)}, Skipped: {len(skipped_urls)}). Cleared {ERROR_VIDEOS_FILE}")

def interactive_config_editor():
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'utils', 'config.py')
    if not os.path.exists(config_path):
        print("[!] config.py tidak ditemukan!")
        return
        
    with open(config_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Extract current
    mw_match = re.search(r'MAX_WORKERS\s*=\s*(\d+)', content)
    md_match = re.search(r'MAX_DURATION\s*=\s*(\d+)', content)
    
    current_mw = mw_match.group(1) if mw_match else "3"
    current_md = md_match.group(1) if md_match else "60"
    
    print("\n" + "="*40)
    print(" PENGATURAN CONFIG")
    print("="*40)
    print(f"1. MAX_WORKERS (Paralel / Utas)     = {current_mw} (Default: 3, Hindari > 5)\n2. MAX_DURATION (Batas Detik Video) = {current_md} (Default: 60)")
    
    print("\nMasukkan opsi nomor yang ingin diubah, atau '0' untuk BATAL")
    choice = input("Pilihan: ").strip()
    
    if choice == '1':
        val = input("Masukkan angka MAX_WORKERS baru: ").strip()
        if val.isdigit():
            content = re.sub(r'(MAX_WORKERS\s*=\s*)\d+', fr'\g<1>{val}', content)
            print(f"[+] Berhasil mengubah MAX_WORKERS menjadi {val}!")
        else:
            print("[!] Angka tidak valid.")
            
    elif choice == '2':
        val = input("Masukkan angka MAX_DURATION baru (detik): ").strip()
        if val.isdigit():
            content = re.sub(r'(MAX_DURATION\s*=\s*)\d+', fr'\g<1>{val}', content)
            print(f"[+] Berhasil mengubah MAX_DURATION menjadi {val} detik!")
        else:
            print("[!] Angka tidak valid.")
    else:
        return
        
    with open(config_path, 'w', encoding='utf-8') as f:
        f.write(content)
        
def auto_cleanup():
    print("\n" + "="*40)
    print(" BERSIHKAN FILE SEMENTARA & LOGS")
    print("="*40)
    files_to_check = [SCANNED_VIDEOS_FILE, ERROR_VIDEOS_FILE, REPORT_FILE]
    
    count = 0
    for file_path in files_to_check:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                print(f"[-] Menghapus: {os.path.basename(file_path)}")
                count += 1
            except Exception as e:
                print(f"[!] Gagal menghapus {os.path.basename(file_path)}: {e}")
                
    if count == 0:
        print("[*] Ruang kerja sudah bersih. Tidak ada file sampah.")
    else:
        print(f"[+] Berhasil menghapus {count} file sementara/laporan.")

def main():
    while True:
        print("\n" + "="*40)
        print(" Bilibili Shorts Downloader CLI")
        print("="*40)
        print("1. Scan Channels (from channels.txt)")
        print("2. Download Scanned Videos (from scanned_videos.txt)")
        print("3. Customize Captions for Downloaded Shorts")
        print("4. Retry Failed Downloads (from video_error_list.txt)")
        print("5. Pengaturan (Interactive Config Editor)")
        print("6. Auto-Cleanup (Hapus Sampah/Log)")
        print("7. Exit")
        print("="*40)
        
        choice = input("Select an option (1-7): ").strip()
        
        if choice == '1':
            scan_channels()
        elif choice == '2':
            download_scanned()
        elif choice == '3':
            run_caption_customizer()
        elif choice == '4':
            retry_failed_downloads()
        elif choice == '5':
            interactive_config_editor()
        elif choice == '6':
            auto_cleanup()
        elif choice == '7':
            print("Exiting...")
            break
        else:
            print("Invalid choice. Please try again.")

if __name__ == "__main__":
    main()
