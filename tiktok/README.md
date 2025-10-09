# TikTok Downloader Suite — Documentation

A robust, modular toolkit to **bulk-download** TikTok videos, preserve **full captions**, enforce **hashtag rules**, prevent duplicates with **SQLite**, and manage your local library with **sorting** and **cleanup** utilities.

This documentation matches your current project layout:

```
📦tiktok
 ┣ 📂tiktok_dl
 ┃ ┣ 📂__pycache__/
 ┃ ┣ 📜bulk.py
 ┃ ┣ 📜cli.py
 ┃ ┣ 📜config.py
 ┃ ┣ 📜db.py
 ┃ ┣ 📜downloader.py
 ┃ ┣ 📜filters.py
 ┃ ┣ 📜meta.py
 ┃ ┣ 📜utils.py
 ┃ ┗ 📜__init__.py
 ┣ 📜bulk_from_file.py
 ┣ 📜download_errors.log
 ┣ 📜main.py
 ┣ 📜manage_videos.py
 ┣ 📜tiktok.db
 ┣ 📜TikTokDownloader.py
 ┗ 📜users.txt
```

---

## 1) What’s Inside

### Core package (`tiktok_dl/`)

* `config.py` — Global knobs (retries, thread count, defaults).
* `utils.py` — Helpers (yt-dlp presence check, filename sanitizing, path utilities).
* `db.py` — SQLite wrapper. Tables:

  * `users(handle UNIQUE, display_name, created_at)`
  * `videos(video_id UNIQUE, url, title, uploader_handle, status, file_path, caption_path, created_at, updated_at)`
  * `user_videos(uploader_handle, video_id, PRIMARY KEY(uploader_handle, video_id))`
* `meta.py` — Listing & full metadata (caption) via yt-dlp (API).
* `downloader.py` — Multithreaded downloading engine (file naming, caption `.txt` writing).
* `filters.py` — Post-download tools: sort by duration, filter by duration/hashtag (delete if desired).
* `bulk.py` — Helpers to read `users.txt`, collect entries per user, apply pre-filter hashtag (before download).
* `cli.py` — Interactive/CLI entry helpers (optional).

### Top-level scripts

* `TikTokDownloader.py` — **Single-file runner without CLI args** (your “just run once” flow). You can configure constants inside the file.
* `bulk_from_file.py` — **Streaming/timeout** variant: lists via `yt-dlp -J --flat-playlist` (with timeouts) then filters captions and downloads. Good for avoiding “stuck”.
* `main.py` — Interactive entry (optional).
* `manage_videos.py` — CLI utility (sort/filter using DB) — optional if you prefer config-only scripts.
* `users.txt` — One user/profile/URL per line (ignored lines start with `#`).
* `tiktok.db` — SQLite database (generated).
* `download_errors.log` — Error log file (appended over time).

---

## 2) Key Features

* **Bulk download per user** (profile) or list of users from `users.txt`.
* **Full caption** preservation using TikTok `description` (no “...” truncation).
* **Hashtag rules**: `all` (all required tags present) or `any` (at least one).
* **De-duplication** at DB level (unique `video_id`).
* **Multithreaded** downloads (tune in `tiktok_dl/config.py`).
* **Management tools**:

  * Sort by duration.
  * Filter by duration/hashtags; optionally delete non-conforming items (video + paired caption file).
* **Stability**:

  * Listing with **timeout** (CLI JSON mode) to avoid hanging.
  * Full metadata fetch with **socket timeouts + retries**.

---

## 3) Requirements

* Python **3.9+** (3.10+ recommended).
* `yt-dlp` (latest).
* `tqdm`.
* **ffmpeg/ffprobe** on PATH (for duration extraction & robust media handling).
* (Optional) Chrome/Firefox/Edge (for `cookies-from-browser` when login is needed).

### Install dependencies

```bash
pip install -U yt-dlp tqdm
# or keep a requirements.txt containing:
# yt-dlp>=2025.1.1
# tqdm>=4.66.0
```

### Install ffmpeg/ffprobe

* Windows: download from ffmpeg.org; add `bin/` to PATH.
* macOS: `brew install ffmpeg`
* Ubuntu/Debian: `sudo apt-get install ffmpeg`

---

## 4) Quick Start

### A) Prepare your sources

Edit `users.txt`:

```
# one per line; comments allowed
@hololiveedit35
https://www.tiktok.com/@some_creator
@another_user
```

### B) Run the simple runner (no CLI args)

Use **`TikTokDownloader.py`** (or your consolidated config-based runner).
Open the file and adjust the **CONFIG** section (input file path, hashtag rules, cookies, quality/format, etc.), then:

```bash
python TikTokDownloader.py
```

This will:

1. Read `users.txt`.
2. List videos per user (with timeouts if using the streaming variant).
3. Prefilter by hashtag rule (if configured).
4. Skip items already in `tiktok.db`.
5. Download the rest to your output folder and write a `.txt` caption alongside each video.

> If your environment sometimes “hangs” on listing, use `bulk_from_file.py` (it’s pre-wired to avoid that by design). Open it, tweak top-of-file constants, and run `python bulk_from_file.py`.

---

## 5) Configuration Highlights

### Global (in `tiktok_dl/config.py`)

* `THREADS`: parallel download workers.
* `MAX_RETRIES`: download retry attempts.
* `DEFAULT_DB`, `DEFAULT_OUTDIR`: defaults used across scripts.

### Runner scripts (e.g., `TikTokDownloader.py` or `bulk_from_file.py`)

Typical adjustable constants:

