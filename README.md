<!-- Banner -->



<h1 align="center">YouTube Shorts & TikTok Downloader Suite</h1>

<p align="center">
  Bulk-download untuk <b>YouTube Shorts</b> & <b>TikTok</b> dengan caption penuh, filter hashtag, de-dup global, dan alat manajemen pustaka.
</p>
<p align="center">
  <a href="images/baner.png" target="_blank">
    <img src="images/baner.png" alt="YouTube Shorts & TikTok Downloader Suite" width="900">
  </a>
</p>
<!-- Core badges -->
<p align="center">
  <!-- Project -->
  <a href="https://github.com/Dhiandika/youtube-shorts-bulk-downloader-CLI/stargazers">
    <img alt="Stars" src="https://img.shields.io/github/stars/Dhiandika/youtube-shorts-bulk-downloader-CLI?style=for-the-badge&logo=github">
  </a>
  <a href="https://github.com/Dhiandika/youtube-shorts-bulk-downloader-CLI/blob/main/LICENSE">
    <img alt="License" src="https://img.shields.io/badge/License-MIT-6E40C9?style=for-the-badge">
  </a>
  <img alt="Python" src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white">
  <img alt="OS" src="https://img.shields.io/badge/OS-Windows%20%7C%20macOS%20%7C%20Linux-333?style=for-the-badge">
</p>

<!-- Tech badges -->
<p align="center">
  <a href="https://github.com/Dhiandika/youtube-shorts-bulk-downloader-CLI/actions/workflows/workflow_name.yml">
    <img alt="CI" src="https://img.shields.io/github/actions/workflow/status/Dhiandika/youtube-shorts-bulk-downloader-CLI/workflow_name.yml?branch=main&style=for-the-badge&logo=github">
  </a>
</p>





<!-- Submodule tags -->
<p align="center">
  <img alt="YouTube" src="https://img.shields.io/badge/Module-YouTube_Shorts-FF0000?style=for-the-badge&logo=youtube&logoColor=white">
  <img alt="TikTok" src="https://img.shields.io/badge/Module-TikTok-000000?style=for-the-badge&logo=tiktok&logoColor=white">
</p>
<p align="center">
<img src="https://hitscounter.dev/api/hit?url=https%3A%2F%2Fgithub.com%2FDhiandika%2Fyoutube-shorts-bulk-downloader-CLI&label=YouTube+Shorts+%26+TikTok+Downloader+Suite&icon=github&color=%233d8bfd&message=&style=for-the-badge&tz=Asia%2FJakarta">

</p>

---

> ⚡️ **Fitur ringkas:** yt-dlp, caption penuh, filter hashtag (all/any), de-dup global (SQLite/TinyDB), numbering stabil, download multithread, pruning durasi, dan tools pengelolaan pustaka.

Bulk-download content from **YouTube Shorts** and **TikTok** with robust tooling: full captions, hashtag filters, global de-duplication, multithread downloads, and library management utilities.

<div align="center">

**Supports:** Windows / macOS / Linux • `yt-dlp` • SQLite / TinyDB
Global de-duplication • Stable numbering • Hashtag rules • Duration pruning

</div>

---

## 📚 Table of Contents

