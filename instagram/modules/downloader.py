import yt_dlp
import instaloader
import os
import datetime
from instagram.database.db_manager import check_exists, add_download, init_db
from instagram.settings import DOWNLOAD_DIR, BASE_DIR
from instagram.modules.utils import smart_sleep
from colorama import Fore, Style

class InstagramDownloader:
    def __init__(self, logger):
        self.logger = logger
        self.save_metadata = True # Default to True, can be toggled
        
        # Ensure DB is ready
        init_db()
        
        # Initialize Instaloader for scanning
        self.L = instaloader.Instaloader(

            download_pictures=False,
            download_videos=False,
            save_metadata=False,
            compress_json=False,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )
        
        # Initialize yt_dlp options
        self.ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': True,
            'nocheckcertificate': True,
            'write_description': False, # Manual hook handles this to ensure .txt format and custom fields
            # We will override 'outtmpl' per request
        }
        
        # Attempt to load session
        self._load_session()

    # _save_caption_hook removed - replaced by post-download logic

    def _load_session(self):
        """Load session file if it exists (CWD or AppData)."""
        loaded = False
        
        # 1. Check CWD
        session_files = [f for f in os.listdir(os.getcwd()) if f.startswith("session-")]
        if session_files:
            try:
                filename = session_files[0]
                self.username = filename.replace("session-", "")
                self.L.load_session_from_file(self.username, filename=filename)
                self.logger.info(f"{Fore.GREEN}Loaded session from CWD: {self.username}{Style.RESET_ALL}")
                loaded = True
            except Exception as e:
                self.logger.error(f"Failed to load CWD session: {e}")
                
        # 2. Check AppData (Standard Instaloader Path)
        if not loaded:
            try:
                # Windows AppData path
                appdata = os.getenv('LOCALAPPDATA')
                if appdata:
                    instaloader_dir = os.path.join(appdata, 'Instaloader')
                    if os.path.exists(instaloader_dir):
                        sessions = [f for f in os.listdir(instaloader_dir) if f.startswith("session-")]
                        if sessions:
                            filename = sessions[0]
                            path = os.path.join(instaloader_dir, filename)
                            self.username = filename.replace("session-", "")
                            self.L.load_session_from_file(self.username, filename=path)
                            self.logger.info(f"{Fore.GREEN}Loaded session from AppData: {self.username}{Style.RESET_ALL}")
                            loaded = True
            except Exception as e:
                self.logger.debug(f"Checked AppData but failed: {e}")

    def login(self, username=None):
        """
        Login using hardcoded 'tumbal' credentials or interactive.
        If username is 'npemburuu' (or generic input), we force the known working credentials.
        """
        try:
            # HARDCODED CREDENTIALS (TUMBAL)
            tumbal_user = "npemburuu"
            tumbal_pass = "qwerty180103"
            
            target_user = username if username else tumbal_user
            
            # If user inputs the tumbal username or we want to force it
            if target_user == tumbal_user:
                self.logger.info(f"Logging in with hardcoded account: {tumbal_user}...")
                self.L.login(tumbal_user, tumbal_pass)
            else:
                # Fallback to interactive for other users
                from getpass import getpass
                self.logger.info(f"Logging in as {target_user}...")
                self.L.interactive_login(target_user)
                
            self.L.save_session_to_file()
            
            # FORCE COPY to CWD to ensure persistence and visibility
            try:
                import shutil
                appdata = os.getenv('LOCALAPPDATA')
                if appdata:
                    src = os.path.join(appdata, 'Instaloader', f"session-{target_user}")
                    dst = os.path.join(os.getcwd(), f"session-{target_user}")
                    if os.path.exists(src):
                        shutil.copy2(src, dst)
                        self.logger.info(f"{Fore.GREEN}Session file copied to project root: {dst}{Style.RESET_ALL}")
            except Exception as e:
                self.logger.warning(f"Could not copy session to root: {e}")

            self.logger.info(f"{Fore.GREEN}Login successful! Session saved.{Style.RESET_ALL}")
            
        except Exception as e:
            self.logger.error(f"Login failed: {e}")
            if "config" in str(e):
                self.logger.error(f"{Fore.YELLOW}Tip: This IP might be flagged. Try using a VPN or mobile data.{Style.RESET_ALL}")

    def _get_target_dir(self, username):
        """Construct the target directory path."""
        # instagram/instagram_downloads/{username}
        return os.path.join(DOWNLOAD_DIR, username)

    def download_post_by_url(self, url):
        """Download a single post using yt-dlp."""
        try:
            # We don't have the username easily from just the URL without fetching info first.
            # But yt-dlp can extract it.
            # Strategy: Let yt-dlp handle extraction. 
            # We'll set a generic structure first, or let yt-dlp determine output.
            
            # To fetch info first without downloading:
            info = self._fetch_info(url)
            if not info:
                self.logger.error("Failed to fetch info from URL.")
                return False

            shortcode = info.get('id')
            
            # CRITICAL FIX: Use handle for folder name, not Display Name
            # Attempt to get handle from 'uploader' (sometimes handle) or 'uploader_id' (sometimes numeric)
            # Safest: Extract from URL or check specific fields
            # User reported uploader_id is numeric ID.
            # We will use our robust utility to get the handle from the URL
            from instagram.modules.utils import extract_username_from_input
            
            clean_handle = extract_username_from_input(info.get('webpage_url', url))
            if not clean_handle:
                 # Fallback
                 clean_handle = info.get('uploader') or info.get('uploader_id') or 'unknown_user'
                 
            # Store handle in info for save_caption to use
            info['final_handle'] = clean_handle
            
            # Check DB
            if check_exists(shortcode):
                self.logger.info(f"{Fore.YELLOW}Post {shortcode} already downloaded. Skipping.{Style.RESET_ALL}")
                return True

            target_dir = self._get_target_dir(clean_handle)
            os.makedirs(target_dir, exist_ok=True)

            self.logger.info(f"Downloading {shortcode} from {clean_handle}...")
            
            # Output template: YYYYMMDD_Handle_shortcode.ext
            # Matches user request for date_user_media format
            # We manually inject the handle into the template to guarantee consistency
            out_tmpl = os.path.join(target_dir, f"%(upload_date)s_{clean_handle}_%(id)s.%(ext)s")
            
            success, final_path = self._run_download(url, out_tmpl, override_handle=clean_handle)
            
            if success:
                # Add to DB
                # Extracts just filename
                fname = os.path.basename(final_path)
                
                # Detect media type
                ext = os.path.splitext(fname)[1].lower()
                media_type = "image" if ext in ['.jpg', '.jpeg', '.png', '.webp'] else "video"
                
                add_download(shortcode, fname, media_type, clean_handle)
                return True
            else:
                return False

        except Exception as e:
            self.logger.error(f"Download error: {e}")
            return False

    def _get_next_index(self, username):
        """Find the highest number in existing filenames: Username_([0-9]+)."""
        target_dir = self._get_target_dir(username)
        if not os.path.exists(target_dir):
            return 1
            
        max_idx = 0
        import re
        # Pattern: Username_123.mp4 (or other ext)
        # We need to escape username mainly if it has special chars, but usually it's clean.
        # Let's assume username is safe or strict regex.
        # Actually simplest is to split by '_' and assume format.
        
        esc_user = re.escape(username)
        pattern = re.compile(rf"^{esc_user}_(\d+)\.\w+$")
        
        for fname in os.listdir(target_dir):
            match = pattern.match(fname)
            if match:
                try:
                    val = int(match.group(1))
                    if val > max_idx:
                        max_idx = val
                except ValueError:
                    pass
        return max_idx + 1

    def download_profile(self, username, limit=None, since_date=None):
        """
        Hybrid Method (Threaded):
        1. Scan with Instaloader (Auth -> Fallback to Guest).
        2. Submit downloads to ThreadPoolExecutor.
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from instagram.settings import MAX_WORKERS
        
        target_dir = self._get_target_dir(username)
        os.makedirs(target_dir, exist_ok=True)
        
        # Calculate Starting Index for Sequential Numbering
        current_sequence = self._get_next_index(username)
        self.logger.info(f"Sequential Numbering: Starting at {username}_{current_sequence}")
        
        self.logger.info(f"Scanning profile {username}...")
        
        # Helper to process posts (Producer)
        def process_iterator(posts_iterator, label="Auth"):
            nonlocal current_sequence # Allow modification
            count = 0
            skipped_consecutive = 0 # Track duplicate streak
            futures = []
            
            # Setup ThreadPool
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                try:
                    for post in posts_iterator:
                        if limit and count >= limit:
                            self.logger.info(f"Limit of {limit} reached.")
                            break
                        
                        if since_date and post.date < since_date:
                            self.logger.info(f"Reached posts older than {since_date.date()}. Stopping.")
                            break
                        
                        if since_date and post.date < since_date:
                            self.logger.info(f"Reached posts older than {since_date.date()}. Stopping.")
                            break
                        
                        if check_exists(post.shortcode):
                            skipped_consecutive += 1
                            if skipped_consecutive >= 15:
                                self.logger.info(f"{Fore.YELLOW}Found 15 consecutive existing items. Stopping scan (Smart Resume).{Style.RESET_ALL}")
                                break
                            self.logger.info(f"Skipping {post.shortcode} (In DB) [Streak: {skipped_consecutive}/15]")
                            continue
                        
                        # Reset streak if we found a new item
                        skipped_consecutive = 0
                        
                        # Prepare args for worker
                        post_url = f"https://www.instagram.com/p/{post.shortcode}/"
                        
                        # NEW FORMAT: Username_1.mp4 (Sequential)
                        # Explicitly pass the full filename to template to force it
                        # But wait, yt-dlp templates... we can just give fixed name if we are sure?
                        # No, we need extension. %(ext)s is mostly mp4. 
                        # We can use formatted string in out_tmpl
                        
                        filename_tmpl = f"{username}_{current_sequence}"
                        out_tmpl = os.path.join(target_dir, f"{filename_tmpl}.%(ext)s")
                        
                        self.logger.info(f"[{label}] [{count+1}] Queuing {post.shortcode} -> {filename_tmpl}...")
                        
                        # Submit to pool
                        futures.append(
                            executor.submit(self._threaded_download, post_url, out_tmpl, shortcode=post.shortcode, date_obj=post.date, username=username)
                        )
                        count += 1
                        current_sequence += 1 # Increment for next file
                        
                        # We still sleep in the Producer loop to not hammer the SCAN endpoint
                        smart_sleep()
                        
                except Exception as e:
                    self.logger.error(f"Error during {label} scan loop: {e}")
            
            # Wait for all futures (Context manager handles this, but we can log results)
            self.logger.info("Waiting for all background downloads to finish...")
            
            success_count = 0
            for future in as_completed(futures):
                if future.result():
                    success_count += 1
                    
            return success_count

        # TRY 1: Authenticated Scan
        try:
            profile = instaloader.Profile.from_username(self.L.context, username)
            total = process_iterator(profile.get_posts(), label="Auth")
            self.logger.info(f"{Fore.GREEN}Batch processing complete. Downloaded {total} new items.{Style.RESET_ALL}")
            return True

        except (instaloader.ConnectionException, instaloader.LoginRequiredException) as e:
            self.logger.warning(f"Authenticated scan failed: {e}")
            self.logger.info(f"{Fore.YELLOW}Switching to GUEST MODE (No Login) to bypass rate limit...{Style.RESET_ALL}")
            
            # TRY 2: Guest Scan (New Instance)
            try:
                # Create a fresh, anonymous instance
                L_guest = instaloader.Instaloader(
                    download_pictures=False,
                    download_videos=False,
                    save_metadata=False,
                    compress_json=False,
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
                )
                profile_guest = instaloader.Profile.from_username(L_guest.context, username)
                total = process_iterator(profile_guest.get_posts(), label="Guest")
                self.logger.info(f"{Fore.GREEN}Guest Batch processing complete. Downloaded {total} new items.{Style.RESET_ALL}")
                return True
                
            except Exception as guest_e:
                self.logger.error(f"Guest mode also failed: {guest_e}")
                return False
                
        except Exception as e:
             self.logger.error(f"Profile scan error: {e}")
             return False

    def _save_caption(self, info, video_path):
        """Save caption to .txt directly matching the video filename."""
        description = info.get('description')
        if not description or not video_path:
            return

        try:
            target_dir = os.path.dirname(video_path)
            # Ensure we strip extension correctly to match video
            base_name = os.path.splitext(os.path.basename(video_path))[0]
            txt_filename = f"{base_name}.txt"
            txt_path = os.path.join(target_dir, txt_filename)
            
            # Write to file
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write(description)
                f.write("\n\n---\n")
                f.write(f"Source: {info.get('webpage_url')}\n")
                f.write(f"Uploader: {info.get('uploader')}\n")
                f.write(f"Date: {info.get('upload_date')}\n")
                
                # Use handle if we injected it, otherwise look for standard keys
                handle = info.get('final_handle') or info.get('uploader_id')
                f.write(f"User_IG: {handle}\n")
            
            self.logger.info(f"{Fore.GREEN}Saved caption to: {txt_filename}{Style.RESET_ALL}")
                
        except Exception as e:
            self.logger.error(f"Failed to save caption: {e}")

    def _load_session(self):
        # ... (Existing code, not changing this part, but replace blocks need context)
        # Actually I will just replace the relevant methods below.
        pass

    def _threaded_download(self, url, out_tmpl, shortcode, date_obj, username):
        """Worker function for threading."""
        try:
             success, final_filename = self._run_download(url, out_tmpl)
             if success and final_filename:
                # Use regex or simple replace to ensure clean db entry if needed
                # But filename from run_download is full path.
                # DB expects just filename usually? Or simplified?
                # db_manager add_download usually takes specific filename.
                
                # We need to extract just the basename for consistency with existing DB logic
                fname = os.path.basename(final_filename)
                
                # Detect media type
                ext = os.path.splitext(fname)[1].lower()
                media_type = "image" if ext in ['.jpg', '.jpeg', '.png', '.webp'] else "video"
                
                # Check format used in run_download, usually returns filepath
                add_download(shortcode, fname, media_type, username)
                return True
        except Exception as e:
            self.logger.error(f"Thread error for {shortcode}: {e}")
        return False

    def _fetch_info(self, url):
        """Helper to get video info without downloading."""
        try:
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                return ydl.extract_info(url, download=False)
        except Exception as e:
            self.logger.error(f"Info fetch error: {e}")
            return None

    def _run_download(self, url, out_tmpl, override_handle=None):
        """Helper to run a single download and return status + filename."""
        opts = self.ydl_opts.copy()
        opts['outtmpl'] = out_tmpl
        opts['write_description'] = False # Ensure disabled

        # No progress hooks for caption needed anymore

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                # Use extract_info with download=True to get metadata AND download
                info = ydl.extract_info(url, download=True)
                
                if override_handle:
                    info['final_handle'] = override_handle
                
                # Get the final filename determined by yt-dlp
                filename = ydl.prepare_filename(info)
                
                # Save caption NOW, using the final info and filename
                if self.save_metadata:
                    self._save_caption(info, filename)
                
                return True, filename
        except Exception as e:
            self.logger.error(f"Execution error: {e}")
            return False, None
