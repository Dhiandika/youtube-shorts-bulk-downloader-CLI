import os
import re
import json
import asyncio
from bilibili_api import user as bili_user, sync, Credential
from .logger import logger
from .config import COOKIES_JSON_FILE

def load_credential_from_json():
    """
    Load SESSDATA, bili_jct, buvid3, DedeUserID from cookies.json
    Return Credential object or None
    """
    if not os.path.exists(COOKIES_JSON_FILE):
        return None
        
    sessdata = ""
    bili_jct = ""
    buvid3 = ""
    dedeuserid = ""
    
    try:
        with open(COOKIES_JSON_FILE, 'r', encoding='utf-8') as f:
            cookies = json.load(f)
            for c in cookies:
                name = c.get('name', '')
                val = c.get('value', '')
                if name == 'SESSDATA': sessdata = val
                elif name == 'bili_jct': bili_jct = val
                elif name == 'buvid3': buvid3 = val
                elif name == 'DedeUserID': dedeuserid = val
                
        if sessdata or bili_jct:
            return Credential(sessdata=sessdata, bili_jct=bili_jct, buvid3=buvid3, dedeuserid=dedeuserid)
    except Exception as e:
        logger.error(f"Failed to load credentials from {COOKIES_JSON_FILE}: {e}")
        
    return None

async def fetch_videos_async(uid, credential_obj):
    u = bili_user.User(uid=uid, credential=credential_obj)
    
    video_urls = []
    page = 1
    
    # Fetch the first page of videos from the user's space
    try:
        res = await u.get_videos(pn=page)
        vlist = res.get('list', {}).get('vlist', [])
        
        for v in vlist:
            bvid = v.get('bvid')
            if bvid:
                video_urls.append(f"https://www.bilibili.com/video/{bvid}")
    except Exception as e:
        logger.error(f"bilibili-api-python fetching failed: {e}")
        raise e
        
    return video_urls

def get_bilibili_channel_videos_fallback(channel_url):
    """
    Fallback method to fetch Bilibili channel videos using bilibili-api-python.
    """
    logger.info(f"Using bilibili-api-python fallback to scan channel: {channel_url}")

    # Extract user ID (UID) from URL
    match = re.search(r'space\.bilibili\.com/(\d+)', channel_url)
    if not match:
        logger.error(f"Could not extract UID from URL: {channel_url}")
        return []

    uid = int(match.group(1))
    
    credential = load_credential_from_json()
    if credential:
        logger.info("Found bilibili-api credentials inside cookies.json. Authenticating scanner...")
    else:
        logger.warning(f"No cookies.json found at {COOKIES_JSON_FILE}. Scanning channel anonymously (may fail with -400)...")
        
    try:
        # Run async function synchronously
        urls = sync(fetch_videos_async(uid, credential))
        logger.info(f"bilibili-api scanner found {len(urls)} videos.")
        return urls
    except Exception as e:
        logger.error(f"Fallback bilibili-api scraper failed for {channel_url}: {str(e)}")
        return []
