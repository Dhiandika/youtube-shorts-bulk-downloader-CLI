import os
import sqlite3
import glob

def repair_database():
    print("YouTube Shorts DB Repair Tool")
    print("==============================\n")
    
    # 1. Tentukan Path DB
    db_path = os.path.join(os.getcwd(), "data", "ytshorts.db")
    if not os.path.exists(db_path):
        print(f"[ERROR] Database tidak ditemukan di: {db_path}")
        return

    # 2. Tentukan Folder Download
    # Default ke 'downloads', user bisa input custom
    default_dir = os.path.join(os.getcwd(), "downloads")
    if not os.path.exists(default_dir):
        print(f"[WARN] Folder default '{default_dir}' tidak ada.")
        user_dir = input("Masukkan path folder download (kosongkan jika 'downloads'): ").strip()
        if user_dir:
            default_dir = user_dir
    
    if not os.path.exists(default_dir):
        print("[ERROR] Folder download tidak valid. Keluar.")
        return

    print(f"\n[INFO] Reading Database: {db_path}")
    print(f"[INFO] Scanning Files in : {default_dir}")
    print("Sedang memindai file fisik... (mohon tunggu)")

    # 3. Index Semua File Fisik (Recursive)
    # Kita cari semua file .mp4 untuk perbandingan
    physical_files = set()
    for root, dirs, files in os.walk(default_dir):
        for file in files:
            if file.lower().endswith(".mp4"):
                physical_files.add(file)
    
    # Gabungkan semua nama file jadi satu string panjang untuk pencarian substring (ID)
    # Ini trik cepat karena nama file kita formatnya "INDEX - JUDUL - ID.mp4" atau sejenisnya
    # Tapi lebih aman kita simpan set untuk checking exact match jika memungkinkan, 
    # namun karena format nama file dinamis, kita lebih baik cari ID di dalam nama file.
    
    print(f"[INFO] Ditemukan {len(physical_files)} file video .mp4 di disk.")

    # 4. Buka Database
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Ambil semua video yang statusnya 'downloaded' (flag boolean/int 1)
        # Struktur tabel videos: key, channel_key, video_id, title, upload_date, downloaded
        cursor.execute("SELECT video_id, title FROM videos WHERE downloaded=1")
        rows = cursor.fetchall()
        
        print(f"[INFO] Database mencatat {len(rows)} video sukses didownload.")
        print("Memulai verifikasi sinkronisasi...")
        
        deleted_count = 0
        
        for video_id, title in rows:
            # Logic Check: Apakah video_id ada di salah satu nama file fisik?
            # Kita loop simple search. (Bisa lambat jika ribuan file, tapi ok untuk tool repair)
            
            found = False
            for fname in physical_files:
                if video_id in fname:
                    found = True
                    break
            
            if not found:
                # Video ID ini tidak ada di folder -> Phantom Entry!
                # Hapus flag downloaded agar didownload ulang nanti
                safe_title = (title or "No Title")[:30]
                print(f"[FIX] Missing: {video_id} ({safe_title}...) -> Resetting flag.")
                
                # Update DB: set downloaded=0
                # Perhatian: key di tabel videos biasanya "CHANNEL::VIDEOID"
                # Kita update based on video_id saja cukup aman jika ID unik global (YouTube ID unik).
                cursor.execute("UPDATE videos SET downloaded=0, downloaded_at=NULL WHERE video_id=?", (video_id,))
                deleted_count += 1
        
        conn.commit()
        conn.close()
        
        print("-" * 40)
        print(f"SELESAI. {deleted_count} entri 'hantu' telah di-reset.")
        print("Silakan jalankan main4.py kembali untuk mengunduh ulang video tersebut dengan kualitas benar.")
        
    except Exception as e:
        print(f"[EXCEPTION] Gagal memperbaiki database: {e}")

if __name__ == "__main__":
    repair_database()
