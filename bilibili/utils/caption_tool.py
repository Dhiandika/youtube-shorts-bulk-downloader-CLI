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
    print(f" PILIH TARGET CHANNEL DI DALAM {type_str.upper()}")
    print("="*40)
    print("[0] Seluruh Channel (Update Semua Folder)")
    for idx, folder in enumerate(folders, 1):
        print(f"[{idx}] {folder}")
        
    choice = input("\nMasukkan nomor pilihan: ").strip()
    target_dirs = []
    try:
        choice_idx = int(choice)
        if choice_idx == 0:
            target_dirs = [os.path.join(base_dir, f) for f in folders]
            print(f"\nTerpilih: SEMUA CHANNEL ({len(target_dirs)} folder)")
        else:
            selected_folder = folders[choice_idx - 1]
            target_dirs = [os.path.join(base_dir, selected_folder)]
            print(f"\nTerpilih: {selected_folder}")
    except (ValueError, IndexError):
        print("\n[!] Pilihan tidak valid. Batal.")
        return
        
    print("\n" + "="*40)
    print(" PILIH AKSI YANG INGIN DILAKUKAN")
    print("="*40)
    print("[1] Custom Caption (Tambah Teks Atas/Bawah pada file .txt)")
    print("[2] Bersihkan Folder (Hapus sisa .part, .cmt.xml & TXT kosong)")
    print("[3] Urutkan Ulang Nama & Generate Template TXT yang Hilang")
    print("[4] Ban Word Filter (Hapus Otomatis Video & Teks Berdasarkan Kata Terlarang)")
    action_choice = input("\nMasukkan nomor aksi (1/2/3/4): ").strip()
    
    if action_choice == '1':
        _action_custom_caption(target_dirs)
    elif action_choice == '2':
        _action_clean_folder(target_dirs)
    elif action_choice == '3':
        _action_reorder_and_generate(target_dirs)
    elif action_choice == '4':
        _action_ban_word_filter(target_dirs)
    else:
        print("\n[!] Pilihan aksi tidak valid.")

def _action_custom_caption(target_dirs):
    all_txt_files = []
    for d in target_dirs:
        for root, _, files in os.walk(d):
            for f in files:
                if f.endswith('.txt'):
                    all_txt_files.append((root, f))
    
    if not all_txt_files:
        print(f"\n[!] Tidak ada file .txt (caption) yang ditemukan di folder pilihan.")
        return
        
    print(f"({len(all_txt_files)} file caption ditemukan dari {len(target_dirs)} folder)\n")
    
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
    print(" OPSI UNTUK CAPTION ATAS")
    print("="*40)
    print("[1] Ganti (Replace) Caption Atas")
    print("[2] Tambahkan (Append) ke Caption Atas yang sudah ada")
    top_mode_choice = input("Pilih mode (1/2) [Default: 1]: ").strip()
    top_mode = 'append' if top_mode_choice == '2' else 'replace'
    
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
    
    print("\n" + "="*40)
    print(" OPSI UNTUK CAPTION BAWAH")
    print("="*40)
    print("[1] Ganti (Replace) Caption Bawah")
    print("[2] Tambahkan (Append) ke Caption Bawah yang sudah ada")
    bottom_mode_choice = input("Pilih mode (1/2) [Default: 1]: ").strip()
    bottom_mode = 'append' if bottom_mode_choice == '2' else 'replace'
    
    # Process files
    success_count = 0
    for target_dir, file_name in all_txt_files:
        file_path = os.path.join(target_dir, file_name)
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            bilibili_match = re.search(r'(Bilibili: [^\n]+)', content)
            link_match = re.search(r'(Link: [^\n]+)', content)
            
            middle_section = []
            if bilibili_match: middle_section.append(bilibili_match.group(1))
            if link_match: middle_section.append(link_match.group(1))
            
            middle_text = "\n".join(middle_section)
            
            if not middle_text:
                logger.warning(f"Format Bilibili/Link tidak ditemukan di {file_name}. Melewati file ini...")
                continue
                
            parts = content.split(middle_text)
            existing_top = parts[0].strip() if len(parts) > 1 else ""
            existing_bottom = parts[1].strip() if len(parts) > 1 else ""
            
            new_content_parts = []
            
            if top_mode == 'append':
                combined_top = []
                if existing_top: combined_top.append(existing_top)
                if top_caption.strip(): combined_top.append(top_caption)
                if combined_top: new_content_parts.append("\n\n".join(combined_top) + "\n")
            else:
                if top_caption.strip(): new_content_parts.append(top_caption + "\n")
                
            new_content_parts.append(middle_text + "\n")
            
            if bottom_mode == 'append':
                combined_bottom = []
                if existing_bottom: combined_bottom.append(existing_bottom)
                if bottom_caption.strip(): combined_bottom.append(bottom_caption)
                if combined_bottom: new_content_parts.append("\n\n".join(combined_bottom) + "\n")
            else:
                if bottom_caption.strip(): new_content_parts.append(bottom_caption + "\n")
            
            new_content = "\n".join(new_content_parts)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
                
            success_count += 1
            
        except Exception as e:
            logger.error(f"Gagal memproses {file_name}: {e}")
            
    print(f"\n[+] Selesai! {success_count} dari {len(all_txt_files)} file caption berhasil di-update.")