- [📚 Table of Contents](#-table-of-contents)
- [About the Project](#about-the-project)
- [Project Layout](#project-layout)
- [Quick Start](#quick-start)
  - [YouTube Shorts — choose a “main”](#youtube-shorts--choose-a-main)
  - [TikTok — run-once flows (config-first)](#tiktok--run-once-flows-config-first)
- [Core Features](#core-features)
- [Requirements](#requirements)
- [Configuration](#configuration)
  - [YouTube (`tiktok/yt_short_downloader/config.py`)](#youtube-tiktokyt_short_downloaderconfigpy)
  - [TikTok (`tiktok/tiktok_dl/config.py` and script-level constants)](#tiktok-tiktoktiktok_dlconfigpy-and-script-level-constants)
- [Output \& Numbering](#output--numbering)
- [De-duplication Rules](#de-duplication-rules)
- [TikTok Tools (DB-based Management)](#tiktok-tools-db-based-management)
- [Pruning by Duration (Folder-level)](#pruning-by-duration-folder-level)
- [Utility Scripts](#utility-scripts)
- [Troubleshooting](#troubleshooting)
- [Legal \& Ethics](#legal--ethics)
- [Contributing](#contributing)
- [License](#license)
- [Notes for Maintainers](#notes-for-maintainers)

---

## About the Project

This repository combines two downloader toolsets:

1. **YouTube Shorts Downloader (CLI-oriented)**
   Modular code with TinyDB for metadata, **global de-dup** by `video_id`, stable numbering, and optional date-window workflows.

2. **TikTok Downloader Suite (config-first or CLI)**
   Full caption extraction, **hashtag prefilter** (all/any), **SQLite**-backed global de-dup, multithread download, and post-download management (sort/filter/prune).

---

## Project Layout

```
📦youtube-shorts-bulk-downloader-CLI
 ┣ 📂images/
 ┃ ┗ 📜image.png
 ┣ 📂tiktok/
 ┃ ┣ 📂tiktok_dl/
 ┃ ┃ ┣ __pycache__/...
 ┃ ┃ ┣ bulk.py              # read sources, prefilter hashtags
 ┃ ┃ ┣ cli.py               # optional CLI helpers
 ┃ ┃ ┣ config.py            # THREADS, MAX_RETRIES, defaults
 ┃ ┃ ┣ db.py                # SQLite schema + helpers
 ┃ ┃ ┣ downloader.py        # multithread downloads + caption .txt
 ┃ ┃ ┣ filters.py           # sort/filter by duration & hashtags (DB)
 ┃ ┃ ┣ meta.py              # listing & full metadata (description)
 ┃ ┃ ┣ utils.py             # sanitizers, yt-dlp check, helpers
 ┃ ┃ ┗ __init__.py
 ┃ ┣ 📂yt_short_downloader/  # YouTube (modular)
 ┃ ┃ ┣ __pycache__/...
 ┃ ┃ ┣ config.py
 ┃ ┃ ┣ db.py                # TinyDB store
 ┃ ┃ ┣ downloader.py
 ┃ ┃ ┣ fetch.py
 ┃ ┃ ┣ orchestrator.py
 ┃ ┃ ┣ utils.py
 ┃ ┃ ┣ ytdlp_tools.py
 ┃ ┃ ┗ __init__.py
 ┃ ┣ __pycache__/...
 ┃ ┣ .env                    # (optional) for caption tools etc.
 ┃ ┣ caption.py              # optional caption generator (YouTube flow)
 ┃ ┣ console_guard.py        # safe UTF-8 console for Windows
 ┃ ┣ download_errors.log     # appended runtime errors
 ┃ ┣ main.py                 # YouTube main 1: classic flow
 ┃ ┣ main2.py                # YouTube main 2: modular + global de-dup
 ┃ ┣ main3.py                # YouTube main 3: date-window workflow
 ┃ ┣ prompt.txt              # prompt for caption.py
 ┃ ┣ README.md               # (TikTok/YouTube local doc — optional)
 ┃ ┣ requirements.txt
 ┃ ┣ sort.py                 # optional organizer/renamer (YouTube)
 ┃ ┗ video_metadata.json     # optional dump
 ┣ .gitattributes
 ┣ .gitignore
 ┣ README.md                 # ← you are here (combined root README)
 ┗ yt_simplify.py
```

> **Databases:**
> *YouTube:* TinyDB (JSON) in `tiktok/yt_short_downloader/db.py`.
> *TikTok:* SQLite `tiktok/tiktok.db` (auto-created).

---

## Quick Start

### YouTube Shorts — choose a “main”

1. Install Python **3.10+** and tools:

   ```bash
   pip install -r tiktok/requirements.txt
   ```
2. Run one of the mains in `tiktok/`:

* **Main 1 — Classic single-file flow** (`main.py`)
  Interactive, step-by-step (no date filtering).

  ```bash
  python tiktok/main.py
  ```

* **Main 2 — Modular + DB + global de-dup** (`main2.py`)
  Uses modular package + TinyDB orchestrator.

  ```bash
  python tiktok/main2.py
  ```

* **Main 3 — Date-window workflow** (`main3.py`)
  Download last 7/30/custom days; can enrich missing dates.

  ```bash
  python tiktok/main3.py
  ```

> Windows tip: use `tiktok/console_guard.py` if you see console encoding issues.

---

### TikTok — run-once flows (config-first)

* **Run from a users list** (one per line; supports `@handle` or profile URL).
  Edit config constants in your script (e.g., `TikTokDownloader.py` or `bulk_from_file.py`) then:

  ```bash
  python tiktok/TikTokDownloader.py
  # or the streaming/timeout variant:
  python tiktok/bulk_from_file.py
  ```

* **Hashtag prefilter:** set `REQUIRED_TAGS` (e.g., `["#fyp", "#hololive"]`) and `TAG_MODE` (`"all"` or `"any"`).
  Non-matching videos are **skipped** up front (optional: `skipped_hashtag` status in DB).

* **Output:** videos saved to `DEFAULT_OUTDIR` (see `tiktok/tiktok_dl/config.py`), with a paired caption `.txt` that contains the **full** `description`.

---

## Core Features

**Common**

* `yt-dlp` integration with retries, backoff, and format selection.
* Safe filenames (ASCII-only sanitizer).
* Progress bars via `tqdm`.
* Error logging to `download_errors.log`.

**YouTube**

* Modular design with TinyDB for channels/videos.
* **Global de-dup** (won’t redownload across channels).
* Stable numbering across runs.
* Optional date windows (7/30/custom days), fast enrichment path.

**TikTok**

* Full caption extraction (no `...` truncation).
* **Hashtag rules** (`all`/`any`) before download.
* **SQLite** DB with statuses: `queued`, `downloading`, `success`, `failed`, `deleted`, `skipped_hashtag`.
* Multithread downloads (configure `THREADS`).

---

## Requirements

* **Python** 3.10+
* **yt-dlp** (Python package)
* **tqdm**
* **ffmpeg/ffprobe** on PATH (for duration & robust probing)
* (Optional for TikTok/YouTube restricted content) **Chrome/Firefox/Edge** for cookies

```bash
pip install -r tiktok/requirements.txt
# or
pip install -U yt-dlp tqdm
```

**ffmpeg/ffprobe**

* Windows: download from ffmpeg.org; add `bin/` to PATH.
* macOS: `brew install ffmpeg`
* Ubuntu/Debian: `sudo apt-get install ffmpeg`

---

## Configuration

### YouTube (`tiktok/yt_short_downloader/config.py`)

* Output dir, default format, retries, etc.
* Or pass values in `main2.py`/`main3.py` logic.

### TikTok (`tiktok/tiktok_dl/config.py` and script-level constants)

* `THREADS`, `MAX_RETRIES`, `DEFAULT_DB` (`tiktok.db`), `DEFAULT_OUTDIR`.
* In `TikTokDownloader.py` / `bulk_from_file.py` set:

  * `INPUT_FILE` (default `tiktok/users.txt`)
  * `COOKIES_FROM_BROWSER` (`None` / `"chrome"` / `"firefox"` / `"edge"`)
  * `MAX_PER_USER` (limit per profile)
  * `QUALITY`/`FORMAT` (e.g., `"best"`, `"mp4"`)
  * `REQUIRED_TAGS` / `TAG_MODE`
  * Listing & metadata timeouts (streaming variant)
  * `DRY_RUN` for simulation

---

## Output & Numbering

**YouTube**

* Filenames like `NN - Clean_Title - Channel_Name.mp4`.
* **Persistent numbering** via orchestrator; continues across runs.

**TikTok**

* Filenames like `NN - Safe_Title - Uploader.mp4` (with paired `NN - ... .txt` caption).
* Index `NN` continues from the highest existing in the output directory.
* Caption `.txt` contains **full** description + URL + ID.

---

## De-duplication Rules

**YouTube**

* Global by `video_id` (TinyDB).
* `is_downloaded_any(video_id)` guards against re-downloads across channels/runs.

**TikTok**

* Global by `video_id` (SQLite UNIQUE).
* Already-known `video_id` → skipped before download.

---

## TikTok Tools (DB-based Management)

You can manage downloaded items using DB:

* **Sort by duration**
  Compute durations via `ffprobe` and list ascending/descending.
  (With your non-CLI config variant or the provided CLI `manage_videos.py`.)

* **Filter by duration & hashtags**
  Enforce `min/max` seconds and hashtag rules.
  Optionally **delete** failing items (video + paired caption `.txt`) and set `status='deleted'`.

---

## Pruning by Duration (Folder-level)

Use the provided **folder-level** pruner (no DB required) to clean `tiktok_downloads/`:

* Keep videos **≤ 120 s** (configurable).
* Delete videos **> limit** **and** their paired caption `.txt` (same base filename).

This is useful after bulk runs or when you want a quick, filesystem-only cleanup.

---

## Utility Scripts

* **YouTube**

  * `caption.py` — generate social captions from `.txt` (requires your API key; see file header).
  * `sort.py` — rename/organize by mtime → `NN - CleanName.ext` (keeps `.txt` paired).
  * `console_guard.py` — guard against Windows console encoding issues.

* **TikTok**

  * `bulk_from_file.py` — *streaming* listing + metadata with timeouts (avoid “stuck”).
  * `manage_videos.py` — CLI sort/filter via DB (if you prefer args over config).
  * Your config-only runners (e.g., `TikTokDownloader.py`) — set constants once and run.

---

## Troubleshooting

* **Stuck listing (TikTok)** → Use `bulk_from_file.py` (CLI JSON listing + timeouts) or enable `COOKIES_FROM_BROWSER`.
* **Caption shows `...`** → Ensure you’re running the flows that fetch **full metadata** (this repo’s TikTok suite does).
* **403 / format not available** → Try `QUALITY = "best"` or a simpler format; enable cookies.
* **Duration `??`** → Install `ffprobe` and ensure it’s on PATH.
* **Windows encoding errors** → Run via `console_guard.py` or set `PYTHONIOENCODING=UTF-8`.

---

## Legal & Ethics

* Only download content you have rights or permission to save.
* Respect TikTok/YouTube Terms of Service and copyright law.
* Keep your cookies private; do not share credentials.

---

## Contributing

PRs welcome. Please:

* Keep modular code clean and typed.
* Add new flows as separate mains/scripts when possible.
* Update this README when changing DB schemas, defaults, or behaviors.

---

## License

MIT (or your preferred license). Add a `LICENSE` file if needed.

---

## Notes for Maintainers

* **YouTube DB:** TinyDB (tables for `channels`, `videos`), global de-dup relies on `video_id`.
* **TikTok DB:** SQLite with `users`, `videos`, `user_videos`, and helpful indices.
* Status transitions (TikTok): `queued → downloading → success | failed | deleted | skipped_hashtag`.
* If changing defaults (e.g., output dirs, DB paths), mirror updates in this README and in script headers.
