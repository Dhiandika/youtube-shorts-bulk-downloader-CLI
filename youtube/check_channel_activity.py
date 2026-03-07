"""
check_channel_activity.py
=========================
Scan channel YouTube dari short_link.txt dan cek seberapa rutin mereka
upload Shorts dalam N hari ke belakang.

Kategorisasi berdasarkan STREAK hari berturut-turut upload:
  🔥 Daily      — upload SETIAP hari (streak = 7/7, semua hari)
  ✅ Active     — streak upload 3–5 hari berturut-turut
  ⚠️  Occasional — upload 2 hari (tidak streak ≥3)
  📉 Rarely     — upload hanya 1 hari dalam window
  ❌ Inactive   — tidak ada upload sama sekali dalam window
  ⛔ Error      — yt-dlp & pytube keduanya gagal fetch

Fetch priority: yt-dlp → pytube (fallback otomatis jika yt-dlp error)

Output ke: youtube/output_reports/
  channel_activity_YYYY-MM-DD.md
  channel_activity_YYYY-MM-DD.txt
"""

# ══════════════════════════════════════════════════════════════════════════════
#  ⚙️  KONFIGURASI — Edit bagian ini sesuai kebutuhan
# ══════════════════════════════════════════════════════════════════════════════

# Jumlah hari ke belakang yang di-scan (default 7)
SCAN_WINDOW_DAYS: int = 7

# Jumlah video terbaru yang di-scan per channel.
# Cara kerja: ambil N video terbaru dari playlist → cek tanggal upload tiap video
# → filter yang masuk 7 hari terakhir → hitung streak hari berturut-turut.
# YouTube tidak bisa discan per-hari secara langsung; ini adalah cara yang benar.
# Naikkan nilai ini jika channel upload sangat banyak per hari (misal 5 video/hari → set 50+)
FETCH_PER_CHANNEL: int = 20

# Batasi jumlah channel yang di-proses.
# None  = proses semua channel dari file
# Angka = hanya proses N channel pertama (berguna untuk test cepat)
CHANNEL_LIMIT = None   # contoh: CHANNEL_LIMIT = 10

# Path file sumber URL (relatif dari lokasi script ini)
INPUT_FILE: str = "short_link.txt"

# ── Threshold streak untuk kategori Active ────────────────────────────────────
# Streak hari berturut-turut yang dianggap "Active"
ACTIVE_STREAK_MIN: int = 3   # minimal 3 hari berturut-turut
ACTIVE_STREAK_MAX: int = 5   # maksimal 5 (lebih dari ini = Daily)

# ══════════════════════════════════════════════════════════════════════════════
#  JANGAN UBAH DI BAWAH INI KECUALI KAMU TAHU APA YANG DILAKUKAN
# ══════════════════════════════════════════════════════════════════════════════

import sys
from datetime import datetime, timedelta, date
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
SHORT_LINK = SCRIPT_DIR / INPUT_FILE
OUTPUT_DIR = SCRIPT_DIR / "output_reports"
TODAY      = datetime.now().date()
TODAY_STR  = TODAY.strftime("%Y-%m-%d")
NOW_TS     = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# ── Label kategori ─────────────────────────────────────────────────────────────
CAT_DAILY      = "🔥 Daily"
CAT_ACTIVE     = "✅ Active"
CAT_OCCASIONAL = "⚠️ Occasional"
CAT_RARELY     = "📉 Rarely"
CAT_INACTIVE   = "❌ Inactive"
CAT_ERROR      = "⛔ Error"

ALL_CATS = [CAT_DAILY, CAT_ACTIVE, CAT_OCCASIONAL, CAT_RARELY, CAT_INACTIVE, CAT_ERROR]


# ══════════════════════════════════════════════════════════════════════════════
#  PROGRESS (tqdm opsional)
# ══════════════════════════════════════════════════════════════════════════════
try:
    from tqdm import tqdm
    _TQDM = True
except ImportError:
    _TQDM = False


def progress_iter(items, desc=""):
    if _TQDM:
        return tqdm(items, desc=desc, unit="ch", dynamic_ncols=True)
    return items


# ══════════════════════════════════════════════════════════════════════════════
#  URL HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def is_youtube(url: str) -> bool:
    return "youtube.com" in url or "youtu.be" in url


