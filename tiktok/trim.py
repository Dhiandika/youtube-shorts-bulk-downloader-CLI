# filter_video_fast_fixed.py
# - Hapus video > 60s
# - Jika gagal baca durasi (corrupt/ffmpeg issue), HAPUS juga
# - Multithreading untuk percepat proses
# - Hapus .txt berpasangan
# - Rename ulang berurutan 01.ext, 02.ext, ...
# Kompatibel MoviePy 2.2.1

import os
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from moviepy import VideoFileClip

# ========= KONFIGURASI =========
FOLDER = Path("tiktok_downloads")                # jalankan script dari dalam folder video
MAX_DURATION = 60.0               # detik
VIDEO_EXTS = (".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v")
MAX_WORKERS = min(32, (os.cpu_count() or 4) * 4)  # I/O bound -> banyak thread OK
# ===============================


def is_video(p: Path) -> bool:
    return p.is_file() and p.suffix.lower() in VIDEO_EXTS


def remove_with_txt(p: Path) -> None:
    """Hapus file video dan txt pasangan jika ada."""
    try:
        if p.exists():
            p.unlink()
    except Exception as e:
        print(f"  ! Gagal hapus video: {p.name} -> {e}")
    txt = p.with_suffix(".txt")
    if txt.exists():
        try:
            txt.unlink()
        except Exception as e:
            print(f"  ! Gagal hapus txt: {txt.name} -> {e}")


def get_duration(path: Path) -> float:
    """Ambil durasi via MoviePy v2.x (pakai context manager)."""
    with VideoFileClip(str(path)) as clip:
        # clip.duration bisa None pada file rusak
        return float(clip.duration or 0.0)


def process_one(path: Path):
    """
    Proses satu file.
    Return tuple: ('kept'|'deleted_dur'|'deleted_err', name, duration_or_None, error_or_None)
    """
    try:
        dur = get_duration(path)
        if dur > MAX_DURATION:
            remove_with_txt(path)
            return ("deleted_dur", path.name, dur, None)
        return ("kept", path.name, dur, None)
    except Exception as e:
        remove_with_txt(path)
        return ("deleted_err", path.name, None, str(e))


def rename_sequential(folder: Path) -> list[str]:
    """Rename sisa video menjadi 01.ext, 02.ext, ... (hindari tabrakan nama)."""
    survivors = sorted([p for p in folder.iterdir() if is_video(p)], key=lambda x: x.name.lower())

    # Rename sementara agar tidak bentrok
    tmp_paths: list[Path] = []
    for i, p in enumerate(survivors):
        tmp = p.with_name(f"__TMP__{i}{p.suffix.lower()}")
        try:
            p.rename(tmp)
            tmp_paths.append(tmp)
        except Exception as e:
            print(f"! Gagal rename sementara: {p.name} -> {e}")

    final_names: list[str] = []
    for idx, tmp in enumerate(sorted(tmp_paths, key=lambda x: x.name.lower()), start=1):
        final = tmp.with_name(f"{idx:02d}{tmp.suffix.lower()}")
        try:
            tmp.rename(final)
            final_names.append(final.name)
        except Exception as e:
            print(f"! Gagal rename final: {tmp.name} -> {e}")

    return final_names


def main() -> None:
    all_videos = sorted([p for p in FOLDER.iterdir() if is_video(p)], key=lambda x: x.name.lower())
    total_awal = len(all_videos)
    if total_awal == 0:
        print("Tidak ada file video yang cocok di folder ini.")
        return

    print(f"Memproses {total_awal} video dengan {MAX_WORKERS} threads...\n")

    kept_count = 0
    deleted_dur = 0
    deleted_err = 0

    # Multithreading
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as exe:
        futures = {exe.submit(process_one, p): p for p in all_videos}
        for fut in as_completed(futures):
            status, name, dur, err = fut.result()
            if status == "kept":
                kept_count += 1
                print(f"AMAN   : {name} ({dur:.2f}s)")
            elif status == "deleted_dur":
                deleted_dur += 1
                print(f"HAPUS  : {name} (> {MAX_DURATION:.0f}s, dur={dur:.2f}s)")
            else:
                deleted_err += 1
                print(f"ERROR* : {name} -> dihapus. Alasan: {err}")

    # Rename berurutan
    final_names = rename_sequential(FOLDER)

    print("\n==== RINGKASAN ====")
    print(f"Total awal             : {total_awal}")
    print(f"Tersisa (akhir)        : {len(final_names)}")
    print(f"Dihapus karena durasi  : {deleted_dur}")
    print(f"Dihapus karena error   : {deleted_err}")
    if final_names:
        contoh = ", ".join(final_names[:5])
        print(f"Contoh nama akhir      : {contoh}{' ...' if len(final_names) > 5 else ''}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nDibatalkan pengguna.")
        sys.exit(1)
