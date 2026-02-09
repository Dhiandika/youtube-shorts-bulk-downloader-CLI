import os
import glob
import re
import argparse
import time
from datetime import datetime

# Import library pembaca metadata (Fallback)
try:
    from hachoir.parser import createParser
    from hachoir.metadata import extractMetadata
    HACHOIR_AVAILABLE = True
except ImportError:
    HACHOIR_AVAILABLE = False

# DB Imports
import sqlite3
from yt_short_downloader.utils import create_safe_filename, parse_upload_date

# --- KONFIGURASI FILTER ---
BLACKLIST_KEYWORDS = ["Nimi", "Promosi", "Iklan"] 
DB_PATH = os.path.join(os.getcwd(), "data", "ytshorts.db")

def _load_db_map():
    """Load map {safe_title: upload_date_timestamp} from DB."""
    if not os.path.exists(DB_PATH):
        return {}
    
    mapping = {}
    try:
        with sqlite3.connect(DB_PATH) as conn:
            # Ambil semua video yang punya upload_date
            cur = conn.execute("SELECT title, upload_date FROM videos WHERE upload_date IS NOT NULL")
            for title, up in cur.fetchall():
                 if not title or not up: continue
                 
                 # Buat key yang sama dengan cara downloader menamai file
                 # Note: downloader memotong di 100/80 char, kita coba match substring
                 safe = create_safe_filename(title, 200) # ambil agak panjang untuk matching
                 
                 dt = parse_upload_date(up)
                 if dt:
                     mapping[safe] = time.mktime(dt.timetuple())
    except Exception as e:
        print(f"[WARN] Gagal baca DB: {e}")
    return mapping

def get_video_date_score(file_path, db_map):
    """
    Prioritas:
    1. DB Match (paling akurat)
    2. Hachoir Metadata (lumayan)
    3. File System Mtime (fallback)
    """
    filename = os.path.basename(file_path)
    base_no_ext = os.path.splitext(filename)[0]
    
    # 1. Coba cari di DB Map
    # Filename format: "01 - Title..." or just "Title..." or "01 - video_ID"
    # Kita cari apakah ada key di db_map yang menjadi substring dari filename
    # Ini brute-force sederhana tapi efektif untuk jumlah kecil-medium
    
    # Normalisasi filename untuk matching: hapus angka depan "01 - "
    clean_name = re.sub(r'^\d+\s*-\s*', '', base_no_ext)
    clean_name = re.sub(r'[_\s]+', ' ', clean_name).strip() # mirip _ascii_only tapi spasi
    
    # Coba direct match (agak susah karena sanitasi beda tipis)
    # Strategy: Token matching? Atau longest substring?
    # Simple strategy: Check if a significant known title is in the filename
    
    best_match_ts = None
    
    # Optimasi: kalau map besar, ini lambat. Tapi untuk tool ini oke.
    # Kita preprocess clean_name biar match dengan sanitize_filename db
    # db_map key sudah disanitasi _ascii_only.
    
    # Coba match dari db_map
    # Perbaiki logic: kita cari entry db mana yang 'mirip' file ini
    # Atau sebaliknya.
    # Cara paling aman: file ini punya 'title' di namanya.
    # Kita cek apakah title itu ada di DB.
    
    # Kita pakai set of tokens untuk fuzzy simple
    file_tokens = set(clean_name.lower().split())
    
    for safe_title, ts in db_map.items():
        # db key contoh: "This_is_a_video_title"
        # file contoh: "01 - This_is_a_video_title.mp4" (atau sudah spaces "This is a video title")
        
        # Versi replace _ dengan spasi
        db_title_clean = safe_title.replace('_', ' ').strip()
        
        if db_title_clean in clean_name or clean_name in db_title_clean:
             # Match strong
             return ts
             
        # Jaga-jaga filename kepotong dot dot dot
        if len(db_title_clean) > 20 and db_title_clean[:20] in clean_name:
             return ts

    # 2. Fallback Hachoir
    if HACHOIR_AVAILABLE:
        try:
            parser = createParser(file_path)
            if parser:
                with parser:
                    metadata = extractMetadata(parser)
                    if metadata and metadata.has("creation_date"):
                        return time.mktime(metadata.get("creation_date").timetuple())
        except Exception:
            pass

    # 3. Fallback OS
    return os.path.getmtime(file_path)