def normalize_url(url: str) -> str:
    url = url.strip().rstrip("/")
    if "/@" in url:
        handle = url.split("/@")[1].split("/")[0]
        return f"https://www.youtube.com/@{handle}/shorts"
    elif "/channel/" in url:
        cid = url.split("/channel/")[1].split("/")[0]
        return f"https://www.youtube.com/channel/{cid}/shorts"
    if not url.endswith("/shorts"):
        url += "/shorts"
    return url


def short_label(url: str) -> str:
    if "/@" in url:
        return "@" + url.split("/@")[1].split("/")[0]
    elif "/channel/" in url:
        cid = url.split("/channel/")[1].split("/")[0]
        return cid[:26] + "…" if len(cid) > 26 else cid
    return url[:40]


def load_urls(filepath: Path) -> list:
    seen: set = set()
    result: list = []
    with open(filepath, encoding="utf-8") as f:
        for line in f:
            raw = line.strip()
            if not raw or raw.startswith("#"):
                continue
            if not is_youtube(raw):
                continue
            norm = normalize_url(raw)
            if norm not in seen:
                seen.add(norm)
                result.append(norm)
    return result


# ══════════════════════════════════════════════════════════════════════════════
#  FETCH — Metode 1: yt-dlp
# ══════════════════════════════════════════════════════════════════════════════
class _SilentLogger:
    """Suppress semua output yt-dlp ke konsol (termasuk error 404 dll)."""
    def debug(self, msg): pass
    def info(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass


def _parse_raw_date(raw: str):
    """Parse string 'YYYYMMDD' ke date object. Return None jika gagal."""
    if raw and len(raw) == 8:
        try:
            return datetime.strptime(raw, "%Y%m%d").date()
        except ValueError:
            pass
    return None


def _get_single_video_date(video_id: str) -> tuple:
    """
    Ambil upload_date & title untuk 1 video via yt-dlp Python API.
    Sama seperti enrich_missing_upload_dates() di main4.py tapi pakai API bukan subprocess.
    Return: (upload_date: date | None, title: str)
    """
    try:
        import yt_dlp
        url = f"https://www.youtube.com/shorts/{video_id}"
        opts = {
            "quiet": True,
            "no_warnings": True,
            "logger": _SilentLogger(),
            "skip_download": True,
            "ignoreerrors": True,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False) or {}
        upload_d = _parse_raw_date(info.get("upload_date") or "")
        title    = (info.get("title") or "Unknown")[:120]
        return upload_d, title
    except Exception:
        return None, "Unknown"


def fetch_ytdlp(channel_url: str, max_fetch: int) -> dict | None:
    """
    2-Phase fetch (terinspirasi main4.py):

    Phase 1 — Flat extraction (cepat):
        Ambil daftar video ID dari playlist channel shorts.
        extract_flat=True → TIDAK mengembalikan upload_date untuk tab Shorts
        (keterbatasan yt-dlp), tapi sangat cepat untuk dapat ID & judul kasar.

    Phase 2 — Per-video enrichment dengan early-stop (dari main4.py):
        Untuk setiap video ID, fetch info lengkap (termasuk upload_date).
        Playlist sudah diurutkan terbaru → terlama, jadi begitu ketemu video
        yang lebih tua dari cutoff → BERHENTI (tidak perlu scan sisa).

        Efeknya:
          - Channel inactive : 1–2 individual call → selesai sangat cepat
          - Channel Daily    : ~7–8 individual call → selesai setelah window penuh
    """
    try:
        import yt_dlp
    except ImportError:
        return None

    # ── Phase 1: Flat extraction untuk dapat daftar video ID ─────────────────
    flat_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "playlistend": max_fetch,
        "logger": _SilentLogger(),
    }
    try:
        with yt_dlp.YoutubeDL(flat_opts) as ydl:
            info = ydl.extract_info(channel_url, download=False)
    except Exception:
        return None

    if not info or "entries" not in info:
        return None

    entries = [e for e in (info.get("entries") or []) if e and e.get("id")]
    name = (
        info.get("uploader")
        or info.get("channel")
        or short_label(channel_url)
    )

    if not entries:
        return {"name": name, "url": channel_url, "videos": [], "method": "yt-dlp"}

    # ── Phase 2: Enrichment per-video + early-stop ───────────────────────────
    cutoff = TODAY - timedelta(days=SCAN_WINDOW_DAYS)
    videos      = []
    skipped_old = 0

    for e in entries[:max_fetch]:
        vid_id = e.get("id", "")

        # Cek apakah flat extraction sudah menyediakan upload_date (kadang ada)
        upload_d = _parse_raw_date(e.get("upload_date") or "")
        title    = (e.get("title") or "Unknown")[:120]

        # Jika tidak ada dari flat → enrichment individual (main4.py style)
        if upload_d is None:
            upload_d, title_fetched = _get_single_video_date(vid_id)
            if title == "Unknown" or not title:
                title = title_fetched

        videos.append({
            "id":          vid_id,
            "title":       title,
            "upload_date": upload_d,
        })

        # ── Early-stop (dari main4.py) ─────────────────────────────────────
        # Playlist diurutkan terbaru → terlama.
        # Begitu upload_date lebih tua dari cutoff, semua sisanya juga lebih tua.
        if upload_d and upload_d < cutoff:
            skipped_old = len(entries) - len(videos)
            break

    return {
        "name":        name,
        "url":         channel_url,
        "videos":      videos,
        "method":      "yt-dlp",
        "early_stop":  skipped_old > 0,
        "skipped_old": skipped_old,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  FETCH — Metode 2: pytube (fallback)
# ══════════════════════════════════════════════════════════════════════════════
def fetch_pytube(channel_url: str, max_fetch: int) -> dict | None:
    try:
        from pytube import Channel
    except ImportError:
        return None

    try:
        base_url = channel_url.replace("/shorts", "").rstrip("/")
        ch = Channel(base_url)

        try:
            name = ch.channel_name
        except Exception:
            name = short_label(channel_url)

        videos = []
        try:
            shorts_iter = ch.shorts
        except AttributeError:
            shorts_iter = ch.videos

        count = 0
        for yt_obj in shorts_iter:
            if count >= max_fetch:
                break
            try:
                upload_d = None
                try:
                    pub = yt_obj.publish_date
                    if pub:
                        upload_d = pub.date() if hasattr(pub, "date") else None
                except Exception:
                    pass

                videos.append({
                    "id":          yt_obj.video_id,
                    "title":       (yt_obj.title or "Unknown")[:120],
                    "upload_date": upload_d,
                })
                count += 1
            except Exception:
                continue

        if count == 0:
            return None

        return {"name": name, "url": channel_url, "videos": videos, "method": "pytube"}

    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════════════
#  FETCH — Gabungan (yt-dlp → pytube)
# ══════════════════════════════════════════════════════════════════════════════
def fetch_channel(channel_url: str, max_fetch: int) -> dict:
    data = fetch_ytdlp(channel_url, max_fetch)
    if data is not None:
        return data

    data = fetch_pytube(channel_url, max_fetch)
    if data is not None:
        data["method"] += " (fallback)"
        return data

    return {
        "name":   None,
        "url":    channel_url,
        "videos": [],
        "method": "failed",
        "error":  "yt-dlp dan pytube keduanya gagal fetch data channel",
    }


# ══════════════════════════════════════════════════════════════════════════════
#  STREAK LOGIC
# ══════════════════════════════════════════════════════════════════════════════
def max_consecutive_streak(dates: list) -> int:
    """
    Hitung streak hari berturut-turut terpanjang dari list of date objects.
    Contoh: [Feb-18, Feb-19, Feb-20, Feb-22] → streak = 3 (18,19,20)
    """
    if not dates:
        return 0
    sorted_dates = sorted(set(dates))
    max_s = current_s = 1
    for i in range(1, len(sorted_dates)):
        diff = (sorted_dates[i] - sorted_dates[i - 1]).days
        if diff == 1:
            current_s += 1
            max_s = max(max_s, current_s)
        else:
            current_s = 1
    return max_s


# ══════════════════════════════════════════════════════════════════════════════
#  ANALISIS
# ══════════════════════════════════════════════════════════════════════════════
def analyse(data: dict, window: int) -> dict:
    """
    Kategorisasi berdasarkan STREAK hari berturut-turut dalam window terakhir:

      Daily      → streak ≥ window (setiap hari tanpa skip)
      Active     → streak 3–5 hari berturut-turut (ACTIVE_STREAK_MIN s/d MAX)
      Occasional → 2 hari upload tapi streak < 3
      Rarely     → hanya 1 hari upload dalam window
      Inactive   → 0 hari upload dalam window
      Error      → fetch gagal
    """
    if "error" in data:
        return {
            **data,
            "category":    CAT_ERROR,
            "unique_days": 0,
            "max_streak":  0,
            "uploads_w":   0,
            "last_upload": None,
            "latest_title": "",
        }

    cutoff = TODAY - timedelta(days=window)

    # Ambil upload_date dalam window (strictly: upload_date > cutoff = hari ini - window)
    dates_window = [
        v["upload_date"] for v in data["videos"]
        if v["upload_date"] and v["upload_date"] > cutoff
    ]

    unique_days  = len(set(dates_window))
    uploads_w    = len(dates_window)
    streak       = max_consecutive_streak(dates_window)

    # Upload date terbaru (dari semua video, bukan hanya window)
    all_dates = [v["upload_date"] for v in data["videos"] if v["upload_date"]]
    last_upload = max(all_dates) if all_dates else None

    # Judul short terbaru (dalam window)
    with_dates = [v for v in data["videos"] if v["upload_date"]]
    latest_title = ""
    if with_dates:
        latest = max(with_dates, key=lambda v: v["upload_date"])
        latest_title = latest["title"]

    # ── Tentukan kategori ──────────────────────────────────────────────────
    # Daily: upload di SETIAP hari dalam window (semua hari terisi)
    if unique_days >= window:
        category = CAT_DAILY

    # Active: ada streak berturut-turut minimal ACTIVE_STREAK_MIN hari
    elif streak >= ACTIVE_STREAK_MIN:
        category = CAT_ACTIVE

    # Occasional: upload 2 hari tapi tidak mencapai streak minimum
    elif unique_days == 2:
        category = CAT_OCCASIONAL

    # Rarely: hanya 1 hari upload dalam window
    elif unique_days == 1:
        category = CAT_RARELY

    # Inactive: tidak ada upload sama sekali
    else:
        category = CAT_INACTIVE

    return {
        **data,
        "category":    category,
        "unique_days": unique_days,
        "max_streak":  streak,
        "uploads_w":   uploads_w,
        "last_upload": last_upload,
        "latest_title": latest_title,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  REPORT HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def cat_order(cat: str) -> int:
    return {CAT_DAILY: 0, CAT_ACTIVE: 1, CAT_OCCASIONAL: 2,
            CAT_RARELY: 3, CAT_INACTIVE: 4, CAT_ERROR: 5}.get(cat, 99)


def fmt_date(d) -> str:
    return d.strftime("%Y-%m-%d") if d else "–"


def sort_group(group: list) -> list:
    """Sort dalam satu group: lebih banyak streak dulu, lalu nama."""
    return sorted(group, key=lambda r: (
        -r.get("max_streak", 0),
        -r.get("unique_days", 0),
        (r.get("name") or "").lower()
    ))


# ══════════════════════════════════════════════════════════════════════════════
#  GENERATE MARKDOWN
# ══════════════════════════════════════════════════════════════════════════════
def generate_md(results: list, window: int, source_file: str) -> str:
    total  = len(results)
    counts = {c: sum(1 for r in results if r["category"] == c) for c in ALL_CATS}

    scan_start = (TODAY - timedelta(days=window)).strftime("%Y-%m-%d")

    lines = [
        "# 📊 YouTube Shorts — Channel Activity Report",
        "",
        "| | |",
        "|---|---|",
        f"| **Generated** | {NOW_TS} |",
        f"| **Source** | `{source_file}` |",
        f"| **Scan Window** | `{scan_start}` → `{TODAY_STR}` ({window} hari) |",
        f"| **Total Channels** | {total} |",
        f"| **Fetch per Channel** | {FETCH_PER_CHANNEL} video terbaru |",
        "",
        "---",
        "",
        "## 📈 Summary",
        "",
        "| Kategori | Jumlah | Keterangan |",
        "|----------|--------|------------|",
        f"| {CAT_DAILY}      | **{counts[CAT_DAILY]}** | Upload **setiap hari** ({window}/{window} hari) |",
        f"| {CAT_ACTIVE}     | **{counts[CAT_ACTIVE]}** | Streak **{ACTIVE_STREAK_MIN}–{ACTIVE_STREAK_MAX} hari** berturut-turut |",
        f"| {CAT_OCCASIONAL} | **{counts[CAT_OCCASIONAL]}** | Upload **2 hari** (tidak berturut-turut) |",
        f"| {CAT_RARELY}     | **{counts[CAT_RARELY]}** | Upload **hanya 1 hari** dalam {window} hari |",
        f"| {CAT_INACTIVE}   | **{counts[CAT_INACTIVE]}** | **Tidak ada upload** dalam {window} hari |",
        f"| {CAT_ERROR}      | **{counts[CAT_ERROR]}** | Gagal fetch (yt-dlp & pytube) |",
        "",
    ]

    sections = [
        (CAT_DAILY,      "🔥 Daily Uploaders",
         f"Upload **setiap hari** selama {window} hari terakhir — konsistensi tertinggi"),
        (CAT_ACTIVE,     "✅ Active Channels",
         f"Punya streak upload **{ACTIVE_STREAK_MIN}–{ACTIVE_STREAK_MAX} hari berturut-turut** dalam {window} hari terakhir"),
        (CAT_OCCASIONAL, "⚠️ Occasional Channels",
         f"Upload di **2 hari** dalam {window} hari terakhir, tapi tidak berurutan"),
        (CAT_RARELY,     "📉 Rarely Active",
         f"Upload hanya **1 hari** dalam {window} hari terakhir"),
        (CAT_INACTIVE,   "❌ Inactive Channels",
         f"**Tidak ada upload** sama sekali dalam {window} hari terakhir"),
        (CAT_ERROR,      "⛔ Fetch Errors",
         "Gagal diambil oleh **yt-dlp** maupun **pytube**"),
    ]

    for cat, heading, desc in sections:
        group = sort_group([r for r in results if r["category"] == cat])
        if not group:
            continue

        lines += ["---", "", f"## {heading}", "", f"*{desc}*", ""]

        if cat == CAT_ERROR:
            lines += [
                "| # | Channel | Error | Method |",
                "|---|---------|-------|--------|",
            ]
            for i, r in enumerate(group, 1):
                name  = (r.get("name") or short_label(r["url"]))[:35]
                err   = (r.get("error") or "Unknown")[:80]
                meth  = r.get("method", "–")
                url_s = f"[{short_label(r['url'])}]({r['url']})"
                lines.append(f"| {i} | {name} / {url_s} | {err} | `{meth}` |")
        else:
            lines += [
                f"| # | Channel | Last Upload | Streak | Days/{window}d | Uploads | Method | Latest Short |",
                f"|---|---------|-------------|--------|--------|---------|--------|--------------|",
            ]
            for i, r in enumerate(group, 1):
                name   = (r.get("name") or short_label(r["url"]))[:30]
                url_s  = f"[{short_label(r['url'])}]({r['url']})"
                last_u = fmt_date(r.get("last_upload"))
                streak = r.get("max_streak", 0)
                days   = r.get("unique_days", 0)
                upl    = r.get("uploads_w", 0)
                meth   = r.get("method", "–")
                title  = (r.get("latest_title") or "")[:50]
                if len(r.get("latest_title") or "") > 50:
                    title += "…"
                streak_disp = f"**{streak}d**" if streak >= ACTIVE_STREAK_MIN else f"{streak}d"
                lines.append(
                    f"| {i} | [{name}]({r['url']}) {url_s} | {last_u} | {streak_disp} | {days}/{window} | {upl} | `{meth}` | {title} |"
                )
        lines.append("")

    lines += [
        "---",
        "",
        f"> *Report ini di-generate oleh `check_channel_activity.py`*  ",
        f"> *Window: {window} hari terakhir | Active streak threshold: ≥{ACTIVE_STREAK_MIN} hari | {NOW_TS}*",
        "",
    ]
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
#  GENERATE PLAIN TEXT
# ══════════════════════════════════════════════════════════════════════════════
def generate_txt(results: list, window: int, source_file: str) -> str:
    total  = len(results)
    counts = {c: sum(1 for r in results if r["category"] == c) for c in ALL_CATS}
    scan_start = (TODAY - timedelta(days=window)).strftime("%Y-%m-%d")

    sep    = "=" * 82
    subsep = "-" * 82

    lines = [
        sep,
        "  YouTube Shorts — Channel Activity Report".center(82),
        sep,
        f"  Generated  : {NOW_TS}",
        f"  Source     : {source_file}",
        f"  Scan Range : {scan_start} → {TODAY_STR}  ({window} hari)",
        f"  Channels   : {total}",
        f"  Active def : streak ≥ {ACTIVE_STREAK_MIN} hari berturut-turut",
        subsep,
        "  SUMMARY",
        subsep,
        f"  {CAT_DAILY:<26} : {counts[CAT_DAILY]:>4}   (upload {window}/{window} hari)",
        f"  {CAT_ACTIVE:<26} : {counts[CAT_ACTIVE]:>4}   (streak {ACTIVE_STREAK_MIN}-{ACTIVE_STREAK_MAX} hari berturut)",
        f"  {CAT_OCCASIONAL:<26} : {counts[CAT_OCCASIONAL]:>4}   (upload 2 hari, tidak berturut)",
        f"  {CAT_RARELY:<26} : {counts[CAT_RARELY]:>4}   (hanya 1 hari upload)",
        f"  {CAT_INACTIVE:<26} : {counts[CAT_INACTIVE]:>4}   (0 upload dalam {window} hari)",
        f"  {CAT_ERROR:<26} : {counts[CAT_ERROR]:>4}   (gagal fetch)",
        "",
    ]

    sections = [
        (CAT_DAILY,      f"DAILY  [{window}/{window} hari upload]"),
        (CAT_ACTIVE,     f"ACTIVE  [streak {ACTIVE_STREAK_MIN}-{ACTIVE_STREAK_MAX} hari berturut-turut]"),
        (CAT_OCCASIONAL, "OCCASIONAL  [2 hari, tidak berurutan]"),
        (CAT_RARELY,     "RARELY  [1 hari saja dalam window]"),
        (CAT_INACTIVE,   f"INACTIVE  [0 upload dalam {window} hari]"),
        (CAT_ERROR,      "FETCH ERRORS"),
    ]

    for cat, heading in sections:
        group = sort_group([r for r in results if r["category"] == cat])
        if not group:
            continue

        lines += [subsep, f"  {heading}", subsep]

        for i, r in enumerate(group, 1):
            name   = (r.get("name") or short_label(r["url"]))[:34]
            meth   = r.get("method", "–")

            if cat == CAT_ERROR:
                err = (r.get("error") or "Unknown")[:72]
                lines.append(f"  {i:>3}. {name:<36}")
                lines.append(f"       URL   : {r['url']}")
                lines.append(f"       Error : {err}")
                lines.append(f"       Via   : {meth}")
            else:
                last_u = fmt_date(r.get("last_upload"))
                streak = r.get("max_streak", 0)
                days   = r.get("unique_days", 0)
                upl    = r.get("uploads_w", 0)
                title  = (r.get("latest_title") or "")[:48]
                lines.append(
                    f"  {i:>3}. {name:<36} streak:{streak:>2}d | {days}/{window}hari | "
                    f"upload:{upl:>2} | last:{last_u} | [{meth}]"
                )
                lines.append(f"       URL    : {r['url']}")
                if title:
                    lines.append(f"       Latest : {title}")
            lines.append("")

    lines += [sep, f"  End of report — {NOW_TS}", sep, ""]
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════
def main():
    if not SHORT_LINK.exists():
        print(f"[ERROR] File tidak ditemukan: {SHORT_LINK}")
        sys.exit(1)

    # Print konfigurasi yang aktif
    print()
    print("=" * 62)
    print("  YouTube Shorts — Channel Activity Checker")
    print("=" * 62)
    print(f"  Input      : {INPUT_FILE}")
    print(f"  Window     : {SCAN_WINDOW_DAYS} hari ke belakang (dari hari ini)")
    print(f"  Daily      : upload setiap hari ({SCAN_WINDOW_DAYS}/{SCAN_WINDOW_DAYS})")
    print(f"  Active     : streak ≥{ACTIVE_STREAK_MIN} hari berturut-turut")
    print(f"  Occasional : upload 2 hari (tidak streak)")
    print(f"  Rarely     : upload 1 hari saja")
    print(f"  Scan       : {FETCH_PER_CHANNEL} video terbaru per channel (early-stop otomatis)")
    print(f"               Playlist diurutkan terbaru→lama: scan berhenti saat video > {SCAN_WINDOW_DAYS} hari")
    print(f"  Fallback   : yt-dlp → pytube (otomatis, error disembunyikan dari konsol)")
    if CHANNEL_LIMIT:
        print(f"  [TEST MODE]: hanya {CHANNEL_LIMIT} channel pertama")
    print()

    # Load URLs
    urls = load_urls(SHORT_LINK)
    if CHANNEL_LIMIT:
        urls = urls[: CHANNEL_LIMIT]

    scan_start = (TODAY - timedelta(days=SCAN_WINDOW_DAYS)).strftime("%Y-%m-%d")
    print(f"  ✔ {len(urls)} channel ditemukan")
    print(f"  Scan range : {scan_start} → {TODAY_STR}")
    print()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── Fetch + Analyse ──────────────────────────────────────────────────────
    results = []
    for i, url in enumerate(progress_iter(urls, desc="Scanning"), 1):
        if not _TQDM:
            label = short_label(url)
            print(f"  [{i:>3}/{len(urls)}] {label:<38}", end="\r", flush=True)

        raw  = fetch_channel(url, FETCH_PER_CHANNEL)
        data = analyse(raw, SCAN_WINDOW_DAYS)
        results.append(data)

    if not _TQDM:
        print(" " * 65, end="\r")

    # Sort: best category first, then streak desc, then name
    results.sort(key=lambda r: (
        cat_order(r["category"]),
        -r.get("max_streak", 0),
        (r.get("name") or "").lower()
    ))

    # ── Generate & save ──────────────────────────────────────────────────────
    md_content  = generate_md(results, SCAN_WINDOW_DAYS, INPUT_FILE)
    txt_content = generate_txt(results, SCAN_WINDOW_DAYS, INPUT_FILE)

    md_path  = OUTPUT_DIR / f"channel_activity_{TODAY_STR}.md"
    txt_path = OUTPUT_DIR / f"channel_activity_{TODAY_STR}.txt"

    md_path.write_text(md_content,  encoding="utf-8")
    txt_path.write_text(txt_content, encoding="utf-8")

    # ── Ringkasan konsol ─────────────────────────────────────────────────────
    counts = {c: sum(1 for r in results if r["category"] == c) for c in ALL_CATS}

    print()
    print("=" * 62)
    print("  HASIL SCAN")
    print("=" * 62)
    for c in ALL_CATS:
        bar  = ("█" * min(counts[c], 40))
        print(f"  {c:<26} : {counts[c]:>3}  {bar}")

    # Preview Daily
    daily = [r for r in results if r["category"] == CAT_DAILY]
    if daily:
        print()
        print(f"  🔥 Daily ({len(daily)} channel — upload SETIAP hari):")
        for r in daily:
            name   = (r.get("name") or short_label(r["url"]))[:40]
            streak = r.get("max_streak", 0)
            last_u = fmt_date(r.get("last_upload"))
            print(f"    - {name:<42} streak:{streak}d  last:{last_u}")

    # Preview Active
    active = [r for r in results if r["category"] == CAT_ACTIVE]
    if active:
        print()
        print(f"  ✅ Active ({len(active)} channel — streak ≥{ACTIVE_STREAK_MIN} hari):")
        for r in active[:10]:
            name   = (r.get("name") or short_label(r["url"]))[:40]
            streak = r.get("max_streak", 0)
            last_u = fmt_date(r.get("last_upload"))
            print(f"    - {name:<42} streak:{streak}d  last:{last_u}")
        if len(active) > 10:
            print(f"    ... dan {len(active) - 10} lainnya (lihat report)")

    # Error summary
    errors = [r for r in results if r["category"] == CAT_ERROR]
    if errors:
        print()
        print(f"  ⛔ {len(errors)} channel gagal di-fetch (lihat report untuk detail)")

    print()
    print("  📄 Report tersimpan di:")
    print(f"     {md_path}")
    print(f"     {txt_path}")
    print()


if __name__ == "__main__":
    main()
