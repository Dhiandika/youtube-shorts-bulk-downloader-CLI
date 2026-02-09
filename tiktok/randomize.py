import os
import random
import uuid

# Path folder sesuai gambar kamu (pastikan path ini benar)
folder_path = r"anime_tiktok_downloads_v2"

def randomize_files():
    # 1. Cek apakah folder ada
    if not os.path.exists(folder_path):
        print(f"Error: Folder tidak ditemukan di {folder_path}")
        return

    # 2. Ambil semua file mp4
    files = [f for f in os.listdir(folder_path) if f.endswith(".mp4")]
    total_files = len(files)
    
    if total_files == 0:
        print("Tidak ada file MP4 di folder tersebut.")
        return

    print(f"Ditemukan {total_files} file. Sedang mengacak urutan...")

    # 3. KUNCI: Mengacak list file secara total
    random.shuffle(files)

    # Dictionary untuk menyimpan mapping nama lama ke nama sementara
    temp_map = []

    # 4. Tahap 1: Rename ke nama sementara (UUID)
    # Ini PENTING agar tidak terjadi crash jika nama target (misal 001.mp4) sudah ada
    print("Tahap 1: Memberi nama sementara...")
    for filename in files:
        old_path = os.path.join(folder_path, filename)
        
        # Buat nama unik acak sementara
        temp_name = str(uuid.uuid4()) + ".mp4"
        temp_path = os.path.join(folder_path, temp_name)
        
        os.rename(old_path, temp_path)
        temp_map.append(temp_path)

    # 5. Tahap 2: Rename ke urutan angka (001, 002, dst)
    # Karena list awal sudah di-shuffle, maka konten video 001 adalah random
    print("Tahap 2: Memberi nama final yang rapi...")
    
    # Menentukan berapa digit angka nol di depan (padding)
    # Jika file ada 400+, kita butuh 3 digit (001 - 999)
    digit_padding = len(str(total_files)) 
    
    for index, temp_path in enumerate(temp_map):
        # Format angka: 1 menjadi 001, 2 menjadi 002, dst.
        new_number = str(index + 1).zfill(digit_padding)
        new_name = f"{new_number} - Random_Anime.mp4"
        final_path = os.path.join(folder_path, new_name)
        
        os.rename(temp_path, final_path)

    print("------------------------------------------------")
    print("SELESAI! Semua file telah diacak urutannya dan diberi nama baru.")
    print(f"Cek folder: {folder_path}")

if __name__ == "__main__":
    # Peringatan keamanan
    print("PERINGATAN: Skrip ini akan mengubah nama semua file MP4 di folder target.")
    confirm = input("Ketik 'y' untuk lanjut: ")
    
    if confirm.lower() == 'y':
        randomize_files()
    else:
        print("Dibatalkan.")