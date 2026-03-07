import os
import re
from .logger import logger
from .config import SHORTS_DIR, LONG_VIDEOS_DIR

def run_caption_customizer():
    print("\n" + "="*40)
    print(" PILIH TIPE VIDEO UNTUK CUSTOM CAPTION")
    print("="*40)
    print("1. Shorts (Video Vertikal)")
    print("2. Long Videos (Video Baring)")
    
    type_choice = input("\nMasukkan nomor tipe (1/2): ").strip()
    
    if type_choice == '1':
        base_dir = SHORTS_DIR
        type_str = "Shorts"
    elif type_choice == '2':
        base_dir = LONG_VIDEOS_DIR
        type_str = "Long Videos"
    else:
        print("\n[!] Pilihan tidak valid. Batal.")
        return

    if not os.path.exists(base_dir):
        print(f"\n[!] Directory {type_str} belum dibuat. Silakan download video terlebih dahulu.")
        return
        
    folders = [f for f in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, f))]
    if not folders:
        print(f"\n[!] Tidak ada folder channel yang ditemukan di dalam {type_str}.")
        return
        
    print(f"\n" + "="*40)
    print(f" PILIH FOLDER CHANNEL DI DALAM {type_str.upper()}")
    print("="*40)
    for idx, folder in enumerate(folders, 1):
        print(f"[{idx}] {folder}")
        
    choice = input("\nMasukkan nomor folder channel: ").strip()
    try:
        choice_idx = int(choice) - 1
        selected_folder = folders[choice_idx]
    except (ValueError, IndexError):
        print("\n[!] Pilihan folder tidak valid. Batal.")
        return
        
    target_dir = os.path.join(base_dir, selected_folder)
    txt_files = [f for f in os.listdir(target_dir) if f.endswith('.txt')]
    
    if not txt_files:
        print(f"\n[!] Tidak ada file .txt yang ditemukan di {selected_folder}.")
        return
        
    print(f"\nTerpilih: {selected_folder} ({len(txt_files)} file caption ditemukan)\n")
    
    print("="*40)
    print("1. MASUKKAN CAPTION ATAS (Judul/Deskripsi)")
    print("   (Ketik 'SELESAI' pada baris baru jika sudah selesai menulis multi-baris)")
    print("="*40)
    top_lines = []
    while True:
        line = input()
        if line.strip().upper() == 'SELESAI':
            break
        top_lines.append(line)
    top_caption = "\n".join(top_lines)
    
    print("\n" + "="*40)
    print("2. MASUKKAN CAPTION BAWAH (Penutup / Hashtag)")
    print("   (Ketik 'SELESAI' pada baris baru jika sudah selesai menulis multi-baris)")
    print("="*40)
    bottom_lines = []
    while True:
        line = input()
        if line.strip().upper() == 'SELESAI':
            break
        bottom_lines.append(line)
    bottom_caption = "\n".join(bottom_lines)
    
    # Process files
    success_count = 0
    for file_name in txt_files:
        file_path = os.path.join(target_dir, file_name)
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # Extract Bilibili: ... and Link: ... lines
            bilibili_match = re.search(r'(Bilibili: [^\n]+)', content)
            link_match = re.search(r'(Link: [^\n]+)', content)
            
            middle_section = []
            if bilibili_match: middle_section.append(bilibili_match.group(1))
            if link_match: middle_section.append(link_match.group(1))
            
            middle_text = "\n".join(middle_section)
            
            # If for some reason the middle text is totally missing, skip safely or just append
            if not middle_text:
                logger.warning(f"Format Bilibili/Link tidak ditemukan di {file_name}. Melewati file ini...")
                continue
                
            # Construct new content
            new_content_parts = []
            if top_caption.strip(): new_content_parts.append(top_caption + "\n")
            new_content_parts.append(middle_text + "\n")
            if bottom_caption.strip(): new_content_parts.append(bottom_caption + "\n")
            
            new_content = "\n".join(new_content_parts)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
                
            success_count += 1
            
        except Exception as e:
            logger.error(f"Gagal memproses {file_name}: {e}")
            
    print(f"\n[+] Selesai! {success_count} dari {len(txt_files)} file caption berhasil di-update.")
