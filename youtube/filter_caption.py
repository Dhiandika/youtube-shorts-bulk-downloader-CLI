"""
filter_caption.py
=================
Filter video berdasarkan isi caption .txt, lalu hapus pasangan .txt + video.

Format .txt yang didukung:
    <judul video>

    YouTube: <nama channel>
    Link: https://www.youtube.com/watch?v=xxxxx

    #hashtag1 #hashtag2 ...

Nama file .txt SAMA dengan nama file video (hanya beda ekstensi).
Contoh:
    01 - Nerissa_and_Raora_BROKE_... - Average_VTuber_Enjoyer.txt
    01 - Nerissa_and_Raora_BROKE_... - Average_VTuber_Enjoyer.mp4

Cara kerja:
  1. Scan folder → baca semua .txt
  2. Terapkan filter (bahasa & keyword)
  3. Tampilkan daftar file yang cocok (preview + kelompok)
  4. Tanya konfirmasi user
  5. Hapus .txt + pasangan video (.mp4 / .mkv / .webm)
"""

# ══════════════════════════════════════════════════════════════════════════════
#  ⚙️  KONFIGURASI — Edit bagian ini
# ══════════════════════════════════════════════════════════════════════════════

# Folder yang akan di-scan (relatif dari lokasi script ini)
# Contoh: "new_week/1080x1920"  atau  "downloads"
SCAN_FOLDER: str = "./new_week/1080x1920"

# ── Filter Bahasa ─────────────────────────────────────────────────────────────
# Aktifkan deteksi bahasa Indonesia penuh.
# True  = hapus file yang caption-nya terdeteksi full Bahasa Indonesia
# False = skip filter bahasa
FILTER_INDONESIAN: bool = False

# Sensitivitas deteksi bahasa Indonesia (0.0 – 1.0)
# Makin tinggi = makin ketat (hanya yang benar-benar full BI)
# Rekomendasi: 0.7 untuk balance, 0.9 untuk sangat ketat
LANG_CONFIDENCE: float = 0.9

# ── Filter Kata Kunci ─────────────────────────────────────────────────────────
# Daftar kata kunci. Kosongkan list jika tidak ingin filter keyword.
# Pencarian CASE-INSENSITIVE.
# Contoh: ["graduation", "goodbye", "yagoo", "gen 7"]
FILTER_KEYWORDS: list = [
    "Outfit ",
    "goodbye",
    "tranformation ",
    "fauna ",
    "Dad",
    "Pokémon ",
    "Pokemon",
    "Debut",
    "Ina ",
    "animal ",
    "Gura ",
    "Ame ",
    "Sana ",
    "Graduating ",
    "Announcement ",
    "SENZAWA ",
    "Mumei ",
    "tapir",
    "Bald ",
    "Paparissa ",
    "song",
    "sing",
    "Singing",
    "brother",
    "RTX ",
    "full bahasa indonesia",
]

# Mode pencocokan keyword:
# "ANY" = cukup satu keyword cocok → masuk filter
# "ALL" = harus semua keyword cocok → masuk filter
KEYWORD_MODE: str = "ANY"

# Bagian caption yang di-cek untuk keyword:
# "title"   = hanya baris pertama (judul)
# "full"    = seluruh isi txt (judul + YouTube + link + hashtag)
KEYWORD_SEARCH_IN: str = "full"

# ── Ekstensi video yang dicari pasangannya ────────────────────────────────────
VIDEO_EXTENSIONS: list = [".mp4", ".mkv", ".webm", ".avi", ".mov"]

# ══════════════════════════════════════════════════════════════════════════════
#  JANGAN UBAH DI BAWAH INI
# ══════════════════════════════════════════════════════════════════════════════

import os
import sys
import re
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
TARGET_DIR = SCRIPT_DIR / SCAN_FOLDER


