#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
prune_by_duration.py
- Scan folder video (default: tiktok_downloads)
- Simpan video dengan durasi <= MAX_DURATION_SECONDS
- Hapus video dengan durasi > MAX_DURATION_SECONDS + caption .txt (nama sama)
- Tanpa CLI; semua pengaturan di CONFIG.
"""

import os
import sys
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional, Tuple

# =========================
# CONFIG — ubah di sini
# =========================
CONFIG = {
    # Folder yang berisi video & caption .txt
    "FOLDER": "tiktok_downloads",

    # Ekstensi video yang akan diproses
    "VIDEO_EXTS": [".mp4", ".webm", ".mkv", ".mov"],

    # Batas durasi aman (detik). > batas → dihapus
    "MAX_DURATION_SECONDS": 120,  # 2 menit

    # Pencarian rekursif ke subfolder?
    "RECURSIVE": False,

    # Jika durasi gagal didapat (ffprobe error), apakah dianggap aman (keep)?
    "KEEP_IF_DURATION_UNKNOWN": True,

    # Jalankan tanpa benar-benar menghapus file (simulasi)?
    "DRY_RUN": False,

    # Paralelisasi pengukuran durasi
    "WORKERS": 8,

    # Tulis laporan ke CSV? (None = tidak)
    "REPORT_CSV": None,  # misal: "prune_report.csv"
}
# =========================


def check_ffprobe() -> bool:
    try:
        subprocess.run(
            ["ffprobe", "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
            text=True,
        )
        return True
    except Exception:
        return False


def get_video_duration_seconds(filepath: str) -> Optional[int]:
    """Ambil durasi video (detik) dengan ffprobe. None jika gagal."""
    if not os.path.exists(filepath):
        return None
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        filepath,
    ]
    try:
        r = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=60,
            encoding="utf-8",
            errors="replace",
        )
        if r.returncode != 0:
            return None
        s = r.stdout.strip()
        if not s:
            return None
        return int(round(float(s)))
    except Exception:
        return None


def find_videos(folder: str, exts: List[str], recursive: bool) -> List[str]:
    exts = [e.lower() for e in exts]
    files = []
    if recursive:
        for root, _, names in os.walk(folder):
            for n in names:
                if os.path.splitext(n)[1].lower() in exts:
                    files.append(os.path.join(root, n))
    else:
        for n in os.listdir(folder):
            p = os.path.join(folder, n)
            if os.path.isfile(p) and os.path.splitext(n)[1].lower() in exts:
                files.append(p)
    return files


def delete_file(path: str, dry_run: bool) -> bool:
    if not path or not os.path.exists(path):
        return False
    if dry_run:
        return True
    try:
        os.remove(path)
        return True
    except Exception:
        return False


def base_stem(path: str) -> str:
    """Nama file tanpa ekstensi, utuh (bisa mengandung ' - ' sesuai pola)."""
    return os.path.splitext(os.path.basename(path))[0]


def process_folder():
    folder = CONFIG["FOLDER"]
    if not os.path.exists(folder):
        print(f"Folder tidak ditemukan: {folder}")
        return

    if not check_ffprobe():
        print("ffprobe tidak ditemukan di PATH. Instal ffmpeg/ffprobe terlebih dulu.")
        return

    video_paths = find_videos(folder, CONFIG["VIDEO_EXTS"], CONFIG["RECURSIVE"])
    if not video_paths:
        print("Tidak ada file video yang cocok di folder.")
        return

    print(f"Ditemukan {len(video_paths)} file video. Mengukur durasi (workers={CONFIG['WORKERS']}) ...")

    durations = {}
    with ThreadPoolExecutor(max_workers=CONFIG["WORKERS"]) as ex:
        futs = {ex.submit(get_video_duration_seconds, p): p for p in video_paths}
        for i, fut in enumerate(as_completed(futs), 1):
            p = futs[fut]
            d = fut.result()
            durations[p] = d
            if i % 20 == 0 or i == len(video_paths):
                print(f"  progress: {i}/{len(video_paths)}")

    limit = CONFIG["MAX_DURATION_SECONDS"]
    dry_run = CONFIG["DRY_RUN"]
    keep_if_unknown = CONFIG["KEEP_IF_DURATION_UNKNOWN"]

    kept, deleted, unknown = 0, 0, 0
    rows_for_csv: List[Tuple[str, Optional[int], str]] = []

    print("\nEvaluasi & tindakan:")
    print("-" * 80)

    for vp in sorted(video_paths):
        dur = durations.get(vp)
        stem = base_stem(vp)
        caption_path = os.path.join(os.path.dirname(vp), f"{stem}.txt")

        action = ""
        if dur is None:
            unknown += 1
            if keep_if_unknown:
                kept += 1
                action = "KEEP (durasi tidak diketahui)"
            else:
                # treat unknown as delete?
                action = f"DELETE (durasi tidak diketahui > dianggap > {limit}s)"
                # hapus video + caption
                ok_v = delete_file(vp, dry_run)
                ok_c = delete_file(caption_path, dry_run)
                deleted += 1 if ok_v else 0
        else:
            if dur > limit:
                action = f"DELETE ({dur}s > {limit}s)"
                ok_v = delete_file(vp, dry_run)
                ok_c = delete_file(caption_path, dry_run)
                deleted += 1 if ok_v else 0
            else:
                kept += 1
                action = f"KEEP ({dur}s <= {limit}s)"

        print(f"{os.path.basename(vp)}  -> {action}")
        rows_for_csv.append((vp, dur, action))

    print("\nRINGKASAN")
    print("-" * 80)
    print(f"Total   : {len(video_paths)}")
    print(f"Kept    : {kept}")
    print(f"Deleted : {deleted}{' (DRY-RUN: tidak benar-benar dihapus)' if dry_run else ''}")
    print(f"Unknown : {unknown} (durasi tidak terbaca)")

    # optional report CSV
    if CONFIG["REPORT_CSV"]:
        try:
            import csv
            with open(CONFIG["REPORT_CSV"], "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["video_path", "duration_seconds", "action"])
                for row in rows_for_csv:
                    w.writerow(row)
            print(f"\nReport CSV: {CONFIG['REPORT_CSV']}")
        except Exception as e:
            print(f"Gagal menulis CSV: {e}")


if __name__ == "__main__":
    try:
        process_folder()
    except KeyboardInterrupt:
        print("\nDibatalkan oleh pengguna.")
