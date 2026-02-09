import sys
import glob

# Force UTF-8 encoding for stdout (console) to handle Japanese characters
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

# ================= KONFIGURASI =================
# ================= KONFIGURASI =================
# Ganti folder sesuai tempat file txt kamu berada
# Resolve path relative to this script file
import os # Ensure os is imported if not already, though it is at top
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FOLDER_PATH = os.path.join(BASE_DIR, "new_week", "1080x1920") 

# Masukkan hashtag yang ingin kamu tambahkan di sini
# Update: Daftar hashtag baru sesuai request (Japanese characters preserved)
HASHTAG_TO_ADD = "#shorts #hololivejp #hololiveindonesia #hololiveID #hololiveenglish #hololiveEN #ホロライブ #hololive #vtuber #fblifestyle " 
# ===============================================

def safe_print(text):
    """Print text safely, replacing characters that can't be encoded by the console."""
    try:
        print(text)
    except UnicodeEncodeError:
        # Fallback: encode to current console encoding (e.g., cp1252) replacing errors, then decode
        enc = sys.stdout.encoding or 'utf-8'
        print(text.encode(enc, errors='replace').decode(enc))

def process_hashtags(folder_path):
    safe_print(f"🔨 Menjalankan Tool Penambah Hashtag di: {folder_path}")
    safe_print(f"📝 Tags: {HASHTAG_TO_ADD}\n")
    
    # 1. Cek apakah folder ada
    if not os.path.exists(folder_path):
        safe_print(f"❌ Folder '{folder_path}' tidak ditemukan.")
        return

    # 2. Ambil semua file .txt
    txt_files = glob.glob(os.path.join(folder_path, "*.txt"))
    total_files = len(txt_files)

    if total_files == 0:
        safe_print(f"❌ Tidak ada file .txt ditemukan di folder '{folder_path}'.")
        return

    safe_print(f"📂 Ditemukan {total_files} file. Memproses...\n")

    updated_count = 0
    skipped_count = 0

    for file_path in txt_files:
        filename = os.path.basename(file_path)
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read().strip()

            if HASHTAG_TO_ADD in content:
                safe_print(f"  ⏭️  Skipped (Sudah ada): {filename}")
                skipped_count += 1
                continue
            
            new_content = f"{content}\n\n{HASHTAG_TO_ADD}"

            with open(file_path, 'w', encoding='utf-8-sig') as f:
                f.write(new_content)
            
            safe_print(f"  ✅ Added: {filename}")
            updated_count += 1

        except Exception as e:
            safe_print(f"  ❌ Error membaca/menulis {filename}: {e}")

    safe_print("\n" + "="*30)
    safe_print(f"🎉 Selesai!")
    safe_print(f"✅ Berhasil ditambahkan: {updated_count} file")
    safe_print(f"⏭️  Dilewati (sudah ada): {skipped_count} file")
    safe_print("="*30)

def main():
    process_hashtags(FOLDER_PATH)

if __name__ == "__main__":
    main()