import os
from moviepy import VideoFileClip  # UPDATED: Import langsung dari root moviepy (v2.0)

def process_videos(folder_path):
    # Konfigurasi
    MAX_DURATION = 90.0  # Detik
    NEW_TITLE_BASE = "Anime Recommendation"
    
    # Mendapatkan semua file mp4
    all_files = os.listdir(folder_path)
    video_files = [f for f in all_files if f.lower().endswith('.mp4')]
    
    valid_videos = []

    print(f"--- Memulai Proses (MoviePy v2.0) di: {folder_path} ---")
    print(f"Total video awal: {len(video_files)}")

    # 1. TAHAP PENGECEKAN & PENGHAPUSAN
    for filename in video_files:
        mp4_path = os.path.join(folder_path, filename)
        txt_filename = filename.rsplit('.', 1)[0] + '.txt'
        txt_path = os.path.join(folder_path, txt_filename)

        try:
            duration = 0
            # UPDATED: Menggunakan Context Manager (with)
            # Ini sangat disarankan di Python 3.7+ dan MoviePy v2.0 untuk resource management
            with VideoFileClip(mp4_path) as clip:
                duration = clip.duration
            
            # Logika seleksi
            if duration > MAX_DURATION:
                print(f"[DELETE] {filename} (Durasi: {duration:.2f}s > {MAX_DURATION}s)")
                
                # Hapus MP4
                try:
                    os.remove(mp4_path)
                    # Hapus TXT pasangannya jika ada
                    if os.path.exists(txt_path):
                        os.remove(txt_path)
                except PermissionError:
                    print(f"[ERROR] Izin ditolak saat menghapus {filename}. File mungkin sedang terbuka.")
            else:
                print(f"[KEEP] {filename} (Durasi: {duration:.2f}s)")
                valid_videos.append(filename)

        except Exception as e:
            print(f"[ERROR] Gagal memproses {filename}: {e}")

    # 2. TAHAP PENGURUTAN ULANG & RENAME (RE-INDEXING)
    print("\n--- Memulai Pengurutan Ulang & Rename ---")
    
    # Sortir nama file lama agar urutan relatif terjaga
    valid_videos.sort()

    for index, old_filename in enumerate(valid_videos, start=1):
        # Format baru: 0001 - anime recommendation.mp4
        new_name_base = f"{index:04d} - {NEW_TITLE_BASE}"
        
        old_mp4_path = os.path.join(folder_path, old_filename)
        new_mp4_path = os.path.join(folder_path, f"{new_name_base}.mp4")
        
        # Rename MP4
        # Cek agar tidak error jika nama target sudah sama
        if old_mp4_path != new_mp4_path:
            try:
                os.rename(old_mp4_path, new_mp4_path)
                
                # Rename TXT pasangannya
                old_txt_name = old_filename.rsplit('.', 1)[0] + '.txt'
                old_txt_path = os.path.join(folder_path, old_txt_name)
                new_txt_path = os.path.join(folder_path, f"{new_name_base}.txt")

                if os.path.exists(old_txt_path):
                    os.rename(old_txt_path, new_txt_path)
                
                print(f"[RENAME] {old_filename} -> {new_name_base}.mp4")
            except OSError as e:
                print(f"[FAIL RENAME] {old_filename}: {e}")

    print("\n--- Selesai! ---")
    print(f"Sisa video valid: {len(valid_videos)}")

if __name__ == "__main__":
    # Sesuaikan path ini dengan folder Anda
    target_folder = r"anime_tiktok_downloads" 
    
    if os.path.exists(target_folder):
        process_videos(target_folder)
    else:
        print(f"Folder tidak ditemukan: {target_folder}")