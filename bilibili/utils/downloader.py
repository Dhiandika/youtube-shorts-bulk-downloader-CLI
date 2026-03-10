import os
import json
import subprocess
import glob
import re
import yt_dlp
from .logger import logger
from .config import (
    SHORTS_DIR, LONG_VIDEOS_DIR, REJECTED_DIR, PLAN_B_DIR,
    EXPECTED_ASPECT_RATIO, ASPECT_RATIO_TOLERANCE, COOKIES_FILE, ARCHIVE_FILE, MAX_DURATION
)
from .cookie_parser import get_cookie_file

def is_vertical_video(width, height):
    """
    Check if a video is vertical (approx 9:16).
    """
    if not width or not height or height == 0:
        return False
    
    aspect_ratio = width / height
    
    # Check if aspect ratio is roughly 9:16
    if abs(aspect_ratio - EXPECTED_ASPECT_RATIO) <= ASPECT_RATIO_TOLERANCE:
        # Also check if it's 1080x1920 or higher ideally
        return True
    
    return False

def cleanup_temp_files(output_dir):
    """
    Removes lingering intermittent/garbage files created by interrupted yt-dlp downloads.
    """
    extensions = ['*.part', '*.ytdl', '*.cmt.xml']
    for ext in extensions:
        for file_path in glob.glob(os.path.join(output_dir, ext)):
            try:
                os.remove(file_path)
                logger.debug(f"Auto-Cleanup: Removed temp file {os.path.basename(file_path)}")
            except Exception as e:
                logger.warning(f"Auto-Cleanup: Failed to remove {file_path}. Error: {e}")

def download_with_you_get(video_url, output_dir, file_name):
    """
    Fallback method using you-get.
    """
    try:
        logger.info(f"Attempting fallback download with you-get for {video_url}")
        output_path = os.path.join(output_dir, file_name)
        
        # you-get command
        # -o for output dir, -O for output filename (without extension)
        base_name = os.path.splitext(file_name)[0]
        cmd = ['you-get', '-o', output_dir, '-O', base_name]
        
        cookie_path = get_cookie_file()
        if cookie_path:
            cmd.extend(['-c', cookie_path])
            
        cmd.append(video_url)
        
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore')
        
        if result.returncode == 0:
            logger.info(f"Successfully downloaded with you-get: {file_name}")
            return True
        else:
            logger.error(f"you-get failed for {video_url}. Error: {result.stderr}")
            return False
            
    except Exception as e:
        logger.error(f"Exception during you-get fallback for {video_url}: {str(e)}")
        return False

def is_video_in_archive(video_url):
    """
    Checks if a video was already downloaded by parsing its BV ID against the central yt-dlp archive.
    """
    import os
    match = re.search(r'video/(BV[a-zA-Z0-9]+)', video_url)
    if not match:
        return False
        
    video_id = match.group(1)
    if not os.path.exists(ARCHIVE_FILE):
        return False
        
    with open(ARCHIVE_FILE, 'r', encoding='utf-8') as f:
        content = f.read()
        if f"bilibili {video_id}" in content:
            return True
            
    return False

def mark_video_in_archive(video_url):
    """
    Manually appends a video to the yt-dlp downloaded_archive.txt.
    Useful for permanently blacklisting videos that exceed MAX_DURATION.
    """
    match = re.search(r'video/(BV[a-zA-Z0-9]+)', video_url)
    if match:
        video_id = match.group(1)
        try:
            with open(ARCHIVE_FILE, 'a', encoding='utf-8') as f:
                f.write(f"bilibili {video_id}\n")
        except Exception as e:
            logger.warning(f"Could not append to archive: {e}")