def clean_orphans(directory):
    """
    Menghapus 'file yatim piatu':
    1. Ada .txt tapi tidak ada Videonya -> HAPUS TXT (Sampah).
    2. Ada Video tapi tidak ada .txt -> HAPUS VIDEO (Sesuai request 'anomali hapus saja').
    """
    print("--- [1/4] Cleaning Orphans (File Tanpa Pasangan) ---")
    
    # Kumpulkan semua nama base file (tanpa ekstensi)
    video_extensions = ["*.mp4", "*.MP4", "*.webm", "*.WEBM", "*.mkv", "*.MKV"]
    video_files = []
    for ext in video_extensions:
        video_files.extend(glob.glob(os.path.join(directory, ext)))
    
    txt_files = glob.glob(os.path.join(directory, "*.txt"))
    
    # Buat set base name untuk pencarian cepat
    # Normalisasi path agar tidak error beda slash
    video_bases = {os.path.splitext(os.path.basename(f))[0] for f in video_files}
    txt_bases = {os.path.splitext(os.path.basename(f))[0] for f in txt_files}
    
    deleted_count = 0

    # KASUS 1: Hapus TXT yang tidak punya Video
    for txt_path in txt_files:
        base = os.path.splitext(os.path.basename(txt_path))[0]
        if base not in video_bases:
            try:
                os.remove(txt_path)
                print(f"[ORPHAN] Menghapus TXT sisa: {os.path.basename(txt_path)}")
                deleted_count += 1
            except OSError as e:
                print(f"Error delete {txt_path}: {e}")

    # KASUS 2: Hapus Video yang tidak punya TXT (Strict Mode)
    for vid_path in video_files:
        base = os.path.splitext(os.path.basename(vid_path))[0]
        if base not in txt_bases:
            try:
                os.remove(vid_path)
                print(f"[ORPHAN] Menghapus Video tanpa TXT: {os.path.basename(vid_path)}")
                deleted_count += 1
            except OSError as e:
                print(f"Error delete {vid_path}: {e}")
                
    if deleted_count == 0:
        print("Data bersih. Tidak ada file orphan.")
    else:
        print(f"Total file orphan dihapus: {deleted_count}")
    print("-" * 30)

def clean_filename(name):
    # 1. Hapus angka/strip awal (cleanup lama)
    name = re.sub(r'^\d+\s*-\s*', '', name)
    # 2. Ganti Underscore (_) dengan Spasi
    name = name.replace("_", " ")
    # 3. Rapikan spasi
    name = re.sub(r'\s+', ' ', name).strip()
    return name

def delete_blacklisted_files(directory):
    print("--- [2/4] Memeriksa Blacklist Keywords ---")
    extensions = ["*.mp4", "*.MP4", "*.webm", "*.WEBM", "*.mkv"]
    files = []
    for ext in extensions:
        files.extend(glob.glob(os.path.join(directory, ext)))
        
    count = 0
    for file_path in files:
        filename = os.path.basename(file_path)
        if any(keyword.lower() in filename.lower() for keyword in BLACKLIST_KEYWORDS):
            try:
                os.remove(file_path)
                print(f"[BLACKLIST] Delete Video: {filename}")
                # Hapus txt pasangannya juga
                base, _ = os.path.splitext(filename)
                txt = os.path.join(directory, f"{base}.txt")
                if os.path.exists(txt):
                    os.remove(txt)
                count += 1
            except Exception as e:
                print(e)
    if count == 0: print("Tidak ada file blacklist.")