# ── Deteksi bahasa (langdetect opsional) ──────────────────────────────────────
def _detect_lang(text: str) -> tuple:
    """
    Deteksi bahasa dari teks.
    Return: (lang_code: str, confidence: float)
    Coba langdetect dulu, fallback ke deteksi manual kata Indonesia.
    """
    # Metode 1: langdetect
    try:
        from langdetect import detect_langs
        results = detect_langs(text)
        if results:
            top = results[0]
            return top.lang, round(top.prob, 3)
    except ImportError:
        pass  # langdetect tidak terinstall, pakai fallback
    except Exception:
        pass

    # Metode 2: Fallback — hitung proporsi kata Indonesia umum
    INDO_WORDS = {
        "dan", "yang", "di", "ke", "dari", "dengan", "ini", "itu",
        "adalah", "pada", "untuk", "dalam", "tidak", "ada", "akan",
        "juga", "saya", "kamu", "dia", "mereka", "kita", "kami",
        "sudah", "belum", "bisa", "harus", "mau", "karena", "tapi",
        "atau", "jika", "kalau", "seperti", "lagi", "masih", "sudah",
        "nya", "nya", "aku", "mu", "ku", "sih", "lah", "kan", "deh",
        "dong", "nih", "aja", "gimana", "kenapa", "kapan", "siapa",
        "bagaimana", "mengapa", "dimana", "ketika", "setelah", "sambil",
        "mulai", "pagi", "malam", "siang", "hari", "bulan", "tahun",
        "baru", "lama", "besar", "kecil", "baik", "buruk", "senang",
        "sedih", "lucu", "maka", "namun", "tetapi", "namun", "sebelum",
    }
    words = re.findall(r'\b[a-zA-Z]+\b', text.lower())
    if not words:
        return "unknown", 0.0
    indo_count = sum(1 for w in words if w in INDO_WORDS)
    confidence = round(indo_count / len(words), 3) if words else 0.0
    lang = "id" if confidence >= 0.15 else "en"
    return lang, confidence


# ── Parse caption txt ─────────────────────────────────────────────────────────
def parse_caption(txt_path: Path) -> dict:
    """
    Baca .txt dan extract komponen:
      title, youtube_channel, link, hashtags, full_text
    """
    try:
        text = txt_path.read_text(encoding="utf-8", errors="replace").strip()
    except Exception:
        return {"title": "", "youtube": "", "link": "", "hashtags": "", "full": ""}

    lines = [l.strip() for l in text.splitlines()]

    title      = ""
    youtube_ch = ""
    link       = ""
    hashtags   = ""

    for i, line in enumerate(lines):
        if not title and line and not line.startswith("#") \
                and not line.lower().startswith("youtube:") \
                and not line.lower().startswith("link:"):
            title = line
        elif line.lower().startswith("youtube:"):
            youtube_ch = line.split(":", 1)[-1].strip()
        elif line.lower().startswith("link:"):
            link = line.split(":", 1)[-1].strip()
        elif line.startswith("#"):
            hashtags = line

    return {
        "title":    title,
        "youtube":  youtube_ch,
        "link":     link,
        "hashtags": hashtags,
        "full":     text,
    }


# ── Cari pasangan video ───────────────────────────────────────────────────────
def find_video_pair(txt_path: Path) -> Path | None:
    """Cari file video dengan nama sama (beda ekstensi)."""
    stem = txt_path.stem
    for ext in VIDEO_EXTENSIONS:
        candidate = txt_path.parent / (stem + ext)
        if candidate.exists():
            return candidate
    return None


