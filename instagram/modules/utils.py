import time
import random
import re
import os
import datetime
from colorama import Fore, Style
from ..settings import SLEEP_RANGE, DOWNLOAD_DIR

def smart_sleep(logger=None):
    """Sleep for a random amount of time to avoid detection."""
    duration = random.uniform(*SLEEP_RANGE)
    if logger:
        logger.info(f"{Fore.CYAN}Sleeping for {duration:.2f} seconds...{Style.RESET_ALL}")
    else:
        print(f"Sleeping for {duration:.2f} seconds...")
    time.sleep(duration)

def parse_date(date_str):
    """Parse a date string (YYYY-MM-DD) into a datetime object."""
    try:
        if not date_str:
            return None
        return datetime.datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return None

def extract_shortcode(url):
    """Extract shortcode from an Instagram URL."""
    # Matches /p/SHORTCODE, /reel/SHORTCODE, /tv/SHORTCODE
    match = re.search(r'instagram\.com/(?:p|reel|tv)/([A-Za-z0-9_-]+)', url)
    if match:
        return match.group(1)
    return None

def extract_username_from_input(input_str):
    """
    Extract clean username from input string.
    Supports:
    - just_username
    - @just_username
    - https://www.instagram.com/just_username/
    - https://instagram.com/just_username
    """
    if not input_str:
        return None
    
    # Remove @ prefix
    clean = input_str.strip().replace('@', '')
    
    # Lowercase for domain check
    lower_clean = clean.lower()
    
    # Check if URL
    if 'instagram.com' in lower_clean:
        # standard url: instagram.com/username/...
        # Remove query params
        clean_no_query = clean.split('?')[0]
        # Remove trailing slash
        clean_no_slash = clean_no_query.rstrip('/')
        # Get last part
        parts = clean_no_slash.split('/')
        username = parts[-1]
        
        return clean_filename(username)
    
    # If not URL, assume it's a username
    return clean_filename(clean)

def clean_filename(text):
    """Sanitize a string to be used as a filename."""
    # Basic sanitization
    return re.sub(r'[<>:"/\\|?*]', '', text).strip()[:100]

def organize_file(filepath, target_dir):
    """Move a file to a target directory, handling existence."""
    if not os.path.exists(filepath):
        return None
    
    filename = os.path.basename(filepath)
    target_path = os.path.join(target_dir, filename)
    
    os.makedirs(target_dir, exist_ok=True)
    
    # If exists, maybe rename? For now, we overwrite or skip? 
    # Instaloader handles downloads, this might be for post-processing
    # But we will let Instaloader save directly to the target folder usually.
    # This is just a helper if we need manual moving.
    try:
        os.rename(filepath, target_path)
        return target_path
    except Exception as e:
        print(f"Error moving file: {e}")
        return None
