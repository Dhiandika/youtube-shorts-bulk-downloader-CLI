import os
import re
import json
import subprocess
from .logger import logger
from .config import COOKIES_JSON_FILE, COOKIES_FILE
from .cookie_parser import get_cookie_file

def get_bilibili_channel_videos_fallback(channel_url):
    """
    Fallback method to fetch Bilibili channel videos using specialized yt-dlp subprocess 
    configured to evade Bilibili's Error 412 server blocks.
    """
    logger.info(f"Initiating Tactical yt-dlp Fallback Scanner for: {channel_url}")

    # Extract user ID (UID) from URL just in case we need it for logs
    match = re.search(r'space\.bilibili\.com/(\d+)', channel_url)
    channel_name = channel_url
    if match:
        channel_name = f"UID_{match.group(1)}"

    video_urls = []
    try:
        # We spawn a totally isolated yt-dlp instance with parameters to spoof an android client/slow down requests
        # --extractor-args "bilibili:player_client=android" or simply dumping flat JSON
        cmd = [
            'yt-dlp',
            '--flat-playlist',
            '--dump-json',
            '--extractor-retries', '5',
            '--sleep-requests', '0.5'
        ]
        
        cookie_path = get_cookie_file()
        if cookie_path:
            cmd.extend(['--cookies', cookie_path])
            
        cmd.append(channel_url)
        
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore')
        
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            for line in lines:
                if not line.strip(): continue
                try:
                    data = json.loads(line)
                    url = data.get('url') or data.get('webpage_url')
                    _id = data.get('id')
                    
                    if url:
                        video_urls.append(url)
                    elif _id:
                        video_urls.append(f"https://www.bilibili.com/video/{_id}")
                        
                    # Attempt to grab the channel name dynamically from the first video if possible
                    if channel_name.startswith("UID_") and data.get('uploader'):
                        channel_name = data.get('uploader')
                        
                except json.JSONDecodeError:
                    continue
                    
        else:
            logger.error(f"Tactical subprocess scanner also failed. Output: {result.stderr[:300]}")
            
    except Exception as e:
        logger.error(f"Tactical fallback crashed for {channel_url}: {str(e)}")
        
    if video_urls:
        logger.info(f"Tactical scanner successfully penetrated block: Found {len(video_urls)} videos for {channel_name}.")
    else:
        logger.warning(f"Tactical scanner found no videos (Block intact or channel empty).")
        
    return channel_name, video_urls
