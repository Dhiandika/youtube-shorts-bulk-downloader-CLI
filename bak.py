import os
import glob

# Folder tempat file .bak berada
TARGET_FOLDER = "video_cut"

def delete_backup_files():
    if not os.path.isdir(TARGET_FOLDER):
        print(f"❌ Folder '{TARGET_FOLDER}' tidak ditemukan.")
        return

    backup_files = glob.glob(os.path.join(TARGET_FOLDER, "*.bak"))

    if not backup_files:
        print("ℹ️ Tidak ada file .bak yang ditemukan.")
        return

    print(f"🔍 Ditemukan {len(backup_files)} file backup. Menghapus...")
    for file_path in backup_files:
        try:
            os.remove(file_path)
            print(f"✅ Dihapus: {os.path.basename(file_path)}")
        except Exception as e:
            print(f"❌ Gagal menghapus {file_path}: {e}")

    print("🧹 Pembersihan selesai.")

if __name__ == "__main__":
    delete_backup_files()
