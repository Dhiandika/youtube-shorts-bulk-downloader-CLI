import os
import json
from datetime import datetime
from .logger import logger
from .config import BASE_DIR

SCHEDULER_FILE = os.path.join(BASE_DIR, 'channel_last_scan.json')

def load_scheduler_db():
    if not os.path.exists(SCHEDULER_FILE):
        return {}
    try:
        with open(SCHEDULER_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to read scheduler DB at {SCHEDULER_FILE}: {e}")
        return {}

def save_scheduler_db(db):
    try:
        with open(SCHEDULER_FILE, 'w', encoding='utf-8') as f:
            json.dump(db, f, indent=4)
    except Exception as e:
        logger.error(f"Failed to save scheduler DB to {SCHEDULER_FILE}: {e}")

def get_last_scan_date(channel_url):
    """
    Returns the YYYYMMDD date string if it exists in the database,
    otherwise returns None.
    """
    db = load_scheduler_db()
    if channel_url in db:
        return db[channel_url].get("last_scan_date")
    return None

def update_last_scan_date(channel_url):
    """
    Updates the channel's last scan date to today's date (YYYYMMDD).
    """
    db = load_scheduler_db()
    today_str = datetime.now().strftime('%Y%m%d')
    
    if channel_url not in db:
        db[channel_url] = {}
        
    db[channel_url]["last_scan_date"] = today_str
    
    save_scheduler_db(db)
    logger.info(f"Updated scheduler DB: {channel_url} -> {today_str}")
