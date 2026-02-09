
import os
import re
from typing import Dict, List

# ==== KONFIGURASI ====
OUTDIR = "anime_tiktok_downloads_v2"
VIDEO_EXTS = {".mp4", ".webm", ".mkv", ".mov"}  # tambah kalau perlu


# ==== UTIL ====

def is_video(fname: str) -> bool:
    _, ext = os.path.splitext(fname)
    return ext.lower() in VIDEO_EXTS

def is_txt(fname: str) -> bool:
    return fname.lower().endswith(".txt")

def parse_prefixed_name(fname: str):
    """
    Parse 'NNNN - something.ext' → (prefix:int, basename:str, ext:str)
    basename = nama tanpa ekstensi, misalnya:
        '0001 - foo [id].mp4' → (1, 'foo [id]', '.mp4')
    Kalau tidak match, return None.
    """
    m = re.match(r"^(\d{4})\s+-\s+(.*)$", fname)
    if not m:
        return None
    prefix_str, rest = m.groups()
    try:
        prefix = int(prefix_str)
    except ValueError:
        return None
    base, ext = os.path.splitext(rest)
    return prefix, base, ext


# ==== SCAN DAN BERSIH-BERSIH ORPHAN ====

def collect_groups(outdir: str):
    """
    Koleksi semua file bernomor.
    Struktur:
        groups[prefix][base] = {
            "base": base,
            "video_path": ... / None,
            "video_ext": ... / None,
            "txt_path": ... / None,
        }
    Juga mengembalikan:
        max_prefix awal
        counts: (deleted_videos, deleted_txts)
    """
    groups: Dict[int, Dict[str, dict]] = {}
    max_prefix = 0

    # 1) kumpulkan dulu
    for fname in os.listdir(outdir):
        full = os.path.join(outdir, fname)
        if not os.path.isfile(full):
            continue

        parsed = parse_prefixed_name(fname)
        if not parsed:
            continue

        prefix, base, ext = parsed
        if prefix > max_prefix:
            max_prefix = prefix

        if prefix not in groups:
            groups[prefix] = {}

        if base not in groups[prefix]:
            groups[prefix][base] = {
                "base": base,
                "video_path": None,
                "video_ext": None,
                "txt_path": None,
            }

        if is_video(fname):
            groups[prefix][base]["video_path"] = full
            groups[prefix][base]["video_ext"] = ext
        elif is_txt(fname):
            groups[prefix][base]["txt_path"] = full

    # 2) buang orphan (video tanpa txt, txt tanpa video)
    deleted_videos = 0
    deleted_txts = 0

    for prefix, bases in list(groups.items()):
        for base, entry in list(bases.items()):
            vp = entry["video_path"]
            tp = entry["txt_path"]
            has_v = bool(vp)
            has_t = bool(tp)

            # video & txt lengkap → aman
            if has_v and has_t:
                continue

            # video tanpa txt → hapus video
            if has_v and not has_t:
                try:
                    os.remove(vp)
                    deleted_videos += 1
                    print(f"[DEL] Hapus video yatim : {os.path.basename(vp)}")
                except Exception as e:
                    print(f"[WARN] Gagal hapus video {vp}: {e}")
                # hapus entry dari groups
                del bases[base]

            # txt tanpa video → hapus txt
            elif has_t and not has_v:
                try:
                    os.remove(tp)
                    deleted_txts += 1
                    print(f"[DEL] Hapus txt yatim   : {os.path.basename(tp)}")
                except Exception as e:
                    print(f"[WARN] Gagal hapus txt {tp}: {e}")
                # hapus entry dari groups
                del bases[base]

        # kalau untuk prefix ini tidak ada base lagi, hapus prefix dari groups
        if not bases:
            del groups[prefix]

    return groups, max_prefix, deleted_videos, deleted_txts


# ==== PERBAIKI NOMOR DOUBEL ====

def fix_duplicates(outdir: str):
    groups, max_prefix, del_v, del_t = collect_groups(outdir)

    print(f"[INFO] Orphan dibersihkan: {del_v} video, {del_t} txt")

    if not groups:
        print("[INFO] Tidak ada pasangan video+txt bernomor yang tersisa.")
        return

    print(f"[INFO] Prefix terbesar yang ada saat ini: {max_prefix:04d}")
    next_prefix = max_prefix + 1

    # Proses prefix dalam urutan naik
    for prefix in sorted(groups.keys()):
        bases = groups[prefix]
        if len(bases) <= 1:
            # hanya 1 judul untuk prefix ini → tidak ada duplikat nomor
            continue

        print(f"\n[INFO] Prefix {prefix:04d} punya {len(bases)} judul (duplikat nomor).")

        # urutkan base supaya deterministik
        sorted_bases: List[str] = sorted(bases.keys())

        # base pertama dibiarkan memakai prefix lama
        keep_base = sorted_bases[0]
        print(f"  - Mempertahankan {prefix:04d} untuk: {keep_base}")

        # sisanya dipindah ke prefix baru satu per satu
        for b in sorted_bases[1:]:
            entry = bases[b]
            base_name = entry["base"]

            new_prefix = next_prefix
            next_prefix += 1

            # rename video
            if entry["video_path"]:
                v_ext = entry["video_ext"] or ".mp4"
                new_vname = f"{new_prefix:04d} - {base_name}{v_ext}"
                new_vpath = os.path.join(outdir, new_vname)
                print(f"  - {prefix:04d} → {new_prefix:04d} (video)   : {os.path.basename(entry['video_path'])} → {new_vname}")
                os.rename(entry["video_path"], new_vpath)

            # rename txt
            if entry["txt_path"]:
                new_tname = f"{new_prefix:04d} - {base_name}.txt"
                new_tpath = os.path.join(outdir, new_tname)
                print(f"  - {prefix:04d} → {new_prefix:04d} (caption) : {os.path.basename(entry['txt_path'])} → {new_tname}")
                os.rename(entry["txt_path"], new_tpath)

    print("\n[INFO] Selesai memperbaiki nomor duplikat.")


def main():
    if not os.path.isdir(OUTDIR):
        print(f"[ERROR] Folder OUTDIR tidak ditemukan: {OUTDIR}")
        return

    print(f"[INFO] Memperbaiki penomoran di folder: {OUTDIR}")
    fix_duplicates(OUTDIR)


if __name__ == "__main__":
    main()
