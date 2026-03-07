import os
import sys
import sqlite3
from collections import defaultdict
from typing import List, Dict, Set
import json
import urllib.request
import urllib.error
import time
import subprocess

# Ensure we can import modules from parent/current dir
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

# Try imports
try:
    from youtube.yt_short_downloader.db_sqlite import SqliteStore
    from youtube.yt_short_downloader.orchestrator import download_videos_with_db
    from youtube.yt_short_downloader.config import DEFAULT_OUTPUT_DIR
    from youtube.yt_short_downloader.utils import create_safe_filename
    from youtube.utility.cleanup import cleanup_incomplete_downloads
    from youtube.yt_short_downloader.pytube_downloader import download_pytube
    from youtube.sort import sort_videos_by_channel
    from youtube.cek_resolusi import check_and_convert_video
except ImportError:
    # Fallback if run from root
    from yt_short_downloader.db_sqlite import SqliteStore
    from yt_short_downloader.orchestrator import download_videos_with_db
    from yt_short_downloader.config import DEFAULT_OUTPUT_DIR
    from yt_short_downloader.utils import create_safe_filename
    # Assuming relative path for these if generic import fails
    try:
        from utility.cleanup import cleanup_incomplete_downloads
        from yt_short_downloader.pytube_downloader import download_pytube
        from sort import sort_videos_by_channel
    except:
        pass

SKIPPED_FILE_NAME = "skipped.txt"

# --- HELPER FUNCS ---

def find_skipped_files(root_dir: str) -> List[str]:
    matches = []
    for root, dirs, files in os.walk(root_dir):
        if SKIPPED_FILE_NAME in files:
            matches.append(os.path.join(root, SKIPPED_FILE_NAME))
    return matches

def parse_skipped_file(filepath: str) -> List[Dict]:
    entries = []
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    for line in lines:
        line = line.strip()
        if not line: continue
        parts = line.split(" SKIP ", 1)
        if len(parts) < 2: continue
        content = parts[1]
        if " - " not in content: continue
        temp, url = content.rsplit(" - ", 1)
        if " - " not in temp: 
             pass
        try:
            vid_id, title = temp.split(" - ", 1)
        except ValueError:
            vid_id = temp.split(" ")[0]
            title = temp[len(vid_id):].strip("- ")

        entries.append({
            "line": line, 
            "id": vid_id.strip(),
            "title": title.strip(),
            "url": url.strip()
        })
    return entries

def get_channel_info(store: SqliteStore, video_id: str):
    try:
        with sqlite3.connect(store.db_path) as conn:
            query = """
                SELECT v.channel_key, c.name 
                FROM videos v
                JOIN channels c ON v.channel_key = c.key
                WHERE v.video_id = ?
            """
            cur = conn.execute(query, (video_id,))
            row = cur.fetchone()
            if row:
                return row[0], row[1]
    except Exception:
        pass
    return None, None

def get_all_downloaded_ids(output_dir: str) -> Set[str]:
    existing_ids = set()
    if not os.path.exists(output_dir):
        return existing_ids
    
    # Check all mp4 files
    all_files = []
    for root, dirs, files in os.walk(output_dir):
        for f in files:
             if f.lower().endswith(".mp4"):
                 all_files.append(f)
    return set(all_files)

def id_exists_in_files(vid_id: str, file_list: Set[str]) -> bool:
    for fname in file_list:
        if vid_id in fname:
            return True
    return False

