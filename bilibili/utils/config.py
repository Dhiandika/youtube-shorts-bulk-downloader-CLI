import os

# Base Directories
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DOWNLOADS_DIR = os.path.join(BASE_DIR, 'downloads')

# Output Directories
SHORTS_DIR = os.path.join(DOWNLOADS_DIR, 'Shorts')
LONG_VIDEOS_DIR = os.path.join(DOWNLOADS_DIR, '_LongVideos')
REJECTED_DIR = os.path.join(DOWNLOADS_DIR, '_Rejected')

# File Paths
CHANNELS_FILE = os.path.join(BASE_DIR, 'channels.txt')
SCANNED_VIDEOS_FILE = os.path.join(BASE_DIR, 'scanned_videos.txt')
COOKIES_FILE = os.path.join(BASE_DIR, 'cookies.txt')
COOKIES_JSON_FILE = os.path.join(BASE_DIR, 'cookies.json')

# Ensure directories exist
os.makedirs(SHORTS_DIR, exist_ok=True)
os.makedirs(LONG_VIDEOS_DIR, exist_ok=True)
os.makedirs(REJECTED_DIR, exist_ok=True)

# Application configurations
TARGET_WIDTH = 1080
TARGET_HEIGHT = 1920
EXPECTED_ASPECT_RATIO = TARGET_WIDTH / TARGET_HEIGHT # 0.5625 (9:16)
ASPECT_RATIO_TOLERANCE = 0.05 # Allow slight variations
