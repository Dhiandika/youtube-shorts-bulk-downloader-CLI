
# Download all YouTube Shorts from a channel

Bulk download Shorts from a YouTube channel using Python ≥ 3.10.

<div align="center">

**Supports:** Windows / macOS / Linux • `yt-dlp`  • TinyDB
Global de-duplication by `video_id` • Persistent numbering • Date window (7/30/custom days)

</div>

---

## 📚 Table of Contents

- [Download all YouTube Shorts from a channel](#download-all-youtube-shorts-from-a-channel)
  - [📚 Table of Contents](#-table-of-contents)
  - [About the Project](#about-the-project)
  - [Project Layout](#project-layout)
  - [Quick Start](#quick-start)
  - [Which “main” should I use?](#which-main-should-i-use)
    - [Main 1 — Classic single-file flow](#main-1--classic-single-file-flow)
    - [Main 2 — Modular + DB + Global de-dup](#main-2--modular--db--global-de-dup)
    - [Main 3 — Date-window workflow (daily/weekly)](#main-3--date-window-workflow-dailyweekly)
  - [Core Features](#core-features)
  - [Requirements](#requirements)
  - [Configuration](#configuration)
  - [Output \& Numbering](#output--numbering)
  - [De-duplication Rules](#de-duplication-rules)
  - [Utility Scripts](#utility-scripts)
    - [`caption.py` (optional)](#captionpy-optional)
    - [`sort.py` (optional)](#sortpy-optional)
  - [Contributing](#contributing)
  - [License](#license)
    - [Notes for Maintainers](#notes-for-maintainers)

---

## About the Project

This repository contains a command-line toolset to download **YouTube Shorts** from a channel, safely, quickly, and repeatably:

* Interactive CLI with quality selection
* Safe filenames (ASCII-only) to avoid Windows console issues
* **TinyDB** for persistent metadata & download history
* **Global de-dup** across channels (by `video_id`)
* **Stable numbering** across runs (doesn’t reset at 1)
* Optional **date filters** (7 / 30 / custom days)

---

## Project Layout

```
.
├─ main.py                      # Main 1: classic single-file flow
├─ main2.py                     # Main 2: modular + DB + global de-dup
├─ main3.py    # Main 3: date-window workflow (+debug/enrichment)
├─ yt_short_downloader/
│  ├─ __init__.py
│  ├─ config.py                 # Defaults (output dir, retries, etc.)
│  ├─ fetch.py                  # get_short_links() via yt-dlp (extract_flat)
│  ├─ downloader.py             # download_video(s), safe filenames, retries
│  ├─ orchestrator.py           # index reservation, callbacks, DB marking
│  ├─ utils.py                  # filename sanitizers, numbering helpers
│  ├─ ytdlp_tools.py            # check_yt_dlp_installation, format helpers
│  ├─ db.py                     # TinyDB store (channels/videos), dedupe helpers
├─ console_guard.py             # Windows-safe printing & UTF-8 env patch
├─ caption.py                   # (optional) caption generation utility
├─ sort.py                      # (optional) organizer/renamer utility
├─ requirements.txt
└─ README.md
```

---

## Quick Start

1. **Install Python** 3.10+
2. **Install system tools**

   * Install `yt-dlp` (Python package)
3. **Install Python deps**

```bash
pip install -r requirements.txt
```

4. **Run one of the mains** (see next section to choose):

```bash
python main.py                # Classic flow
python main2.py               # Modular + DB + global de-dup
python main3.py               # Date-window workflow
```

> 💡 Windows users: we ship `console_guard.py` which sets `PYTHONIOENCODING=UTF-8` and patches `print` to avoid `charmap` errors in the console.

---

## Which “main” should I use?

### Main 1 — Classic single-file flow

**File:** `main.py`
**Use when:** You just want the original step-by-step flow, no date filtering.
**Flow:**

1. Ask for channel URL
2. Fetch & preview list (first 10 titles)
3. Confirm to proceed
4. Ask how many videos to download (or all)
5. Choose quality (best/worst/137+140/136+140/135+140)
6. Choose file format (MP4/WEBM)
7. Show final list to download
8. Download with progress bar

**What’s included:**

* Safe ASCII printing (via `console_guard`)
* Saves caption `.txt` next to each video
* Retries + best-format fallback
* **DB de-dup per video\_id globally** (won’t re-download across channels)
* Persistent numbering in the output folder

Run:

```bash
python main.py
```

---

### Main 2 — Modular + DB + Global de-dup

**File:** `main2.py`
**Use when:** You want the **modular code** path with TinyDB, orchestrator (stable numbering), and **global de-dup** across channels.
**Flow:** Similar to Main 1, but uses the refactored modules and DB flow everywhere.

**Extra goodies:**

* `TinyStore.is_downloaded_any(video_id)` → skip across channels
* `orchestrator.reserve_indices()` → numbering continues across runs
* Cleaner logs / error handling

Run:

```bash
python main2.py
```

---

### Main 3 — Date-window workflow (daily/weekly)

**File:** `main3.py`
**Use when:** You want to download **only videos in the last 7 days / 30 days / custom X days**.
**Flow:**

1. Ask for channel URL
2. Choose time window: 7 / 30 / custom / all
3. Fetch & **debug-dump** entries (raw/normalized/parsed dates)
4. Filter by date window
5. (Optional) **Enrich** missing `upload_date` via per-video `yt-dlp --dump-single-json` (max 25)
6. DB upsert, **global de-dup**, preview, download

Run:

```bash
python main3.py
```

---

## Core Features

* ✅ Bulk-download Shorts from a channel
* ✅ Quality selection & format (mp4/webm)
* ✅ Safe filenames (ASCII-only) to avoid Windows console encoding issues
* ✅ Multithreaded downloads with retries + backoff
* ✅ Caption `.txt` generation per video
* ✅ Progress bar via `tqdm`
* ✅ **TinyDB** metadata: channels/videos, timestamps
* ✅ **Global de-dup** by `video_id` (skip across channels and future runs)
* ✅ **Persistent numbering** (does not reset after switching channels)
* ✅ **Date filters** (Main 3): 7 / 30 / custom X days, with optional quick enrichment

---

## Requirements

* **Python** 3.10+
* **yt-dlp** (Python package)
* Python libs (via `requirements.txt`), e.g.: `tqdm`, `tinydb`, etc.

> Check `yt-dlp` availability is built-in (`check_yt_dlp_installation()`).

---

## Configuration

See `yt_short_downloader/config.py`. Common defaults:

* `DEFAULT_OUTPUT_DIR` → e.g. `"new_week"`
* `DEFAULT_FILE_FORMAT` → `"mp4"`
* `MAX_RETRIES` → `3`

You can change these or pass custom values inside your own wrapper scripts.

---

## Output & Numbering

* Files are named like:
  `NN - Clean_Title - Channel_Name.mp4`
  with `NN` continuing from the **highest existing index** in the output directory.
* Numbering is **reserved in DB** before starting (via orchestrator) to guarantee consistency even with multithreading.

---

## De-duplication Rules

* **Primary key**: YouTube `video_id` (unique globally).
* **Global check**: `TinyStore.is_downloaded_any(video_id)` ensures a video won’t be downloaded again even if you switch channels later.
* On successful download, `orchestrator` marks `downloaded=True` in DB; future runs will skip that `video_id`.

> If you ever want per-channel duplicates (not recommended), you could switch back to `store.is_downloaded(channel_key, vid)` — but the repo defaults to **global** de-dup to avoid clutter.

---

## Utility Scripts

### `caption.py` (optional)

* Reads `.txt` prompt files and generates social captions via **Google Gemini** (user supplies API key)
* Overwrites the original `.txt` with generated caption + hashtags

> See script header for usage details.

### `sort.py` (optional)

* Sort videos by mtime and rename to `NN - CleanName.ext`
* Renames matching `.txt` sidecars to keep captions aligned
* `--desc` for newest → oldest

---

## Contributing

PRs welcome! If you’re adding features:

* Keep the modular code in `yt_short_downloader/` clean & typed
* Prefer adding new flows as separate mains (so users can choose)
* Include a short note in this README

---

## License

MIT (or your preferred license). Add a `LICENSE` file if you haven’t yet.

---

### Notes for Maintainers

* The **DB schema** is intentionally simple (TinyDB tables: `channels`, `videos`).
* Global de-dup relies on `videos` documents where `downloaded=True`.
* If you change the DB path or table names, please reflect it in this README.
