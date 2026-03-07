import os
import sys

# Add the directory containing this script to sys.path to ensure 'utils' can be imported
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import yt_dlp

from utils.logger import logger
from utils.config import CHANNELS_FILE, SCANNED_VIDEOS_FILE, COOKIES_FILE
from utils.cookie_parser import get_cookie_file
from utils.downloader import process_video
from utils.bili_api import get_bilibili_channel_videos_fallback
from utils.caption_tool import run_caption_customizer

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
        
        # If yt-dlp fails to extract videos (Error 352 or silent fail), trigger fallback
        if not video_urls:
            logger.warning(f"yt-dlp extracted no videos for {channel_url}. Attempting fallback API scraper...")
            video_urls = get_bilibili_channel_videos_fallback(channel_url)

        return video_urls

    except Exception as e:
        logger.error(f"Failed to scan channel {channel_url} with yt-dlp: {str(e)}")
        logger.info(f"Attempting fallback API scraper due to exception...")
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

    logger.info(f"Starting scan for {len(channels_to_scan)} channels...")
    all_video_urls = []
    
    for channel_url in channels_to_scan:
        urls = get_channel_videos(channel_url)
        all_video_urls.extend(urls)
        
    # Remove duplicates
    all_video_urls = list(dict.fromkeys(all_video_urls))
        
    if all_video_urls:
        with open(SCANNED_VIDEOS_FILE, 'w', encoding='utf-8') as f:
            for url in all_video_urls:
                f.write(f"{url}\n")
        logger.info(f"Successfully saved {len(all_video_urls)} video URLs to {SCANNED_VIDEOS_FILE}")
    else:
        logger.info("No videos found during scan.")

def download_scanned():
    if not os.path.exists(SCANNED_VIDEOS_FILE):
        logger.error(f"Scanned videos file not found at {SCANNED_VIDEOS_FILE}. Please run scan first.")
        return
        
    video_urls = []
    with open(SCANNED_VIDEOS_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            url = line.strip()
            if url:
                video_urls.append(url)
                
    if not video_urls:
        logger.warning(f"No URLs found in {SCANNED_VIDEOS_FILE}.")
        return

    logger.info(f"Starting download for {len(video_urls)} videos...")
    
    for url in video_urls:
        success = process_video(url)
        if success:
            logger.info(f"Finished processing: {url}")
            
    logger.info("All downloads completed.")

def main():
    while True:
        print("\n" + "="*40)
        print(" Bilibili Shorts Downloader CLI")
        print("="*40)
        print("1. Scan Channels (from channels.txt)")
        print("2. Download Scanned Videos (from scanned_videos.txt)")
        print("3. Customize Captions for Downloaded Shorts")
        print("4. Exit")
        print("="*40)
        
        choice = input("Select an option (1/2/3/4): ").strip()
        
        if choice == '1':
            scan_channels()
        elif choice == '2':
            download_scanned()
        elif choice == '3':
            run_caption_customizer()
        elif choice == '4':
            print("Exiting...")
            break
        else:
            print("Invalid choice. Please try again.")

if __name__ == "__main__":
    main()
