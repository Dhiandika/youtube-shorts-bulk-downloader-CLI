# Instagram Downloader Module

A robust, modular CLI tool for downloading Instagram Feed Posts and Reels in high resolution.
Designed with "Ghost Mode" (anonymous downloading) and smart rate limiting to prevent IP bans.

## Features
-   **High Resolution**: Automatically fetches the best quality available.
-   **Ghost Mode**: Auto-attempts anonymous download (no login required for public profiles).
-   **Smart Organization**: Saves files to `instagram_downloads/{username}/`.
-   **History Tracking**: Uses SQLite (`history.db`) to prevent re-downloading the same posts.
-   **Date Filtering**: Download profiles starting from a specific date.
-   **JSON Metadata**: Saves full post metadata for archives.

## Installation
1.  Open your terminal in the project root.
2.  Install dependencies:
    ```bash
    pip install -r instagram/requirements.txt
    ```

## Usage Scripts

### 1. Single Post Downloader
Best for quick downloads of specific Reels or Posts.
```bash
python instagram/single_downloader.py
```
*   **Input**: Paste an Instagram URL (Reel, Photo, TV).
*   **Output**: Downloads media to `instagram_downloads/{username}/`.

### 2. Bulk Profile Downloader
Best for archiving user profiles.
```bash
python instagram/bulk_downloader.py
```
*   **Input**: Enter a username (e.g., `cristiano`).
*   **Options**:
    *   *Download All*: Fetches every post.
    *   *Since Date*: Fetches posts newer than a specific date (e.g., `2024-01-01`).
    *   *Limit*: Fetches the last N posts.

### 3. All-in-One Menu
Interactive menu combining all features.
```bash
python instagram/main.py
```

## Workflow
1.  **Input**: User provides a URL or Username.
2.  **Verification**: Tool checks `database/history.db`.
    *   If `shortcode` exists -> **SKIP** (prevents duplicates).
    *   If new -> **PROCEED**.
3.  **Download**:
    *   Connects to Instagram (anonymously if possible).
    *   Downloads Media (Images/Video) + Caption + Metadata.
    *   Saves to `instagram_downloads/{username}/`.
4.  **Logging**: detailed logs in `instagram/logs/debug.log`.
5.  **Sleep**: Random delay (5-12s) between downloads to mimic human behavior (Safety).

## Configuration
Edit `instagram/settings.py` to change:
*   `SLEEP_RANGE`: Delay time.
*   `DOWNLOAD_DIR`: Where files are saved.