# ── Cek apakah file cocok dengan filter ──────────────────────────────────────
def matches_filter(caption: dict) -> tuple:
    """
    Return: (matched: bool, reasons: list[str])
    """
    reasons = []

    # ── Filter bahasa Indonesia
    if FILTER_INDONESIAN:
        # Cek title + body (exclude hashtag agar tidak bias)
        check_text = caption["title"] + " " + caption["full"]
        # Hilangkan hashtags dari pengecekan bahasa
        check_text = re.sub(r"#\S+", "", check_text).strip()
        if check_text:
            lang, conf = _detect_lang(check_text)
            if lang == "id" and conf >= LANG_CONFIDENCE:
                reasons.append(f"Bahasa Indonesia (conf: {conf:.0%})")

    # ── Filter keyword
    if FILTER_KEYWORDS:
        search_text = caption["full"] if KEYWORD_SEARCH_IN == "full" else caption["title"]
        search_text = search_text.lower()
        matched_kw  = [kw for kw in FILTER_KEYWORDS if kw.lower() in search_text]

        if KEYWORD_MODE.upper() == "ALL":
            if len(matched_kw) == len(FILTER_KEYWORDS):
                kw_list = ", ".join(f'"{k}"' for k in matched_kw)
                reasons.append(f"Keyword cocok: {kw_list}")
        else:  # ANY
            if matched_kw:
                kw_list = ", ".join(f'"{k}"' for k in matched_kw)
                reasons.append(f"Keyword cocok: {kw_list}")

    return bool(reasons), reasons


