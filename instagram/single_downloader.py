import sys
import os
from colorama import init, Fore, Style

# Add project root to path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.append(project_root)

from instagram.modules.logger import setup_logger, log_success, log_error
from instagram.modules.downloader import InstagramDownloader
from instagram.database.db_manager import init_db

init()

# Force UTF-8 encoding for Windows console to handle emojis
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

def main():
    os.system('cls' if os.name == 'nt' else 'clear')
    print(f"{Fore.MAGENTA}=== INSTAGRAM SINGLE POST DOWNLOADER (yt-dlp) ==={Style.RESET_ALL}")
    
    # Ensure DB exists
    init_db()
    
    logger = setup_logger()
    downloader = InstagramDownloader(logger)
    
    while True:
        url = input(f"\n{Fore.GREEN}Enter Post/Reel URL (or 'q' to quit): {Style.RESET_ALL}").strip()
        
        if url.lower() == 'q':
            break
            
        if not url:
            continue
            
        print(f"{Fore.CYAN}Processing with yt-dlp...{Style.RESET_ALL}")
        if downloader.download_post_by_url(url):
            log_success(logger, "Done!")
        else:
            print(f"{Fore.RED}Failed. Check logs.{Style.RESET_ALL}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nExiting...")