import shutil

def _action_clean_folder(target_dirs):
    deleted_count = 0
    for d in target_dirs:
        for root, _, files in os.walk(d, topdown=False):
            for f in files:
                path = os.path.join(root, f)
                # Delete junk yt-dlp cache files
                if f.endswith('.part') or f.endswith('.ytdl') or f.endswith('.cmt.xml'):
                    try:
                        os.remove(path)
                        deleted_count += 1
                        print(f"Dihapus (File Sisa): {f}")
                    except Exception:
                        pass
                # Delete orphaned .txt files (exclude archive)
                elif f.endswith('.txt') and f != 'downloaded_archive.txt':
                    mp4_file = f.replace('.txt', '.mp4')
                    if not os.path.exists(os.path.join(root, mp4_file)):
                        try:
                            os.remove(path)
                            deleted_count += 1
                            print(f"Dihapus (TXT tanpa video): {f}")
                        except Exception:
                            pass
            
            # Delete empty subdirectories that may have been created by yt-dlp formats
            if root != d:
                try:
                    if not os.listdir(root):
                        os.rmdir(root)
                        print(f"Dihapus (Folder Kosong): {os.path.basename(root)}")
                except Exception:
                    pass
                    
    print(f"\n[+] Pembersihan selesai! {deleted_count} file sisa/orphaned berhasil dihapus.")

