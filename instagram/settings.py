import os

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Download folder: instagram/instagram_downloads
DOWNLOAD_DIR = os.path.join(BASE_DIR, "instagram_downloads")
LOG_DIR = os.path.join(BASE_DIR, "logs")
DB_PATH = os.path.join(BASE_DIR, "database", "history.db")

# Rate Limiting
SLEEP_RANGE = (8, 15)  # Increased delay to avoid 401/429 errors
MAX_WORKERS = 3  # Number of concurrent downloads (Safest: 2-4)


# Feature Toggles
HEADLESS_BROWSER = True