def normalize_and_reconstruct_filenames(output_path: str):
    """
    1. Renames 'Retry - ...' files to remove the prefix.
    2. Scans metadata .txt files to map VideoID -> CorrectFilename.
    3. Renames .mp4 files to match the correct format (Index - Title - Channel).
    """
    print("  [NORMALIZE] 1. Stripping 'Retry -' prefix...")
    count_strip = 0
    for root, dirs, files in os.walk(output_path):
        for f in files:
            if f.startswith("Retry - "):
                old_path = os.path.join(root, f)
                new_name = f.replace("Retry - ", "", 1)
                new_path = os.path.join(root, new_name)
                try:
                    os.rename(old_path, new_path)
                    count_strip += 1
                except Exception as e:
                    print(f"    [ERR] Rename failed for {f}: {e}")
    
    if count_strip > 0:
        print(f"  [NORMALIZE] Stripped prefix from {count_strip} files.")

    print("  [NORMALIZE] 2. Reconstructing filenames from Metadata...")
    
    # Build Map: VideoID -> BaseFilename (from .txt)
    # .txt format: "Index - Title - Channel.txt" or "Title - ID.txt"
    # We trust the .txt filename is the desired target.
    id_to_base = {}
    
    # 1. Scan all txt files
    txt_files = []
    for root, dirs, files in os.walk(output_path):
        for f in files:
            if f.lower().endswith(".txt") and "skipped" not in f:
                txt_files.append(os.path.join(root, f))
    
    for txt_path in txt_files:
        try:
            with open(txt_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                # Find Link: ... v=VIDEO_ID
                match = None
                # Method A: Regex for youtube link
                # Link: https://www.youtube.com/watch?v=4zBZTAI34ts
                import re
                id_match = re.search(r'v=([a-zA-Z0-9_-]{11})', content)
                if id_match:
                    vid_id = id_match.group(1)
                    # Base name without ext
                    base_name = os.path.splitext(os.path.basename(txt_path))[0]
                    id_to_base[vid_id] = base_name
        except: pass
        
    print(f"  [METADATA] Mapped {len(id_to_base)} IDs from text files.")
    
    # 2. Scan mp4 files and rename if possible
    mp4_files = []
    for root, dirs, files in os.walk(output_path):
        for f in files:
             if f.lower().endswith(".mp4"):
                 mp4_files.append(os.path.join(root, f))
                 
    count_recon = 0
    for mp4_path in mp4_files:
        filename = os.path.basename(mp4_path)
        
        # Check if this file contains an ID we know
        # Strategy: check if any ID in our map is a substring of this filename
        # This is expensive O(N*M), but N (mp4) and M (ids) are small (~100).
        
        matched_id = None
        matched_base = None
        
        # Heuristic: Extract ID from filename end? "Title - ID.mp4"
        # Split by ' - ' and take last part?
        base_no_ext = os.path.splitext(filename)[0]
        parts = base_no_ext.split(' - ')
        if parts:
            potential_id = parts[-1].strip()
            if len(potential_id) == 11 and potential_id in id_to_base:
                matched_id = potential_id
                matched_base = id_to_base[potential_id]
        
        # Fallback: substring search
        if not matched_id:
            for vid_id, base in id_to_base.items():
                if vid_id in filename:
                    matched_id = vid_id
                    matched_base = base
                    break
        
        if matched_id and matched_base:
            # Check if rename needed
            current_base = os.path.splitext(filename)[0]
            if current_base != matched_base:
                dir_path = os.path.dirname(mp4_path)
                new_path = os.path.join(dir_path, matched_base + ".mp4")
                if not os.path.exists(new_path):
                    try:
                        os.rename(mp4_path, new_path)
                        count_recon += 1
                        # print(f"    [RENAME] {filename} -> {matched_base}.mp4")
                    except Exception as e:
                        print(f"    [ERR] Rename {filename}: {e}")
    
    if count_recon > 0:
        print(f"  [NORMALIZE] Reconstructed {count_recon} filenames to match Metadata.")
    else:
        print("  [NORMALIZE] Filenames already match metadata.")

# --- MAIN ---

def run_cookie_retry(video_url: str, output_path: str, browser: str) -> bool:
    """
    Attempts to download using cookies from a specific browser.
    """
    print(f"  [COOKIES] Trying with {browser} cookies...")
    
    # Construct base command
    cmd = [
        "yt-dlp",
        "--no-warnings", "--no-check-certificates", # --quiet removed for debug
        "--cookies-from-browser", browser,
        "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "-f", "bv*[height>=1080]+ba/b[height>=1080] / bv*[height>=720]+ba/b[height>=720]",
        "--merge-output-format", "mp4",
        "--match-filter", "duration <= 180",
        "-o", os.path.join(output_path, "%(title)s - %(id)s.%(ext)s"),
        video_url
    ]
    
    try:
        # Run yt-dlp directly and CAPTURE OUTPUT for debugging
        result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return True
    except subprocess.CalledProcessError as e:
        # PRINT DEBUG DETAIL
        print(f"    [DEBUG] {browser} Exit Code: {e.returncode}")
        if e.stderr:
            # Filter standard progress info, show only errors
            err_lines = [l for l in e.stderr.split('\n') if "ERROR" in l or "WARNING" in l]
            for l in err_lines[-3:]: # Show last 3 error lines
                print(f"    [DEBUG] {l}")
        return False
    except FileNotFoundError:
        print("    [ERR] yt-dlp not found in PATH.")
        return False

# --- MAIN ---

def main():
    print("Retry Skipped Videos Tool - Mega Resilience Mode")
    print("================================================")
    
    # Init DB
    try:
        store = SqliteStore()
        print(f"Database: {store.db_path}")
    except Exception as e:
        print(f"DB Error: {e}. Proceeding without DB.")
        store = None

    # Find skipped logs
    search_path = os.getcwd()
    candidates = find_skipped_files(search_path)
    
    target_file = None
    if not candidates:
        print(f"No '{SKIPPED_FILE_NAME}' found in {search_path}.")
        def_dl = os.path.join(search_path, "downloads")
        if os.path.exists(def_dl):
            candidates = find_skipped_files(def_dl)
        if not candidates:
             yt_dir = os.path.join(search_path, "youtube")
             if os.path.exists(yt_dir):
                 candidates = find_skipped_files(yt_dir)

    # Allow running purely for cleanup/sort if no skipped.txt found?
    # User might want to fix existing folder even if skipped.txt is missing/empty.
    # But usually this tool depends on finding the folder VIA skipped.txt location.
    
    if not candidates:
         print("Cannot find skipped.txt anywhere nearby.")
         # Try to guess output dir from current dir?
         print("Attempting to organize current directory instead...")
         output_dir = os.getcwd()
         # Skip retry logic, jump to cleanup
         raw_entries = []
    else:
        target_file = candidates[0]
        if len(candidates) > 1:
            print("Found multiple skipped files:")
            for i, p in enumerate(candidates):
                print(f"{i+1}. {p}")
            sel = input("Select file [1]: ").strip()
            if sel.isdigit() and 1 <= int(sel) <= len(candidates):
                target_file = candidates[int(sel)-1]

        print(f"Processing: {target_file}")
        output_dir = os.path.dirname(target_file)
        print(f"Output Directory: {output_dir}")
        
        # Parse items
        raw_entries = parse_skipped_file(target_file)
        print(f"  [QUEUE] Parsed {len(raw_entries)} entries.")

    # Deduplicate entries
    unique_entries = []
    seen_ids = set()
    for entry in raw_entries:
        if entry['id'] not in seen_ids:
            unique_entries.append(entry)
            seen_ids.add(entry['id'])
            
    if len(unique_entries) < len(raw_entries):
        diff = len(raw_entries) - len(unique_entries)
        print(f"  [QUEUE] Removed {diff} duplicates.")
    elif raw_entries: # Only print if there were entries to begin with
        print(f"  [QUEUE] No duplicates found.")

    # Check & Retry (Only if we have entries)
    to_download = []
    success_ids = set()
    
    if unique_entries:
        print("Checking for existing downloads (File System + DB)...")
        existing_files = get_all_downloaded_ids(output_dir)
        
        for entry in unique_entries:
            vid = entry['id']
            
            # Check Filesystem
            file_exists = id_exists_in_files(vid, existing_files)
            
            # Check DB
            db_exists = False
            if store:
                 # We can't check 'is_downloaded' easily without channel key, 
                 # but we can try to find if video exists in videos table
                 try:
                     with sqlite3.connect(store.db_path) as conn:
                         c = conn.cursor()
                         c.execute("SELECT 1 FROM videos WHERE video_id=? AND downloaded=1", (vid,))
                         if c.fetchone():
                             db_exists = True
                 except: pass

            if file_exists:
                print(f"  [EXIST-FILE] {vid} found on disk. Verified.")
                success_ids.add(vid)
                # Sync DB if needed
                if store and not db_exists:
                     ckey, _ = get_channel_info(store, vid)
                     if ckey: 
                        try: store.mark_downloaded(ckey, vid)
                        except: pass
            
            elif db_exists:
                 print(f"  [EXIST-DB] {vid} marked downloaded in DB.")
                 # If exact file missing, it might be renamed or moved. 
                 # For safety, if DB says yes but File say no, we might want to re-download?
                 # User said: "tetap di lakukan pengecekan atau di hapus" (keep checking or delete)
                 # Let's assume if it's in DB, we consider it done to avoid loop, UNLESS user wants strict re-download.
                 # But usually DB is source of truth for "already processed".
                 # However, if file is truly gone, we should re-download.
                 # Let's add to download list if file is missing, but log it.
                 print(f"    -> File missing. Re-queueing for download.")
                 to_download.append(entry)
                 
            else:
                to_download.append(entry)
                
        print(f"  {len(success_ids)} resolved (already exist).")
        print(f"  {len(to_download)} need retrying.")
    else:
        print("  [QUEUE] No items to retry.")
    
    if to_download:
        print("\nStarting Retry Process...")
        total_items = len(to_download)
        
        for i, entry in enumerate(to_download, 1):
            vid = entry['id']
            title = entry['title']
            url = entry['url']
            print(f"\n[{i}/{total_items}] Retrying: {title} ({vid})")
            

            # PHASE 1: STANDARD ORCHESTRATOR (Includes Pytube Fallback internally)
            # -----------------------------------------------
            success = False
            batch = [{"id": vid, "title": title, "upload_date": None}]
            cname = "Unknown Channel"
            ckey = "mb_retry_key"
            
            # Determine correct output folder (Channel based) if possible
            # But wait, download_videos_with_db puts files in output_path directly or channel subfolder?
            # It puts them in output_path. Main4 handles channel subfolders externally.
            # So here, we should ideally mimic Main4: output_dir/ChannelName
            
            target_out_path = output_dir
            if store:
                k, n = get_channel_info(store, vid)
                if k: ckey = k
                if n: 
                    cname = n
                    # Create channel folder structure
                    safe_cname = create_safe_filename(cname, 50)
                    target_out_path = os.path.join(output_dir, safe_cname)
                    if not os.path.exists(target_out_path):
                         os.makedirs(target_out_path, exist_ok=True)
                
            try:
                valid_store = store if store else SqliteStore()
                download_videos_with_db(
                    video_entries=batch,
                    output_path=target_out_path, # Use channel folder
                    channel_name=cname,
                    quality="best",
                    file_format="mp4",
                    channel_key=ckey,
                    store=valid_store
                )
            except Exception as e:
                # DEBUG: Print Standard failure reason
                print(f"  [DEBUG] Execution Failed: {e}")

            # Verify Success
            # Check either in channel folder OR root
            current_files_root = get_all_downloaded_ids(output_dir)
            current_files_sub = get_all_downloaded_ids(target_out_path)
            
            if id_exists_in_files(vid, current_files_root) or id_exists_in_files(vid, current_files_sub):
                print("  [SUCCESS] Downloaded & Validated.")
                success_ids.add(vid)
                success = True
                
                # --- POST-DOWNLOAD QUALITY CHECK (SHORTS ENFORCEMENT) ---
                # Check Duration & Ratio immediately
                # Find the actual file path
                found_paths = []
                # Check subfolder first
                if os.path.exists(target_out_path):
                    for f in os.listdir(target_out_path):
                        if vid in f and f.lower().endswith(('.mp4', '.webm', '.mkv')):
                            found_paths.append(os.path.join(target_out_path, f))
                
                # Also check root if not in sub
                if not found_paths and os.path.exists(output_dir):
                    for f in os.listdir(output_dir):
                        if vid in f and f.lower().endswith(('.mp4', '.webm', '.mkv')):
                            found_paths.append(os.path.join(output_dir, f))

                if found_paths:
                    try:
                        # Ensure 'check_and_convert_video' is available
                        if 'check_and_convert_video' in globals():
                             # This checks Ratio AND Duration (Max 180s)
                             # If rejected (duration > 180), it prints and moves to _LongVideos
                             check_and_convert_video(found_paths[0], target_mode='reels', force=False)
                    except Exception as e:
                        print(f"  [WARN] Validation Error: {e}")
                # ---------------------------------------------------------
            
            if not success:
                 print("  [FAIL] All strategies exhausted.")
                 
            # Cleanup per video
            try: cleanup_incomplete_downloads(target_out_path)
            except: pass


    # Rewrite skipped.txt & Cleanup Duplicates
    if target_file and (success_ids or len(unique_entries) < len(raw_entries)):
        remaining_lines = []
        for entry in raw_entries:
            # Drop if successful OR if it's a duplicate we already processed (handled implicitly by rewrite? No)
            # Actually, we want to Keep lines that failed.
            # If an ID succeeded, ALL lines with that ID should go.
            # If an ID failed, ALL lines with that ID should stay? Or just one?
            # Better to rewrite only UNIQUE failed entries to clean up the file.
            
            if entry['id'] not in success_ids:
                 remaining_lines.append(entry['line'])
        
        # Deduplicate remaining lines based on ID to clean up file
        final_lines = []
        seen_remaining = set()
        for line in remaining_lines:
            # We need to parse ID again or rely on order? 
            # Let's just blindly deduplicate exact lines for simplicity, or 
            # filter by ID.
            # Simpler: Just write back what wasn't successful.
            final_lines.append(line)

        try:
            with open(target_file, 'w', encoding='utf-8') as f:
                # We can do a set on lines to dedup exact duplicates
                unique_final_lines = list(dict.fromkeys(final_lines))
                for line in unique_final_lines:
                    f.write(line + "\n")
            
            removed_count = len(raw_entries) - len(unique_final_lines)
            print(f"\n[DONE] Updated {target_file}.")
            print(f"       Removed {len(success_ids)} successful items.")
            print(f"       Cleaned duplicates.")
        except Exception as e:
            print(f"Failed to save skipped.txt: {e}")
    else:
        print("\n[DONE] No new videos downloaded / No changes.")
        
    # POST-PROCESSING: Normalize, Cleanup, Sort
    print("\n[POST-PROCESSING] Cleaning up folder...")
    
    # Normalize Filenames (Remove 'Retry - ' and sync with .txt)
    normalize_and_reconstruct_filenames(output_dir)
    
    # Cleanup Junk
    try: cleanup_incomplete_downloads(output_dir)
    except: pass

    # Organize into Channels
    print("[ORGANIZING] Running Final Sort...")
    try:
        # Check if sort function is available
        if 'sort_videos_by_channel' in globals():
             sort_videos_by_channel(output_dir)
             print("[DONE] Files organized into channel folders.")
        else:
             print("[INFO] Sort function not available. Skipping sort.")
    except Exception as e:
        print(f"[WARN] Sort failed: {e}")

if __name__ == "__main__":
    main()
