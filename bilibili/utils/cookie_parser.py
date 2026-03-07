import os
import json
from .logger import logger
from .config import COOKIES_FILE, COOKIES_JSON_FILE

def get_cookie_file():
    """
    Checks if a valid cookie file exists.
    If cookies.json exists, converts it to Netscape format cookies.txt.
    Returns the path to cookies.txt if valid, or None.
    """
    # Auto-convert cookies.json to cookies.txt if json is present
    if os.path.exists(COOKIES_JSON_FILE):
        logger.info(f"Found cookies.json. Converting to Netscape format as cookies.txt...")
        try:
            with open(COOKIES_JSON_FILE, 'r', encoding='utf-8') as jf:
                cookies_data = json.load(jf)
                
            with open(COOKIES_FILE, 'w', encoding='utf-8') as f:
                f.write("# Netscape HTTP Cookie File\n")
                f.write("# This file was automatically generated. Edit at your own risk.\n\n")
                
                for c in cookies_data:
                    domain = c.get('domain', '')
                    include_subdomains = 'TRUE' if domain.startswith('.') else 'FALSE'
                    path = c.get('path', '/')
                    secure = 'TRUE' if c.get('secure', False) else 'FALSE'
                    expiration = str(int(c.get('expirationDate', 0))) if c.get('expirationDate') else '0'
                    name = c.get('name', '')
                    value = c.get('value', '')
                    
                    f.write(f"{domain}\t{include_subdomains}\t{path}\t{secure}\t{expiration}\t{name}\t{value}\n")
                    
            logger.info("Successfully converted cookies.json to cookies.txt")
        except Exception as e:
            logger.error(f"Failed to convert cookies.json: {str(e)}")

    # Proceed if cookies.txt exists and is valid
    if os.path.exists(COOKIES_FILE):
        try:
            with open(COOKIES_FILE, 'r', encoding='utf-8') as f:
                first_line = f.readline()
                if "# Netscape HTTP Cookie File" in first_line:
                    logger.info(f"Valid Netscape cookies.txt found. Using it for yt-dlp.")
                    return COOKIES_FILE
                else:
                    logger.warning(f"cookies.txt is NOT in Netscape format. Please replace it or use cookies.json instead.")
                    return None
        except Exception as e:
            logger.error(f"Error reading cookies.txt: {str(e)}")
            return None
            
    return None
