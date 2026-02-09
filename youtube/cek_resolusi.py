import cv2
import os
import shutil
import subprocess
import sys

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
    cap.release()

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
    
    # Counter untuk laporan
    moved_count = 0
    converted_count = 0
    
    print(f"Mulai merapikan file di: {folder_path}")
    print("-" * 50)

    all_files = os.listdir(folder_path)
    
    for filename in all_files:
        # Hanya proses jika itu adalah VIDEO
        if filename.lower().endswith(video_extensions):
            video_full_path = os.path.join(folder_path, filename)
            
            # --- AUTO CONVERT LOGIC ---
            # Cek dan ubah jika perlu SEBELUM di-sort
            # Catch updated path (if extension changed from .webm to .mp4)
            video_full_path, converted = check_and_convert_video(video_full_path, target_mode, force)
            
            if converted:
                # Update filename variable because it is used below for destination path logic
                filename = os.path.basename(video_full_path)
                converted_count += 1
            # -------------------------------
            
            # Cek ulang resolusi (mungkin sudah berubah setelah convert)
            cap = cv2.VideoCapture(video_full_path)
            if cap.isOpened():
                w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                cap.release() # Tutup video
                
                # Nama folder tujuan berdasarkan resolusi
                target_folder_name = f"{w}x{h}"
                target_folder_path = os.path.join(folder_path, target_folder_name)
                
                # Buat folder jika belum ada
                if not os.path.exists(target_folder_path):
                    os.makedirs(target_folder_path)
                
                # 1. PINDAHKAN VIDEO
                destination_video = os.path.join(target_folder_path, filename)
                try:
                    shutil.move(video_full_path, destination_video)
                    # print(f"[MOVE] Video: {filename} -> /{target_folder_name}")
                except Exception as e:
                    print(f"Gagal memindahkan video {filename}: {e}")
                    continue

                # 2. CARI DAN PINDAHKAN FILE TXT PASANGANNYA
                file_basename = os.path.splitext(filename)[0]
                txt_filename = file_basename + ".txt"
                txt_full_path = os.path.join(folder_path, txt_filename)
                
                if os.path.exists(txt_full_path):
                    destination_txt = os.path.join(target_folder_path, txt_filename)
                    try:
                        shutil.move(txt_full_path, destination_txt)
                    except Exception as e:
                        print(f"Gagal memindahkan txt {txt_filename}: {e}")
                
                moved_count += 1
            else:
                cap.release()
                print(f"[SKIP] Video rusak/tidak terbaca: {filename}")

    print("-" * 50)
    print(f"Selesai! Total {moved_count} pasang file dikelompokkan.")
    print(f"Total berhasil dikonversi otomatis: {converted_count}")

# --- PENGGUNAAN ---
if __name__ == "__main__":
    # Ganti dengan path folder kamu
    lokasi_folder = r"new_week/1080x1920"
    
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