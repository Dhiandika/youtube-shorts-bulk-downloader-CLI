import cv2
import os
import shutil
import subprocess
import sys
import re

# Force output to UTF-8
try:
    sys.stdout.reconfigure(encoding='utf-8')
except: pass

import json

def get_stream_info(file_path):
    """Retrieve all streams metadata using ffprobe."""
    cmd = [
        "ffprobe", 
        "-v", "error", 
        "-show_entries", "stream=index,codec_name,codec_type,pix_fmt", 
        "-of", "json", 
        file_path
    ]
    try:
        # Check if ffprobe is in path
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        return data.get("streams", [])
    except Exception as e:
        # Fallback if ffprobe fails or not installed
        # print(f"[WARN] FFprobe check failed: {e}")
        return []

def check_and_convert_video(video_path, target_mode='reels', force=False):
    """
    Validates and converts video to Meta-compliant format (H.264/AAC/MP4).
    Uses smart detection to skip if already compliant (unless force=True).
    """
    if not os.path.exists(video_path):
        return video_path, False

    # Init variables
    folder = os.path.dirname(video_path)
    filename = os.path.basename(video_path)
    base_name, ext = os.path.splitext(filename)

    # 1. Check Dimensions/Resolution first (Fast Check)
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened(): return video_path, False
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = frames / fps if fps > 0 else 0
    cap.release()

    # Check 0: Duration Validation (Max 180s)
    if duration > 180 and not force:
        print(f"  [SKIP] Duration {duration:.1f}s > 180s limit. Skipping conversion.")
        return video_path, False

    # Config user target
    if target_mode == 'feed':
        target_w, target_h = 1080, 1350
        ratio_str = "4:5"
    else: # reels
        target_w, target_h = 1080, 1920
        ratio_str = "9:16"

    needs_conversion = False
    reason = ""

    # Check 1: Resolution Validation
    if w != target_w or h != target_h:
        needs_conversion = True
        reason = f"Resolution Mismatch ({w}x{h} != {target_w}x{target_h})"

    # Check 2: Codec Validation (Slower Check)
    if not needs_conversion and not force:
        streams = get_stream_info(video_path)
        video_ok = False
        audio_ok = False
        
        for s in streams:
            if s.get("codec_type") == "video":
                # Meta loves h264 & yuv420p
                if s.get("codec_name") == "h264" and s.get("pix_fmt") == "yuv420p":
                    video_ok = True
            elif s.get("codec_type") == "audio":
                # Meta loves aac
                if s.get("codec_name") == "aac":
                    audio_ok = True
        
        if not video_ok or not audio_ok:
            needs_conversion = True
            reason = "Codec Incompatible (Need H.264/AAC/YUV420P)"

    if force:
        needs_conversion = True
        reason = "Force Re-encode Active"

    if not needs_conversion:
        # print(f"  ✅ Skipping (Already Compliant): {filename}")
        return video_path, False

    print(f"  ⚠️  Processing: {filename}")
    print(f"     Reason: {reason}")
    print(f"     Target: {ratio_str} Ultimate Standard...")

    temp_output = os.path.join(folder, f"{base_name}_temp.mp4")

    # Ultimate FFmpeg Command from User/Docs
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-i", video_path,
        
        # Metadata Scrubbing
        "-map_metadata", "-1",

        # Video Settings
        "-c:v", "libx264",
        "-profile:v", "main",
        "-level:v", "4.0",
        "-preset", "medium", # Changed from slow to medium for speed balance
        "-crf", "23",
        "-pix_fmt", "yuv420p",

        # Scaling & Padding
        "-vf", f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2,setsar=1",

        # GOP & Stability
        "-x264-params", "scenecut=0:open_gop=0:min-keyint=60:keyint=60:ref=4",

        # Audio Settings
        "-c:a", "aac",
        "-ar", "44100", # 44.1k is safer generic standard
        "-b:a", "128k",
        "-ac", "2",

        # Safety Limits
        "-maxrate", "25M",
        "-bufsize", "35M",
        "-movflags", "+faststart",

        temp_output
    ]

    try:
        subprocess.run(cmd, check=True)
        
        # Replace original file logic
        if os.path.exists(temp_output):
            final_path = os.path.join(folder, f"{base_name}.mp4")
            
            # Remove old file if extension changed
            if video_path != final_path and os.path.exists(video_path):
                os.remove(video_path)
            
            if os.path.exists(final_path):
                 os.remove(final_path)
            os.replace(temp_output, final_path)
            
            print(f"  ✅ Converted: {os.path.basename(final_path)}")
            return final_path, True

    except Exception as e:
        print(f"  ❌ FFmpeg Failed: {e}")
        if os.path.exists(temp_output): os.remove(temp_output)

    return video_path, False

