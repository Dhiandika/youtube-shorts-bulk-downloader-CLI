import os
import json
import subprocess
import yt_dlp
from .logger import logger
from .config import (
    SHORTS_DIR, LONG_VIDEOS_DIR, REJECTED_DIR,
    EXPECTED_ASPECT_RATIO, ASPECT_RATIO_TOLERANCE, COOKIES_FILE
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
        cmd = ['you-get', '-o', output_dir, '-O', base_name, video_url]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info(f"Successfully downloaded with you-get: {file_name}")
            return True
        else:
            logger.error(f"you-get failed for {video_url}. Error: {result.stderr}")
            return False
            
    except Exception as e:
        logger.error(f"Exception during you-get fallback for {video_url}: {str(e)}")
        return False

def process_video(video_url):
    """
    Extract video info, check aspect ratio, and download if criteria met.
    """
    logger.info(f"Processing video: {video_url}")
    
    ydl_opts_info = {
        'skip_download': True,
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False, # We need full info for width/height
    }
    
    cookie_path = get_cookie_file()
    if cookie_path:
        ydl_opts_info['cookiefile'] = cookie_path

    try:
        with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
            info = ydl.extract_info(video_url, download=False)
            
            title = info.get('title', 'Unknown Title')
            width = info.get('width')
            height = info.get('height')
            ext = info.get('ext', 'mp4')
            video_id = info.get('id', 'unknown_id')
            uploader = info.get('uploader', 'unknown_uploader')
            
            # Sanitize filename
            safe_title = "".join([c for c in title if c.isalpha() or c.isdigit() or c==' ']).rstrip()
            file_name = f"{uploader}_{video_id}_{safe_title}.{ext}"
            
            logger.debug(f"Video Data - ID: {video_id}, Title: {title}, Width: {width}, Height: {height}")

            if not width or not height:
                logger.warning(f"Could not determine dimensions for {video_url}. Skipping.")
                return False

            if is_vertical_video(width, height):
                logger.info(f"Vertical video detected (9:16). Dimensions: {width}x{height}")
                output_dir = os.path.join(SHORTS_DIR, uploader)
                is_short = True
            else:
                logger.info(f"Horizontal/Long video detected. Dimensions: {width}x{height}")
                output_dir = os.path.join(LONG_VIDEOS_DIR, uploader)
                is_short = False

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
            }
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
                with yt_dlp.YoutubeDL(ydl_opts_download) as ydl_dl:
                    ydl_dl.download([video_url])
                logger.info(f"Successfully downloaded {video_url} with yt-dlp")
                return True
            except Exception as e:
                logger.error(f"yt-dlp download failed for {video_url}: {str(e)}")
                # Try fallback
                return download_with_you_get(video_url, output_dir, file_name)

    except Exception as e:
        logger.error(f"Failed to process video {video_url} with yt-dlp: {str(e)}")
        return False
