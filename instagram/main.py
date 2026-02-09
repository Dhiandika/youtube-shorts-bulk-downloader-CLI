import sys
import os
import datetime
from colorama import init, Fore, Style

# Add project root to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.append(project_root)

from instagram.modules.logger import setup_logger, log_info, log_error, log_success
from instagram.modules.downloader import InstagramDownloader
from instagram.modules.utils import parse_date, extract_username_from_input
from instagram.database.db_manager import init_db, get_history, reset_db

# Initialize Colorama
init()

# Force UTF-8 encoding for Windows console to handle emojis
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

def print_header(caption_mode=True):
    os.system('cls' if os.name == 'nt' else 'clear')
    print(f"{Fore.MAGENTA}=============================================")
    print(f"   INSTAGRAM BULK DOWNLOADER (Feed & Reels)")
    print(f"   (Powered by yt-dlp)")
    print(f"============================================={Style.RESET_ALL}")
    
    # Mode Indicator
    mode_str = f"{Fore.GREEN}ON{Style.RESET_ALL}" if caption_mode else f"{Fore.RED}OFF{Style.RESET_ALL}"
    print(f"{Fore.CYAN}Features: Ghost Mode, Resume Capability, Smart Organization{Style.RESET_ALL}")
    print(f"Captions (.txt): [{mode_str}]")
    
    # Show Login Status if possible
    # Check CWD first
    session_files = [f for f in os.listdir(os.getcwd()) if f.startswith("session-")]
    
    # Check AppData if not in CWD
    if not session_files:
        appdata = os.getenv('LOCALAPPDATA')
        if appdata and os.path.exists(os.path.join(appdata, 'Instaloader')):
            path = os.path.join(appdata, 'Instaloader')
            session_files = [f for f in os.listdir(path) if f.startswith("session-")]
            
    if session_files:
        # Extract username from the first found session file
        user = session_files[0].replace("session-", "")
        print(f"{Fore.GREEN}Status: Logged in as {user}{Style.RESET_ALL}\n")
    else:
        print(f"{Fore.YELLOW}Status: Guest Mode (Limited){Style.RESET_ALL}\n")

def main_menu():
    print(f"{Fore.YELLOW}Select Mode:{Style.RESET_ALL}")
    print("1. Download Single Post/Reel (URL)")
    print("2. Download Profile (Batch - via yt-dlp)")
    print("3. View Download History")
    print("4. Download from 'batch_urls.txt' (Manual List)")
    print(f"5. Login (Generate Session for Batch Mode)")
    print("6. Exit")
    print(f"7. Toggle Captions (ON/OFF)")
    return input(f"\n{Fore.GREEN}Choice > {Style.RESET_ALL}").strip()

def profile_menu():
    print(f"\n{Fore.YELLOW}Profile Download Options:{Style.RESET_ALL}")
    print("1. Download All Posts")
    print("2. Download Since Date (e.g., 2024-01-01)")
    print("3. Download Limit")
    print("4. Back")
    print("4. Back")
    return input(f"\n{Fore.GREEN}Choice > {Style.RESET_ALL}").strip()