def _action_reorder_and_generate(target_dirs):
    renamed_count = 0
    generated_count = 0
    moved_count = 0
    
    for d in target_dirs:
        # The true channel name is the target directory chosen initially
        channel_name = os.path.basename(d)
        
        # 1. FLATTEN DIRECTORY PHASE
        # Pull all files out of deep subfolders (e.g. 1728p) into the main channel folder
        for root, dirs, files in os.walk(d, topdown=False):
            if root != d:
                for f in files:
                    # Move everything up
                    src = os.path.join(root, f)
                    dst = os.path.join(d, f)
                    
                    # Handle collisions if file somehow exists at root already
                    if os.path.exists(dst):
                        base, ext = os.path.splitext(f)
                        dst = os.path.join(d, f"{base}_alt{ext}")
                        
                    try:
                        shutil.move(src, dst)
                        moved_count += 1
                        print(f"Dipindah ke Luar ({os.path.basename(root)}): {f}")
                    except Exception as e:
                        logger.error(f"Gagal memindah {f}: {e}")
                
                # Prune the empty subfolder after moving its files
                try:
                    os.rmdir(root)
                except Exception:
                    pass

        # 2. PROCESSING PHASE (Now we strictly target the flat channel root 'd')
        mp4s = [f for f in os.listdir(d) if f.endswith('.mp4')]
        if not mp4s:
            continue
            
        # Sort files by modification time chronologically to preserve the actual download order
        mp4s.sort(key=lambda x: os.path.getmtime(os.path.join(d, x)))
        
        # Deduplication Pass
        seen_base_titles = set()
        unique_mp4s = []
        
        for old_mp4 in mp4s:
            base_title = re.sub(r'^\d+\s*-\s*', '', old_mp4)
            tracker_title = base_title.lower()
            
            if tracker_title in seen_base_titles:
                path_to_delete = os.path.join(d, old_mp4)
                try:
                    os.remove(path_to_delete)
                    txt_to_delete = path_to_delete.replace('.mp4', '.txt')
                    if os.path.exists(txt_to_delete):
                        os.remove(txt_to_delete)
                    print(f"Dihapus (Video Duplikat): {old_mp4}")
                except Exception as e:
                    pass
            else:
                seen_base_titles.add(tracker_title)
                unique_mp4s.append(old_mp4)
        
        for idx, old_mp4 in enumerate(unique_mp4s, 1):
            # Extract pure title removing prefix like '001 - ' or '05 - '
            base_title = re.sub(r'^\d+\s*-\s*', '', old_mp4)
            base_title_no_ext = base_title.replace('.mp4', '')
            
            new_mp4 = f"{idx:03d} - {base_title}"
            old_mp4_path = os.path.join(d, old_mp4)
            new_mp4_path = os.path.join(d, new_mp4)
            
            # If name is out of order, rename it
            if old_mp4 != new_mp4:
                os.rename(old_mp4_path, new_mp4_path)
                renamed_count += 1
                print(f"Diurutkan: {old_mp4} -> {new_mp4}")
                
            old_txt = old_mp4.replace('.mp4', '.txt')
            new_txt = new_mp4.replace('.mp4', '.txt')
            old_txt_path = os.path.join(d, old_txt)
            new_txt_path = os.path.join(d, new_txt)
            
            # Rename corresponding txt file if it exists so it tracks
            if os.path.exists(old_txt_path):
                if old_txt_path != new_txt_path:
                    os.rename(old_txt_path, new_txt_path)
                
                # Proactively clean up existing txt files
                try:
                    with open(new_txt_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        
                    # Remove residual brackets globally
                    content = content.replace('【', '').replace('】', '')
                    
                    # Force overwrite any incorrect 'Bilibili: [resolution]' assignments to the true root channel name
                    content = re.sub(r'Bilibili:\s*.*', f'Bilibili: {channel_name}', content)
                    
                    with open(new_txt_path, 'w', encoding='utf-8') as f:
                        f.write(content)
                except Exception as e:
                    logger.error(f"Gagal membersihkan isi txt lama {new_txt}: {e}")
            else:
                # Clean up ugly yt-dlp raw titles (e.g. Uploader_BV1HV1sBSExv_Title -> Title)
                clean_title = base_title_no_ext
                bv_match = re.search(r'BV[A-Za-z0-9]{10}[_-]+(.+)$', clean_title)
                if bv_match:
                    clean_title = bv_match.group(1).strip()
                    
                # Generate missing text template completely for orphaned videos
                template = f"{clean_title}\nBilibili: {channel_name}\n#animation #anime #vtuber #MMD"
                with open(new_txt_path, 'w', encoding='utf-8') as f:
                    f.write(template)
                generated_count += 1
                print(f"Dibuat TXT baru: {new_txt}")

    print(f"\n[+] Re-order selesai! {moved_count} file ditarik ke luar, {renamed_count} video diurutkan, {generated_count} TXT baru dibuat.")
    
def _action_ban_word_filter(target_dirs):
    print("\n" + "="*40)
    print(" FILTER PENGHAPUS KATA TERLARANG (BAN WORD)")
    print("="*40)
    print("Masukkan daftar kata terlarang dipisahkan dengan koma.")
    print("Contoh: AI, mmd, tarian, buram")
    user_input = input("\nKata terlarang: ").strip()
    
    if not user_input:
        print("\n[!] Tidak ada kata terlarang yang dimasukkan. Batal.")
        return
        
    # Build list of lower-cased exact string matches
    banned_words = [w.strip().lower() for w in user_input.split(',')]
    banned_words = [w for w in banned_words if w]
    
    if not banned_words:
        return
        
    print(f"\n[+] Memulai scan mendalam untuk kata terlarang: {', '.join(banned_words)}...")
    
    deleted_pairs_count = 0
    deleted_files = set()
    pending_deletions = []
    seen_bases = set()
    
    def check_contains_banned(text: str) -> str | None:
        """
        Check if text contains any banned word.
        If the banned word is alphanumeric (e.g., 'ai', 'mmd'), enforce ascii word boundaries 
        so it doesn't match inside 'wait' or 'maiden', but DO NOT use \\b because Python treats 
        Chinese characters as \\w (word chars), which breaks matches like 'AI动画'.
        """
        for w in banned_words:
            if re.match(r'^[a-z0-9_-]+$', w):
                # Enforce ascii boundaries only: not preceded/followed by another ascii char
                if re.search(fr'(?<![a-z0-9_]){re.escape(w)}(?![a-z0-9_])', text):
                    return w
            else:
                # Raw substring match for CJK or mixed words
                if w in text:
                    return w
        return None
    
    def flag_pair(root_d, base_filename, reason_msg):
        """Flag a file base for deletion and cache it in the pending queue."""
        base_no_ext = os.path.splitext(base_filename)[0]
        full_base_path = os.path.join(root_d, base_no_ext)
        if full_base_path not in seen_bases:
            seen_bases.add(full_base_path)
            pending_deletions.append((root_d, base_no_ext, reason_msg))

    for d in target_dirs:
        for root, dirs, files in os.walk(d, topdown=False):
            for f in files:
                # 1. Check Filename for Ban Words
                f_lower = f.lower()
                matched_word = check_contains_banned(f_lower)
                if matched_word:
                    flag_pair(root, f, f"Judul mengandung kata '{matched_word}'")
                    continue
                    
                # 2. If it's a TXT file, check its internal contents for Ban Words
                if f.endswith('.txt'):
                    txt_path = os.path.join(root, f)
                    try:
                        with open(txt_path, 'r', encoding='utf-8') as tf:
                            content = tf.read().lower()
                            
                        matched_content_word = check_contains_banned(content)
                        if matched_content_word:
                            flag_pair(root, f, f"Isi TXT mengandung kata '{matched_content_word}'")
                    except Exception:
                        pass

    # 3. Present Findings to User
    if not pending_deletions:
        print("\n[+] Scan selesai. Tidak ada video/teks yang mengandung kata terlarang tersebut.")
        return
        
    print("\n" + "="*40)
    print(f" HASIL SCAN BAN WORD")
    print("="*40)
    for idx, (root_d, base_no_ext, reason) in enumerate(pending_deletions, 1):
        print(f"{idx}. {base_no_ext}\n   ^-- Alasan: {reason}\n")
        
    print(f"[!] Ditemukan total {len(pending_deletions)} pasang file yang melanggar aturan.")
    
    # 4. Confirmation Prompt
    confirm = input("\nApakah Anda YAKIN ingin menghapusnya secara PERMANEN? (Y/n): ").strip().upper()
    if confirm != 'Y':
        print("\n[!] Penghapusan dibatalkan oleh pengguna. Tidak ada file yang dihapus.")
        return
        
    # 5. Execute Mass Obliteration
    print("\n[+] Memulai proses penghapusan permanen...")
    for root_d, base_no_ext, reason in pending_deletions:
        mp4_path = os.path.join(root_d, base_no_ext + '.mp4')
        txt_path = os.path.join(root_d, base_no_ext + '.txt')
        
        deleted_something = False
        try:
            if os.path.exists(mp4_path):
                os.remove(mp4_path)
                deleted_something = True
                
            if os.path.exists(txt_path):
                os.remove(txt_path)
                deleted_something = True
                
            if deleted_something:
                deleted_pairs_count += 1
                print(f"[TERHAPUS] {base_no_ext}")
        except Exception as e:
            logger.error(f"Gagal menghapus {base_no_ext}: {e}")
            
    # Purge empty directories left behind
    for d in target_dirs:
        for root, dirs, files in os.walk(d, topdown=False):
            if root != d:
                try:
                    if not os.listdir(root):
                        os.rmdir(root)
                except Exception:
                    pass
                    
    print(f"\n[+] Sweeping selesai! {deleted_pairs_count} video+caption dihapus ke akar-akarnya.")
