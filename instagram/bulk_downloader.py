import sys
import os
from colorama import init, Fore, Style

# Add project root to path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.append(project_root)

from instagram.modules.logger import setup_logger, log_error
from instagram.modules.downloader import InstagramDownloader
from instagram.modules.utils import parse_date
from instagram.database.db_manager import init_db

init()

# Force UTF-8 encoding for Windows console to handle emojis
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

def main():
    os.system('cls' if os.name == 'nt' else 'clear')
    print(f"{Fore.MAGENTA}=== INSTAGRAM BULK PROFILE DOWNLOADER (yt-dlp) ==={Style.RESET_ALL}")
    
    # Ensure DB exists
    init_db()
    
    logger = setup_logger()
    downloader = InstagramDownloader(logger)
    
    while True:
        username = input(f"\n{Fore.GREEN}Enter Username (or 'q' to quit): {Style.RESET_ALL}").strip()
        if username.lower() == 'q':
            break
        if not username:
            continue
            
        print(f"\n{Fore.YELLOW}Options:{Style.RESET_ALL}")
        print("1. Download All")
        print("2. Download Since Date")
        print("3. Download Limit")
        
        opt = input("Choice: ").strip()
        
        since_date = None
        limit = None
        
        if opt == '2':
            d_str = input("Enter Date (YYYY-MM-DD): ").strip()
            since_date = parse_date(d_str)
            if not since_date:
                print("Invalid date.")
                continue
        elif opt == '3':
            try:
                limit = int(input("Enter limit: "))
            except:
                print("Invalid number.")
                continue
                
        print(f"{Fore.CYAN}Starting bulk download for '{username}'...{Style.RESET_ALL}")
        if downloader.download_profile(username, limit=limit, since_date=since_date):
             print(f"\n{Fore.GREEN}Batch complete for {username}.{Style.RESET_ALL}")
        else:
             print(f"\n{Fore.RED}Batch incomplete. Check logs.{Style.RESET_ALL}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nExiting...")