# ── Tampilkan ringkasan kelompok ──────────────────────────────────────────────
def group_by_reason(matches: list) -> dict:
    """Kelompokkan hasil match berdasarkan alasan filter."""
    groups: dict = {}
    for item in matches:
        for reason_type in item["reasons"]:
            # Ambil prefix reason (sebelum '(')
            key = reason_type.split("(")[0].strip()
            groups.setdefault(key, []).append(item)
    return groups


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    print()
    print("=" * 65)
    print("  Caption Filter — Hapus Video Berdasarkan Isi Caption")
    print("=" * 65)
    print(f"  Folder scan    : {TARGET_DIR}")
    print(f"  Filter bahasa  : {'Indonesia (langdetect/fallback)' if FILTER_INDONESIAN else 'Tidak aktif'}")
    print(f"  Filter keyword : {FILTER_KEYWORDS if FILTER_KEYWORDS else 'Tidak aktif'}")
    if FILTER_KEYWORDS:
        print(f"  Keyword mode   : {KEYWORD_MODE} (semua harus cocok)" if KEYWORD_MODE == "ALL" \
              else f"  Keyword mode   : {KEYWORD_MODE} (cukup satu cocok)")
        print(f"  Cari di        : {'Seluruh teks' if KEYWORD_SEARCH_IN == 'full' else 'Judul saja'}")
    print()

    # Validasi konfigurasi
    if not FILTER_INDONESIAN and not FILTER_KEYWORDS:
        print("  ⚠️  Tidak ada filter aktif!")
        print("  → Set FILTER_INDONESIAN = True  dan/atau isi FILTER_KEYWORDS")
        sys.exit(0)

    if not TARGET_DIR.exists():
        print(f"  ❌ Folder tidak ditemukan: {TARGET_DIR}")
        sys.exit(1)

    # Cari semua .txt
    txt_files = sorted(TARGET_DIR.rglob("*.txt"))
    if not txt_files:
        print(f"  ❌ Tidak ada file .txt di {TARGET_DIR}")
        sys.exit(0)

    print(f"  📂 Ditemukan {len(txt_files)} file .txt di folder tersebut")
    print(f"  🔍 Sedang scan dan filter...\n")

    # ── Scan & apply filter ────────────────────────────────────────────────────
    matches   = []
    no_match  = 0
    no_pair   = []

    for i, txt_path in enumerate(txt_files, 1):
        print(f"  [{i:>3}/{len(txt_files)}] {txt_path.name[:60]}", end="\r", flush=True)

        caption   = parse_caption(txt_path)
        matched, reasons = matches_filter(caption)

        if matched:
            video_pair = find_video_pair(txt_path)
            matches.append({
                "txt":     txt_path,
                "video":   video_pair,
                "caption": caption,
                "reasons": reasons,
            })
            if not video_pair:
                no_pair.append(txt_path.name)
        else:
            no_match += 1

    print(" " * 70, end="\r")  # clear progress line

    # ── Hasil scan ─────────────────────────────────────────────────────────────
    if not matches:
        print("  ✅ Tidak ada file yang cocok dengan filter yang aktif.")
        print(f"  ({no_match} file tidak cocok)\n")
        return

    # Kelompokkan berdasarkan alasan
    groups = group_by_reason(matches)

    print(f"  ⚠️  Ditemukan {len(matches)} file yang cocok dengan filter:\n")
    print("=" * 65)

    for group_name, items in groups.items():
        print(f"\n  📁 [{group_name}] — {len(items)} file")
        print(f"  {'─' * 61}")
        for idx, item in enumerate(items, 1):
            title    = (item["caption"]["title"] or item["txt"].stem)[:58]
            youtube  = item["caption"]["youtube"] or "?"
            video_ok = f"✓ {item['video'].suffix}" if item["video"] else "✗ no video"
            reason   = " | ".join(item["reasons"])
            print(f"  {idx:>3}. {title}")
            print(f"       YouTube : {youtube}")
            print(f"       File    : {item['txt'].name}")
            print(f"       Video   : {video_ok}")
            print(f"       Alasan  : {reason}")
            print()

    # Statistik hapus
    txt_count   = len(matches)
    video_count = sum(1 for m in matches if m["video"])
    print("=" * 65)
    print(f"  📊 Total yang akan dihapus:")
    print(f"     • File .txt  : {txt_count}")
    print(f"     • File video : {video_count} (dari total {txt_count} pasangan)")
    if no_pair:
        print(f"     ⚠️  {len(no_pair)} file .txt tidak punya pasangan video:")
        for f in no_pair[:5]:
            print(f"        - {f}")
        if len(no_pair) > 5:
            print(f"        ... dan {len(no_pair) - 5} lainnya")
    print()

    # ── Konfirmasi user ────────────────────────────────────────────────────────
    print("  ⚠️  PERHATIAN: Penghapusan bersifat PERMANEN dan tidak bisa di-undo!")
    print()
    confirm = input(f"  Apakah kamu yakin ingin menghapus {txt_count} file .txt dan {video_count} file video? (ketik 'HAPUS' untuk lanjut): ").strip()

    if confirm != "HAPUS":
        print()
        print("  🚫 Dibatalkan. Tidak ada file yang dihapus.")
        print()
        return

    # ── Hapus file ─────────────────────────────────────────────────────────────
    print()
    deleted_txt   = 0
    deleted_video = 0
    failed        = []

    for item in matches:
        # Hapus .txt
        try:
            item["txt"].unlink()
            deleted_txt += 1
            print(f"  🗑️  Dihapus: {item['txt'].name}")
        except Exception as e:
            failed.append((item["txt"].name, str(e)))
            print(f"  ❌ Gagal hapus txt: {item['txt'].name} — {e}")

        # Hapus video (jika ada)
        if item["video"]:
            try:
                item["video"].unlink()
                deleted_video += 1
                print(f"  🗑️  Dihapus: {item['video'].name}")
            except Exception as e:
                failed.append((item["video"].name, str(e)))
                print(f"  ❌ Gagal hapus video: {item['video'].name} — {e}")

    # ── Ringkasan akhir ─────────────────────────────────────────────────────────
    print()
    print("=" * 65)
    print("  SELESAI")
    print("=" * 65)
    print(f"  ✅ File .txt dihapus  : {deleted_txt}")
    print(f"  ✅ Video dihapus      : {deleted_video}")
    if failed:
        print(f"  ❌ Gagal             : {len(failed)}")
        for fn, err in failed:
            print(f"     - {fn}: {err}")
    print()


if __name__ == "__main__":
    main()