def run():
    # Setup
    init_db()
    logger = setup_logger()
    downloader = InstagramDownloader(logger)
    
    # Global Toggle State (Default ON)
    caption_mode = True 
    
    while True:
        # Sync downloader state
        downloader.save_metadata = caption_mode
        print_header(caption_mode)
        choice = main_menu()
        
        if choice == '1':
            url = input("Enter Post/Reel URL: ").strip()
            if url:
                print(f"\n{Fore.CYAN}Starting download...{Style.RESET_ALL}")
                if downloader.download_post_by_url(url):
                    log_success(logger, "Process successful!")
                input("\nPress Enter to continue...")
                
        elif choice == '2':
            print(f"\n{Fore.CYAN}Tip: You can enter multiple usernames/URLs separated by comma (,){Style.RESET_ALL}")
            raw_input = input("Enter Username(s) or Profile URL(s): ").strip()
            
            if not raw_input:
                continue
            
            # Split and clean
            targets = [x.strip() for x in raw_input.split(',')]
            
            p_choice = profile_menu()
            if p_choice == '4':
                continue
                
            # 1. Ask Options First
            limit = None
            since_date_obj = None
            
            if p_choice == '2':
                date_str = input("Enter Date (YYYY-MM-DD): ").strip()
                since_date_obj = parse_date(date_str)
                if not since_date_obj:
                    log_error(logger, "Invalid date format. Skipping date filter.")
            
            elif p_choice == '3':
                try:
                    limit = int(input("Enter number of posts: "))
                except ValueError:
                    log_error(logger, "Invalid number. Defaulting to None.")

            # 2. Loop Execution
            for i, target_raw in enumerate(targets, 1):
                username = extract_username_from_input(target_raw)
                
                if not username:
                    log_error(logger, f"Skipping invalid input: {target_raw}")
                    continue
                    
                print(f"\n{Fore.MAGENTA}=== [{i}/{len(targets)}] Processing: {username} ==={Style.RESET_ALL}")
                
                if p_choice in ['1', '2', '3']:
                    downloader.download_profile(username, limit=limit, since_date=since_date_obj)
            
            input("\nBatch operation finished. Press Enter to continue...")
                
        elif choice == '3':
            os.system('cls' if os.name == 'nt' else 'clear')
            print(f"{Fore.YELLOW}=== Recent Download History ==={Style.RESET_ALL}")
            history = get_history(limit=15)
            
            if history:
                # Header
                print(f"{Fore.CYAN}{'Date':<18} | {'Uploader':<15} | {'Filename (Truncated)'}{Style.RESET_ALL}")
                print("-" * 75)
                
                for item in history:
                    # item: shortcode, filename, media_type, timestamp, uploader
                    # Handle legacy data where column might be missing or None
                    try:
                        shortcode = item[0]
                        filename = item[1] if item[1] else "Unknown"
                        timestamp = item[3]
                        uploader = item[4] if len(item) > 4 and item[4] else "N/A"
                        
                        # Clean Timestamp (remove ms)
                        if isinstance(timestamp, str):
                            ts_display = timestamp.split('.')[0]
                        else:
                            ts_display = str(timestamp)
                            
                        # Truncate Filename
                        fname_display = (filename[:35] + '..') if len(filename) > 35 else filename
                        # Truncate Uploader
                        uploader_display = (uploader[:13] + '..') if len(uploader) > 13 else uploader
                        
                        print(f"{ts_display:<18} | {uploader_display:<15} | {fname_display}")
                        
                    except IndexError:
                        continue
                        
                print("-" * 75)
            else:
                print("No history found.")
            
            print(f"\n{Fore.YELLOW}Options:{Style.RESET_ALL}")
            print("1. Back")
            print("2. Reset/Clear History (For Testing)")
            h_choice = input(f"{Fore.GREEN}Choice > {Style.RESET_ALL}").strip()
            
            if h_choice == '2':
                confirm = input(f"{Fore.RED}Are you sure you want to clear ALL history? (y/N) > {Style.RESET_ALL}").lower()
                if confirm == 'y':
                    reset_db()
                    input("History cleared. Press Enter to continue...")
            # else loop back or continue loop (block ends, loop restarts)
            
        elif choice == '4':
            # Batch from File
            file_path = "instagram/batch_urls.txt"
            if not os.path.exists(file_path):
                 file_path = "batch_urls.txt" # Try root
            
            if os.path.exists(file_path):
                print(f"\n{Fore.CYAN}Reading list from {file_path}...{Style.RESET_ALL}")
                try:
                    with open(file_path, 'r') as f:
                        lines = [line.strip() for line in f if line.strip() and not line.startswith('#')]
                    
                    if lines:
                        print(f"Found {len(lines)} items. Starting advanced processing...")
                        
                        for i, line in enumerate(lines, 1):
                            # Parse Line: "Input | Limit"
                            parts = [p.strip() for p in line.split('|')]
                            raw_input = parts[0]
                            limit = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
                            
                            print(f"\n{Fore.MAGENTA}>>> [{i}/{len(lines)}] Processing: {raw_input} (Limit: {limit or 'ALL'}){Style.RESET_ALL}")
                            
                            # Detect Type: Post or Profile?
                            is_post = False
                            if "instagram.com/p/" in raw_input or "instagram.com/reel/" in raw_input or "instagram.com/tv/" in raw_input:
                                is_post = True
                            
                            if is_post:
                                # Process as Single Post
                                downloader.download_post_by_url(raw_input)
                            else:
                                # Process as Profile
                                user = extract_username_from_input(raw_input)
                                if user:
                                    downloader.download_profile(user, limit=limit)
                                else:
                                    log_error(logger, f"Invalid Profile/URL: {raw_input}")
                                    
                            print("-" * 40)
                            
                        log_success(logger, "Batch file processing complete!")
                    else:
                        print("File is empty or contains only comments.")
                except Exception as e:
                    log_error(logger, f"Error processing file: {e}")
            else:
                print(f"{Fore.RED}File 'batch_urls.txt' not found.{Style.RESET_ALL}")
                print("Please create 'instagram/batch_urls.txt' and follow the rules inside.")
            input("\nPress Enter to continue...")

        elif choice == '5':
            username = input("Enter Instagram Username: ").strip()
            if username:
                print(f"\n{Fore.CYAN}Please enter your password in the prompt that appears...{Style.RESET_ALL}")
                try:
                    downloader.login(username)
                except Exception as e:
                    log_error(logger, f"Login Error: {e}")
            input("\nPress Enter to continue...")

        elif choice == '6':
            print("Exiting...")
            break
            
        elif choice == '7':
            # Toggle Mode
            caption_mode = not caption_mode
            status = "ENABLED" if caption_mode else "DISABLED"
            print(f"\n{Fore.GREEN}Captions are now {status}.{Style.RESET_ALL}")
            # Loop will refresh header
            
        else:
            print("Invalid choice.")
            
if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print(f"\n{Fore.RED}Operation cancelled by user.{Style.RESET_ALL}")
        sys.exit(0)