def get_sorted_files(directory, newest_first=True):
    extensions = ["*.mp4", "*.MP4", "*.webm", "*.WEBM", "*.mkv"]
    files = []
    for ext in extensions:
        files.extend(glob.glob(os.path.join(directory, ext)))
    files = list(set(files))
    
    if not files: return []

    print("--- [3/4] Membaca Metadata & Database (Mohon Tunggu...) ---")
    
    # 1. Load DB
    db_map = _load_db_map()
    if db_map:
        print(f"  [INFO] Loaded {len(db_map)} dates from Database.")
    else:
        print("  [INFO] Database kosong/tidak ketemu. Fallback file time.")

    # 2. Score files
    files_with_date = []
    for f in files:
        ts = get_video_date_score(f, db_map)
        files_with_date.append((f, ts))
    
    # 3. Sort
    sorted_files = sorted(files_with_date, key=lambda x: x[1], reverse=newest_first)
    
    # Debug print top 3
    print("  [DEBUG] Top 3 Newest (menurut logika ini):")
    for f, ts in sorted_files[:3]:
        dt_str = datetime.fromtimestamp(ts).strftime('%Y-%m-%d')
        print(f"   - {dt_str} | {os.path.basename(f)}")

    return [f[0] for f in sorted_files]

def rename_files(directory, newest_first=True):
    # STEP 1: Hapus Anomali (Orphan)
    clean_orphans(directory)
    
    # STEP 2: Hapus Blacklist
    delete_blacklisted_files(directory)
    
    # STEP 3: Sorting berdasarkan Metadata
    sorted_files = get_sorted_files(directory, newest_first)
    
    if not sorted_files:
        print("Tidak ada file tersisa untuk di-rename.")
        return

    mode_str = "TERBARU (New) ke TERLAMA (Old)" if newest_first else "TERLAMA (Old) ke TERBARU (New)"
    print(f"\n--- [4/4] Proses Rename: {mode_str} ---")

    total = len(sorted_files)
    padding = len(str(total)) 
    if padding < 2: padding = 2

    for index, file_path in enumerate(sorted_files, start=1):
        directory_path = os.path.dirname(file_path)
        base_name, ext = os.path.splitext(os.path.basename(file_path))
        
        clean_base = clean_filename(base_name)
        
        # Nama Baru
        new_filename = f"{index:0{padding}d} - {clean_base}{ext}"
        new_path = os.path.join(directory_path, new_filename)
        
        if file_path != new_path:
            try:
                if os.path.exists(new_path):
                     # Handle collision dengan timestamp
                     clean_base = f"{clean_base}_{int(time.time())}"
                     new_filename = f"{index:0{padding}d} - {clean_base}{ext}"
                     new_path = os.path.join(directory_path, new_filename)
                
                os.rename(file_path, new_path)
                print(f"[{index}] {os.path.basename(file_path)} -> {new_filename}")
            except OSError as e:
                print(f"Error: {e}")

        # Handle TXT Pasangan
        txt_old = os.path.join(directory_path, f"{base_name}.txt")
        txt_new = os.path.join(directory_path, f"{index:0{padding}d} - {clean_base}.txt")
        
        if os.path.exists(txt_old) and txt_old != txt_new:
            try:
                os.rename(txt_old, txt_new)
            except: pass

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", nargs="?")
    # Default behavior: Newest First. Flag --oldest untuk membalik.
    parser.add_argument("--oldest", action="store_true", help="Sort Oldest to Newest")
    
    args = parser.parse_args()
    
    if not args.directory:
        args.directory = input("Path Folder: ").strip().replace('"', '').replace("'", "")
    
    if not os.path.exists(args.directory):
        print("Folder tidak ditemukan.")
        return
        
    if not os.path.exists(args.directory):
        print("Folder tidak ditemukan.")
        return
        
    # Default: newest_first = True
    newest_first = True
    
    # Jika user tidak pakai flag --oldest, kita tanya mode interaktif
    if not args.oldest:
        print("\nPilih Mode Sorting:")
        print("1. Terbaru ke Terlama (Newest -> Oldest) [Default]")
        print("2. Terlama ke Terbaru (Oldest -> Newest)")
        choice = input("Pilihan (1/2): ").strip()
        if choice == '2':
            newest_first = False
            print("Mode: Oldest -> Newest")
        else:
            print("Mode: Newest -> Oldest")
    else:
        # Jika pakai flag --oldest
        newest_first = False

    rename_files(args.directory, newest_first=newest_first)
    print("\nSelesai!")

if __name__ == "__main__":
    main()