def sort_files_by_resolution(folder_path, target_mode='reels', force=False):
    if not os.path.exists(folder_path):
        print(f"Error: Folder '{folder_path}' tidak ditemukan.")
        return

    # Ekstensi video yang didukung
    video_extensions = ('.mp4', '.avi', '.mov', '.mkv', '.webm')
    
    # Tracker untuk sequence number di folder tujuan
    folder_indices = {}

    def get_next_sequence(target_folder):
        """Lazy load max index dari folder tujuan."""
        if target_folder not in folder_indices:
            max_idx = 0
            if os.path.exists(target_folder):
                for f in os.listdir(target_folder):
                    # Cari pattern "NN - Title"
                    m = re.match(r'^(\d+)\s*-\s*', f)
                    if m:
                        try:
                            val = int(m.group(1))
                            if val > max_idx: max_idx = val
                        except: pass
            folder_indices[target_folder] = max_idx + 1
        
        idx = folder_indices[target_folder]
        folder_indices[target_folder] += 1
        return idx

    # Counter untuk laporan
    moved_count = 0
    converted_count = 0
    
    print(f"Mulai merapikan file di: {folder_path}")
    print("-" * 50)

    all_files = os.listdir(folder_path)
    # Sort agar urutan file yang dipindah konsisten (misal berdasarkan nama)
    all_files.sort() 
    
    for original_filename in all_files:
        # Hanya proses jika itu adalah VIDEO
        if original_filename.lower().endswith(video_extensions):
            video_full_path = os.path.join(folder_path, original_filename)
            
            # --- AUTO CONVERT LOGIC ---
            # Cek dan ubah jika perlu SEBELUM di-sort
            # Catch updated path (if extension changed from .webm to .mp4)
            video_full_path, converted = check_and_convert_video(video_full_path, target_mode, force)
            
            # Update filename variable because it is used below for destination path logic
            current_filename = os.path.basename(video_full_path)
            
            if converted:
                converted_count += 1
            # -------------------------------
            
            # Cek ulang resolusi (mungkin sudah berubah setelah convert)
            cap = cv2.VideoCapture(video_full_path)
            if cap.isOpened():
                w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                fps = cap.get(cv2.CAP_PROP_FPS)
                frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                duration = frames / fps if fps > 0 else 0
                cap.release() # Tutup video
                
                # Nama folder tujuan
                if duration > 180:
                     # Pisahkan video durasi panjang (> 3 menit)
                     target_folder_name = "_LongVideos"
                     # print(f"[REJECT] Duration {duration:.1f}s > 180s. Moving to {_LongVideos}...")
                else:
                     target_folder_name = f"{w}x{h}"

                target_folder_path = os.path.join(folder_path, target_folder_name)
                
                # Buat folder jika belum ada
                if not os.path.exists(target_folder_path):
                    os.makedirs(target_folder_path)
                
                # --- AUTO-SEQ & RENAME ---
                # Dapatkan nomor urut selanjutnya untuk folder ini
                next_seq = get_next_sequence(target_folder_path)
                
                # Bersihkan nama file dari index lama (misal "01 - ...")
                clean_name = re.sub(r'^\d+\s*-\s*', '', current_filename)
                
                # Jika nama bersih kosong (karena nama cuma angka?), pakai original
                if not clean_name: clean_name = current_filename

                # Bentuk nama baru: "01 - Title.mp4"
                new_filename = f"{next_seq:02d} - {clean_name}"
                destination_video = os.path.join(target_folder_path, new_filename)
                
                # 1. PINDAHKAN VIDEO
                try:
                    shutil.move(video_full_path, destination_video)
                    # print(f"[MOVE] {current_filename} -> {target_folder_name}/{new_filename}")
                except Exception as e:
                    print(f"Gagal memindahkan video {current_filename}: {e}")
                    continue

                # 2. CARI DAN PINDAHKAN FILE TXT PASANGANNYA
                # Cari file text original (yang mungkin punya nama lama sebelum convert/rename)
                # Kita pakai original_filename (sebelum convert) untuk cari txt?
                # Atau current_filename? Biasanya txt namanya sama dengan video input.
                # Tapi `check_and_convert` mungkin ganti input path.
                
                # Strategy: Cek txt dari Base Name *saat ini* (current_filename)
                # dan juga cek txt dari Base Name *original* (original_filename).
                
                base_current = os.path.splitext(current_filename)[0]
                base_original = os.path.splitext(original_filename)[0]
                
                found_txt = None
                
                # Cek current (.mp4 base)
                cand1 = os.path.join(folder_path, base_current + ".txt")
                # Cek original (.webm base)
                cand2 = os.path.join(folder_path, base_original + ".txt")
                
                if os.path.exists(cand1): found_txt = cand1
                elif os.path.exists(cand2): found_txt = cand2
                
                if found_txt:
                    # Rename TXT agar sesuai dengan Video Baru (NN - Title.txt)
                    base_new = os.path.splitext(new_filename)[0]
                    new_txt_name = base_new + ".txt"
                    destination_txt = os.path.join(target_folder_path, new_txt_name)
                    
                    try:
                        shutil.move(found_txt, destination_txt)
                    except Exception as e:
                        print(f"Gagal memindahkan txt {os.path.basename(found_txt)}: {e}")
                
                moved_count += 1
            else:
                cap.release()
                print(f"[SKIP] Video rusak/tidak terbaca: {original_filename}")

    print("-" * 50)
    print(f"Selesai! Total {moved_count} pasang file dikelompokkan.")
    print(f"Total berhasil dikonversi otomatis: {converted_count}")

# --- PENGGUNAAN ---
if __name__ == "__main__":
    # Ganti dengan path folder kamu
    lokasi_folder = r"new_week"
    
    print("Pilih Mode Target:")
    print("1. Reels / Shorts / TikTok (9:16) [Default]")
    print("2. Instagram Feed / Post (4:5) [Solusi jika error aspect ratio 4:5 to 16:9]")
    print("3. Force Re-encode (9:16) [Paksa convert ulang sesuai standar Meta]")
    
    pilihan = input("Masukkan pilihan (1/2/3): ").strip()
    
    mode = 'reels'
    force_mode = False
    
    if pilihan == '2':
        mode = 'feed'
        print(">> Mode terpilih: FEED (4:5) - 1080x1350")
    elif pilihan == '3':
        mode = 'reels'
        force_mode = True
        print(">> Mode terpilih: FORCE RECODE (9:16) - Menggunakan standar ketat Meta")
    else:
        print(">> Mode terpilih: REELS (9:16) - 1080x1920")

    sort_files_by_resolution(lokasi_folder, target_mode=mode, force=force_mode)