def is_video_too_long(video_url):
    """
    Directly queries Bilibili's public API to retrieve video duration in seconds.
    If it exceeds MAX_DURATION, returns True. Helps rescue scrapers avoid downloading movies.
    """
    import urllib.request
    match = re.search(r'video/(BV[a-zA-Z0-9]+)', video_url)
    if not match:
        return False
        
    bvid = match.group(1)
    api_url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
    
    try:
        req = urllib.request.Request(api_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            if data.get('code') == 0:
                duration_seconds = data.get('data', {}).get('duration', 0)
                if duration_seconds > MAX_DURATION:
                    logger.warning(f"Video {bvid} duration ({duration_seconds}s) exceeds MAX_DURATION ({MAX_DURATION}s). Blacklisting.")
                    mark_video_in_archive(video_url)
                    return True
    except Exception as e:
        logger.warning(f"Could not verify length for {bvid} via BiliAPI: {e}")
        
    return False

def download_plan_b_rescue(video_url):
    """
    Emergency fallback method using you-get. Disregards normal resolution parsing 
    and drops directly into the Rescue folder.
    """
    if is_video_in_archive(video_url):
        logger.info(f"Video {video_url} is already in the archive. Skipping Plan B.")
        return "success"
        
    if is_video_too_long(video_url):
        logger.info(f"Rescue aborted: Video exceeds MAX_DURATION limit. Blacklisted.")
        return "blacklisted_duration"
        
    logger.info(f"Initiating Plan B you-get Rescue for: {video_url}")
    
    try:
        # you-get automatically downloads the highest quality. We don't specify -O so it uses video title.
        cmd = ['you-get', '-o', PLAN_B_DIR]
        cookie_path = get_cookie_file()
        if cookie_path:
            cmd.extend(['-c', cookie_path])
            
        cmd.append(video_url)
        
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore')
        
        if result.returncode == 0:
            logger.info(f"Plan B Successful: {video_url}")
            
            # Since we bypassed yt-dlp, manually append to the archive to prevent duplicates
            mark_video_in_archive(video_url)
                    
            return "success"
        else:
            logger.error(f"Plan B you-get failed for {video_url}. Error: {result.stderr}")
            return "error"
            
    except Exception as e:
        logger.error(f"Exception during Plan B rescue for {video_url}: {str(e)}")
        return "error"

def download_plan_c_rescue(video_url):
    """
    Ultimate fallback method using BBDown, a dedicated Bilibili Downloader.
    """
    if is_video_in_archive(video_url):
        logger.info(f"Video {video_url} is already in the archive. Skipping Plan C.")
        return "success"
        
    if is_video_too_long(video_url):
        logger.info(f"Rescue aborted: Video exceeds MAX_DURATION limit. Blacklisted.")
        return "blacklisted_duration"
        
    logger.info(f"Initiating Plan C BBDown Rescue for: {video_url}")
    
    try:
        # BBDown command, outputting to PLAN_B_DIR workspace
        cmd = ['BBDown', '--work-dir', PLAN_B_DIR]
        cmd.append(video_url)
        
        # BBDown handles its own TV login via QR if no cookies, but works best out of the box for free content
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore')
        
        if result.returncode == 0:
            logger.info(f"Plan C BBDown Successful: {video_url}")
            # Mark manually archive
            mark_video_in_archive(video_url)
                    
            return "success"
        else:
            logger.error(f"Plan C BBDown failed for {video_url}. Error: {result.stderr}")
            return "error"
            
    except Exception as e:
        logger.error(f"Exception during Plan C rescue for {video_url}: {str(e)}")
        return "error"

def process_video(video_url, date_after=None):
    """
    Extract video info, check aspect ratio/duration, date filter, and download if criteria met.
    Returns: 'success', 'error', 'skipped_duration', or 'skipped_date'
    """
    if is_video_in_archive(video_url):
        logger.info(f"Video {video_url} is already in the archive. Skipping yt-dlp processing.")
        return "success"
        
    logger.info(f"Processing video: {video_url}")
    
    ydl_opts_info = {
        'skip_download': True,
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False, # We need full info for width/height
    }
    
    if date_after:
        ydl_opts_info['dateafter'] = date_after
    
    cookie_path = get_cookie_file()
    if cookie_path:
        ydl_opts_info['cookiefile'] = cookie_path

    try:
        with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
            info = ydl.extract_info(video_url, download=False)
            
            # Check if video was filtered out by date plugin natively before throwing error
            # If so, info dictionary won't have the normal fields appropriately, but usually it raises an exception "Video date is smaller than..."
            # Alternatively, we can let yt-dlp download handle it. yt-dlp normally skips it smoothly but returns info as None if filtered.
            if info is None:
                logger.warning(f"Video {video_url} skipped by yt-dlp date filter.")
                return "skipped_date"
                
            title = info.get('title', 'Unknown Title')
            width = info.get('width')
            height = info.get('height')
            duration = info.get('duration', 0)
            ext = info.get('ext', 'mp4')
            video_id = info.get('id', 'unknown_id')
            uploader = info.get('uploader', 'unknown_uploader')
            
            # Sanitize filename
            safe_title = "".join([c for c in title if c.isalpha() or c.isdigit() or c==' ']).rstrip()
            file_name = f"{uploader}_{video_id}_{safe_title}.{ext}"
            
            logger.debug(f"Video Data - ID: {video_id}, Title: {title}, Width: {width}, Height: {height}, Duration: {duration}s")

            if not width or not height:
                logger.warning(f"Could not determine dimensions for {video_url}. Skipping.")
                return "error"
                
            if duration and duration > MAX_DURATION:
                logger.warning(f"Video duration ({duration}s) exceeds MAX_DURATION ({MAX_DURATION}s). Blacklisting {video_url}.")
                mark_video_in_archive(video_url)
                return "blacklisted_duration"

            if is_vertical_video(width, height):
                logger.info(f"Vertical video detected (9:16). Dimensions: {width}x{height}")
                base_dir = SHORTS_DIR
                is_short = True
            else:
                logger.info(f"Horizontal/Long video detected. Dimensions: {width}x{height}")
                base_dir = LONG_VIDEOS_DIR
                is_short = False

            # Create Resolution Subfolder (e.g., 1080p, 720p)
            res_folder = f"{height}p" if height else "Unknown"
            output_dir = os.path.join(base_dir, uploader, res_folder)

            os.makedirs(output_dir, exist_ok=True)

            # Determine Sequence Number based on existing files in the directory
            # Count the existing `.mp4` or `.txt` files to assign the next number
            existing_files = [f for f in os.listdir(output_dir) if f.endswith('.mp4')]
            seq_num = len(existing_files) + 1
            
            # Format: 001 - Title - Uploader.mp4
            numbered_title = f"{seq_num:03d} - {safe_title} - {uploader}"
            
            # Primary download attempt with yt-dlp
            output_template = os.path.join(output_dir, f"{numbered_title}.%(ext)s")
            
            ydl_opts_download = {
                'format': 'bestvideo[width<=1080][height<=1920]+bestaudio/best[width<=1080][height<=1920]/best',
                'outtmpl': output_template,
                'quiet': False,
                'no_warnings': True,
                'download_archive': ARCHIVE_FILE
            }
            if date_after:
                ydl_opts_download['dateafter'] = date_after
                
            if cookie_path:
                ydl_opts_download['cookiefile'] = cookie_path

            # Create Caption .txt File
            txt_path = os.path.join(output_dir, f"{numbered_title}.txt")
            tags = " ".join([f"#{t}" for t in info.get('tags', [])]) if info.get('tags') else ""
            
            # Format according to user template
            caption_content = f"{title}\n\nBilibili: {uploader}\nLink: {video_url}\n\n{tags}\n"

            try:
                # Write caption file first
                with open(txt_path, 'w', encoding='utf-8') as f:
                    f.write(caption_content)
                logger.info(f"Generated caption file: {txt_path}")
                
                logger.info(f"Downloading with yt-dlp to {output_dir}")
                
                try:
                    with yt_dlp.YoutubeDL(ydl_opts_download) as ydl_dl:
                        ydl_dl.download([video_url])
                except Exception as dl_e:
                    error_msg = str(dl_e).lower()
                    if "premium member" in error_msg or "format(s)" in error_msg:
                        logger.warning(f"Premium Format Error for {video_url}. Downgrading resolution to highest free available and retrying...")
                        
                        # Fallback Format String (Limit to 30fps to avoid 60fps premium locks, or step down to 720p)
                        ydl_opts_download['format'] = 'bestvideo[height<=1080][fps<=30]+bestaudio / bestvideo[height<=720]+bestaudio / best'
                        
                        with yt_dlp.YoutubeDL(ydl_opts_download) as ydl_dl_fallback:
                            ydl_dl_fallback.download([video_url])
                    else:
                        raise dl_e # Re-raise if it's unrelated to premium formats
                        
                logger.info(f"Successfully downloaded {video_url} with yt-dlp")
                cleanup_temp_files(output_dir)
                return "success"
                
            except Exception as e:
                logger.error(f"yt-dlp download failed for {video_url}: {str(e)}")
                # Try fallback
                fallback_success = download_with_you_get(video_url, output_dir, file_name)
                cleanup_temp_files(output_dir)
                return "success" if fallback_success else "error"

    except Exception as e:
        logger.error(f"Failed to process video {video_url} with yt-dlp: {str(e)}")
        return "error"