* `INPUT_FILE` — path to `users.txt`.
* `DB_PATH`, `OUTDIR`.
* `COOKIES_FROM_BROWSER` — `None`, `"chrome"`, `"firefox"`, or `"edge"`.
* `MAX_PER_USER` — limit videos per user.
* `QUALITY` — yt-dlp format expression (e.g., `"best"`, `"bv*+ba"`, `"worst"`).
* `FORMAT` — `"mp4"` or `"webm"`.
* `REQUIRED_TAGS` — list of hashtags; use `["#fyp", "#hololive"]` or without `#` (both handled).
* `TAG_MODE` — `"all"` or `"any"`.
* `MARK_SKIPPED_IN_DB` — set `True` to record non-conforming items as `skipped_hashtag`.
* Timeouts: listing timeout, metadata socket timeout, retries.
* `DRY_RUN` — simulate filtering without downloading (or without deleting, depending on the script).

---

## 6) Workflows

### 6.1 Download with hashtag prefilter

1. Set `REQUIRED_TAGS` and `TAG_MODE` in `TikTokDownloader.py` (or `bulk_from_file.py`).
2. Optionally set `COOKIES_FROM_BROWSER` to pass login checks.
3. Run the script: `python TikTokDownloader.py`.
4. Only qualifying items (by hashtag) are downloaded and recorded as `success` in DB.

### 6.2 Manage library after download (DB-level)

Use **`manage_videos.py`** (CLI) or config-driven `manage_videos_config.py` (if you created it):

* **Sort by duration** (read durations with ffprobe and print top N).
* **Filter by duration & hashtags**, optionally **delete** those failing criteria.
  When deleting:

  * Video file is removed.
  * Caption `.txt` with the same base filename is removed.
  * DB status updated to `deleted`.

### 6.3 Folder pruning by duration (no DB)

Use **`prune_by_duration.py`** to scan `tiktok_downloads/` and:

* Keep videos `≤ 120s`.
* Delete videos `> 120s` **and** the paired caption `.txt` that shares the same base name.

Example of paired names:

```
01 - #hololive_#hololiveclips_#vestiazeta - anggaeg.mp4
01 - #hololive_#hololiveclips_#vestiazeta - anggaeg.txt
```

---

## 7) Script-by-Script Guide

### `TikTokDownloader.py`

* **Purpose:** Configuration-first, one-shot run. No external CLI args.
* **Flow:**

  1. Read `users.txt`.
  2. List entries per user (with timeout, if using the streaming approach).
  3. Prefilter by hashtags using full metadata (caption).
  4. Skip duplicates (DB).
  5. Download remaining items (multithreaded).
  6. Write `.txt` caption for every video.

### `bulk_from_file.py`

* **Purpose:** More “resilient” version focused on **not getting stuck**.
* **Key behavior:** Listing via `yt-dlp -J --flat-playlist` + timeout; metadata fetch per item with socket timeout/retries; prefilter hashtags; then download.

### `main.py`

* Optional interactive entry point (depends on your earlier setup). Not required if you prefer configuration-only runners.

### `manage_videos.py` (CLI)

* **sort:** print sorted list by duration (asc/desc).
* **filter:** filter by `min/max` duration & hashtags; optional deletion (video + paired caption) and DB status update.

> If you prefer **no CLI**, port the config block version you already created (`manage_videos_config.py` style) and run it directly.

### `tiktok_dl/*` modules

* **You generally don’t run these**; they are imported by the scripts.
* Change behavior via `config.py` (e.g., thread count, retries) or by editing calling scripts.

---

## 8) Database & Statuses

* Each video is uniquely keyed by **`video_id`** in `videos`.
* Typical lifecycle:

  * `queued` → `downloading` → `success`
  * Or: `failed` on last retry
  * Or: `skipped_hashtag` (prefilter failed)
  * Or: `deleted` (removed by maintenance tools)
* The **anti-duplication** check prevents re-downloading if `video_id` already exists.

---

## 9) Error Logs

* All non-fatal runtime errors append to `download_errors.log`.
* If downloads fail or time out, inspect this file for the exact yt-dlp command and stderr.

---

## 10) Tips & Troubleshooting

* **Listing “hangs”**: use `bulk_from_file.py`, which enforces timeouts; or enable `COOKIES_FROM_BROWSER`.
* **403 / format not available**: switch `QUALITY` to a more general expression (`"best"` or `"b"`), and/or enable cookies.
* **Duration is “??”**: ensure `ffprobe` is installed and on PATH.
* **Caption shows “...”**: this suite fetches **full metadata**; `.txt` uses `description` (untruncated). If truncated, verify the script uses the full-metadata path before writing `.txt`.

---

## 11) Legal & Ethics

* Download only content you have the rights or permission to save.
* Respect TikTok ToS, local laws, and copyright.
* Cookies are personal—do not share them.

---

## 12) License

Specify your project license (recommended: MIT). Example:

```
MIT License
Copyright (c) ...
```

---

### Appendix: Common Config Snippets

**Require any of these tags before download:**

```python
REQUIRED_TAGS = ["#fyp", "#hololive"]
TAG_MODE = "any"
```

**Hard limit to 50 per user and best MP4:**

```python
MAX_PER_USER = 50
QUALITY = "best"
FORMAT = "mp4"
```

**Use cookies from Chrome (for private/age-gated profiles):**

```python
COOKIES_FROM_BROWSER = "chrome"
```

**Prune local folder to ≤ 120s (simulate first):**

```python
# in prune_by_duration.py CONFIG
"MAX_DURATION_SECONDS": 120,
"DRY_RUN": True,
```

If you want, I can add a **single consolidated README.md** file to your repo with this content, plus quick badges and a minimal changelog.
