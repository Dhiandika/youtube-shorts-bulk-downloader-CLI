import os

# Base Directories
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DOWNLOADS_DIR = os.path.join(BASE_DIR, 'downloads')

# Output Directories
SHORTS_DIR = os.path.join(DOWNLOADS_DIR, 'Shorts')
LONG_VIDEOS_DIR = os.path.join(DOWNLOADS_DIR, '_LongVideos')
REJECTED_DIR = os.path.join(DOWNLOADS_DIR, '_Rejected')
PLAN_B_DIR = os.path.join(SHORTS_DIR, '_PlanB_Rescued')

# File Paths
CHANNELS_FILE = os.path.join(BASE_DIR, 'channels.txt')
SCANNED_VIDEOS_FILE = os.path.join(BASE_DIR, 'scanned_videos.txt')
COOKIES_FILE = os.path.join(BASE_DIR, 'cookies.txt')
COOKIES_JSON_FILE = os.path.join(BASE_DIR, 'cookies.json')
ERROR_VIDEOS_FILE = os.path.join(BASE_DIR, 'video_error_list.txt')
ARCHIVE_FILE = os.path.join(BASE_DIR, 'downloaded_archive.txt')
REPORT_FILE = os.path.join(BASE_DIR, 'download_report.txt')

# Ensure directories exist
os.makedirs(SHORTS_DIR, exist_ok=True)
os.makedirs(LONG_VIDEOS_DIR, exist_ok=True)
os.makedirs(REJECTED_DIR, exist_ok=True)
os.makedirs(PLAN_B_DIR, exist_ok=True)

# Application configurations
TARGET_WIDTH = 1080
TARGET_HEIGHT = 1920
EXPECTED_ASPECT_RATIO = TARGET_WIDTH / TARGET_HEIGHT # 0.5625 (9:16)
ASPECT_RATIO_TOLERANCE = 0.05 # Allow slight variations
MAX_DURATION = 60 # Maximum allowed duration in seconds

# Threading Configurations
MAX_WORKERS = 5 # Number of concurrent downloads/scans. Keep low (3-5) to avoid Bilibili block.
COOLDOWN_SECONDS = 2 # Delay between consecutive thread dispatches to prevent spamming server
