import os
import yt_dlp
import subprocess
import threading
from tqdm import tqdm
import time
import traceback

MAX_RETRIES = 3  # Jumlah maksimum percobaan ulang jika gagal


def check_yt_dlp_installation():
    """Check if yt-dlp is properly installed and accessible"""
    try:
        result = subprocess.run(['yt-dlp', '--version'], 
                              stdout=subprocess.PIPE, 
                              stderr=subprocess.PIPE, 
                              text=True, 
                              timeout=10)
        if result.returncode == 0:
            print(f"yt-dlp version: {result.stdout.strip()}")
            return True
        else:
            print("yt-dlp is installed but not working properly")
            return False
    except FileNotFoundError:
        print("yt-dlp is not installed or not in PATH")
        print("Please install yt-dlp: pip install yt-dlp")
        return False
    except subprocess.TimeoutExpired:
        print("yt-dlp check timed out")
        return False
    except Exception as e:
        print(f"Error checking yt-dlp: {e}")
        return False


def get_short_links(channel_url, max_videos=None):
    ydl_opts = {
        'quiet': True,
        'extract_flat': True,
        'playlistend': max_videos if max_videos else None,
    }

    try:
        if '/@' in channel_url:
            channel_username = channel_url.split('/@')[1].split('/')[0]
            channel_url = f'https://www.youtube.com/@{channel_username}/shorts'
        else:
            channel_url = channel_url.split('/about')[0]
            channel_url += '/shorts'

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            result = ydl.extract_info(channel_url, download=False)

        if 'entries' in result:
            video_entries = result['entries'][:max_videos] if max_videos else result['entries']
            channel_name = result.get('uploader', channel_username)
            video_entries = sorted(video_entries, key=lambda v: v.get('upload_date', '99999999'))
            return video_entries, channel_name
        else:
            print("No videos found on the channel.")
            return [], ""

    except Exception as e:
        tb = traceback.format_exc()
        print(f"Error fetching video list: {e}")
        with open("download_errors.log", "a", encoding="utf-8") as log_file:
            log_file.write(f"Error fetching video list from {channel_url}:\n{tb}\n")
        return [], ""


def get_existing_index(output_path):
    files = os.listdir(output_path)
    indexes = [int(f.split(' - ')[0]) for f in files if f.split(' - ')[0].isdigit()]
    return max(indexes, default=0)


def sanitize_filename(title):
    import re
    import string
    
    # Remove emoji and other Unicode characters that can cause issues
    # This regex removes most emoji and special Unicode characters
    title = re.sub(r'[^\x00-\x7F]+', '', title)
    
    # Remove or replace problematic characters for file systems
    # Replace colons, slashes, backslashes, and other problematic chars
    title = re.sub(r'[<>:"/\\|?*]', '_', title)
    
    # Replace multiple underscores with single underscore
    title = re.sub(r'_+', '_', title)
    
    # Remove leading/trailing underscores and spaces
    title = title.strip(' _')
    
    # Limit length to avoid filesystem issues
    if len(title) > 200:
        title = title[:200]
    
    # Ensure it's not empty
    if not title:
        title = "untitled"
    
    return title


def create_safe_filename(title, max_length=100):
    """Create a filename that's safe for command line arguments"""
    import re
    
    # Remove all non-ASCII characters including emoji
    safe_title = re.sub(r'[^\x20-\x7E]', '', title)
    
    # Replace problematic characters
    safe_title = re.sub(r'[<>:"/\\|?*]', '_', safe_title)
    
    # Replace multiple spaces/underscores with single underscore
    safe_title = re.sub(r'[\s_]+', '_', safe_title)
    
    # Remove leading/trailing underscores
    safe_title = safe_title.strip('_')
    
    # Limit length
    if len(safe_title) > max_length:
        safe_title = safe_title[:max_length]
    
    # Ensure it's not empty
    if not safe_title:
        safe_title = "untitled"
    
    return safe_title


def validate_filename(filename):
    """Validate if a filename is safe for command line usage"""
    import re
    
    # Check for problematic characters
    if re.search(r'[<>:"/\\|?*\x00-\x1F\x7F-\x9F]', filename):
        return False
    
    # Check for non-ASCII characters
    if not filename.isascii():
        return False
    
    # Check length
    if len(filename) > 255:
        return False
    
    return True


def get_unique_filename(base_path, filename):
    """Get a unique filename to avoid conflicts"""
    if not os.path.exists(os.path.join(base_path, filename)):
        return filename
    
    name, ext = os.path.splitext(filename)
    counter = 1
    while True:
        new_filename = f"{name}_{counter}{ext}"
        if not os.path.exists(os.path.join(base_path, new_filename)):
            return new_filename
        counter += 1


def cleanup_partial_downloads(output_path, filename_pattern):
    """Clean up any partial downloads that might exist"""
    try:
        for file in os.listdir(output_path):
            if file.startswith(filename_pattern) and file.endswith('.part'):
                part_file = os.path.join(output_path, file)
                try:
                    os.remove(part_file)
                    print(f"Cleaned up partial file: {part_file}")
                except Exception as e:
                    print(f"Failed to clean up partial file {part_file}: {e}")
    except Exception as e:
        print(f"Error during cleanup: {e}")


def download_video(video_id, video_title, output_path, channel_name, quality, file_format, index):
    video_url = f"https://www.youtube.com/shorts/{video_id}"
    safe_title = create_safe_filename(video_title, max_length=80)  # Use shorter length for command line
    safe_channel = create_safe_filename(channel_name, max_length=50)
    filename = f"{index:02d} - {safe_title} - {safe_channel}.{file_format}"
    
    # Validate the filename
    if not validate_filename(filename):
        print(f"Warning: Generated filename may be problematic, using fallback: {filename}")
        # Use a simpler filename if validation fails
        filename = f"{index:02d} - video_{video_id}.{file_format}"
    
    filename = get_unique_filename(output_path, filename)
    file_path = os.path.join(output_path, filename)
    
    # Clean up any existing partial downloads
    cleanup_partial_downloads(output_path, f"{index:02d} - {safe_title}")
    
    # Create caption text first
    caption_text = f"{video_title} #shorts #vtuber #hololive\n\nYoutube: {channel_name}"
    caption_filename = f"{index:02d} - {safe_title} - {safe_channel}.txt"
    caption_filename = get_unique_filename(output_path, caption_filename)
    caption_file = os.path.join(output_path, caption_filename)
    
    # Always try to create caption file first
    try:
        with open(caption_file, 'w', encoding='utf-8') as f:
            f.write(caption_text)
        print(f"Caption created: {caption_file}")
    except Exception as e:
        print(f"Failed to create caption file: {e}")
        with open("download_errors.log", "a", encoding="utf-8") as log_file:
            log_file.write(f"Error creating caption for {video_url}:\n{e}\n")
        
        # Try with a simpler filename if the original fails
        try:
            simple_caption_file = os.path.join(output_path, f"{index:02d} - caption.txt")
            with open(simple_caption_file, 'w', encoding='utf-8') as f:
                f.write(caption_text)
            print(f"Caption created with simple filename: {simple_caption_file}")
        except Exception as e2:
            print(f"Failed to create caption file even with simple name: {e2}")
            with open("download_errors.log", "a", encoding="utf-8") as log_file:
                log_file.write(f"Error creating simple caption for {video_url}:\n{e2}\n")

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            cmd = [
                'yt-dlp',
                '--merge-output-format', file_format,
                '--output', file_path,
                '--no-warnings',  # Reduce noise in output
                '--quiet',  # Make output cleaner
                '--no-check-certificates',  # Avoid SSL issues
                '--ignore-errors',  # Continue on errors
                '--no-playlist',  # Ensure single video download
                '--extractor-args', 'youtube:player_client=android',  # Use mobile client for better compatibility
                '--user-agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'  # Use desktop user agent
            ]

            # Use different format selection based on quality
            if quality == 'best':
                # For best quality, let yt-dlp choose the best available format
                cmd.extend(['-f', 'best[ext=mp4]/best'])
            elif quality == 'worst':
                # For worst quality, get the smallest file
                cmd.extend(['-f', 'worst[ext=mp4]/worst'])
            else:
                # For specific quality, try the requested format first, then fallback
                cmd.extend(['-f', f'{quality}+bestaudio/best[ext=mp4]/best'])

            cmd.append(video_url)

            # Jalankan perintah yt-dlp
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
                timeout=300,  # 5 minute timeout
                encoding='utf-8',  # Explicit encoding
                errors='replace'  # Replace problematic characters
            )

            if not os.path.exists(file_path) or os.path.getsize(file_path) < 1000:
                raise Exception("Downloaded file is too small or missing, might be corrupted.")

            print(f"Downloaded successfully: {video_url}")
            break

        except subprocess.TimeoutExpired:
            error_msg = f"Attempt {attempt} timed out for {video_url}"
            print(error_msg)
            with open("download_errors.log", "a", encoding="utf-8") as log_file:
                log_file.write(error_msg + "\n")
            time.sleep(2 ** attempt)
        except subprocess.CalledProcessError as e:
            error_msg = (
                f"Attempt {attempt} failed for {video_url}\n"
                f"Command: {' '.join(cmd)}\n"
                f"Return Code: {e.returncode}\n"
                f"STDOUT:\n{e.stdout}\n"
                f"STDERR:\n{e.stderr}\n"
            )
            print(error_msg)

            with open("download_errors.log", "a", encoding="utf-8") as log_file:
                log_file.write(error_msg + "\n")

            # Check if it's a format availability issue
            if "Requested format is not available" in e.stderr or "HTTP Error 403" in e.stderr:
                print(f"Format not available for {video_url}, trying with best available format...")
                
                # Try with best available format
                try:
                    best_format = get_best_available_format(video_url)
                    if best_format:
                        cmd_with_best = [
                            'yt-dlp',
                            '--merge-output-format', file_format,
                            '--output', file_path,
                            '--no-warnings',
                            '--quiet',
                            '--no-check-certificates',
                            '--ignore-errors',
                            '--no-playlist',
                            '--extractor-args', 'youtube:player_client=android',
                            '--user-agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                            '-f', best_format,
                            video_url
                        ]
                        
                        result = subprocess.run(
                            cmd_with_best,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                            check=True,
                            timeout=300,
                            encoding='utf-8',
                            errors='replace'
                        )
                        
                        if os.path.exists(file_path) and os.path.getsize(file_path) >= 1000:
                            print(f"Downloaded successfully with best available format: {video_url}")
                            return True
                    else:
                        print(f"Could not determine best format for {video_url}")
                except Exception as format_error:
                    print(f"Best format download also failed: {format_error}")

            # Try with a simpler filename if the original fails
            if attempt == MAX_RETRIES:
                try:
                    simple_filename = f"{index:02d} - video_{video_id}.{file_format}"
                    simple_file_path = os.path.join(output_path, simple_filename)
                    
                    simple_cmd = [
                        'yt-dlp',
                        '--merge-output-format', file_format,
                        '--output', simple_file_path,
                        '--no-warnings',
                        '--quiet',
                        '--no-check-certificates',
                        '--ignore-errors',
                        '--no-playlist',
                        '--extractor-args', 'youtube:player_client=android',
                        '--user-agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                        '-f', 'best[ext=mp4]/best'
                    ]
                    
                    print(f"Trying with simple filename: {simple_filename}")
                    result = subprocess.run(
                        simple_cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        check=True,
                        timeout=300,
                        encoding='utf-8',
                        errors='replace'
                    )
                    
                    if os.path.exists(simple_file_path) and os.path.getsize(simple_file_path) >= 1000:
                        print(f"Downloaded successfully with simple filename: {video_url}")
                        return True
                        
                except Exception as fallback_error:
                    print(f"Fallback download also failed: {fallback_error}")
                    with open("download_errors.log", "a", encoding="utf-8") as log_file:
                        log_file.write(f"Fallback download failed for {video_url}:\n{fallback_error}\n")

            time.sleep(2 ** attempt)

            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    print(f"Corrupted file deleted: {file_path}")
                except Exception as cleanup_err:
                    print(f"Failed to delete corrupted file: {file_path}\n{cleanup_err}")
        except Exception as e:
            error_msg = (
                f"Attempt {attempt} failed for {video_url}\n"
                f"General Error: {e}\n"
            )
            print(error_msg)
            with open("download_errors.log", "a", encoding="utf-8") as log_file:
                log_file.write(error_msg + "\n")
            time.sleep(2 ** attempt)
    else:
        return False

    return True


def test_video_accessibility(video_url):
    """Test if a video is accessible before attempting download"""
    try:
        cmd = [
            'yt-dlp',
            '--no-download',
            '--no-warnings',
            '--quiet',
            '--no-check-certificates',
            '--extractor-args', 'youtube:player_client=android',
            '--user-agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            video_url
        ]
        
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
            encoding='utf-8',
            errors='replace'
        )
        
        return result.returncode == 0
    except Exception as e:
        print(f"Error testing video accessibility: {e}")
        return False


def get_available_formats(video_url):
    """Get available formats for a video"""
    try:
        cmd = [
            'yt-dlp',
            '--list-formats',
            '--no-warnings',
            '--quiet',
            '--no-check-certificates',
            video_url
        ]
        
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=60,
            encoding='utf-8',
            errors='replace'
        )
        
        if result.returncode == 0:
            return result.stdout
        else:
            return None
    except Exception as e:
        print(f"Error getting formats for {video_url}: {e}")
        return None


def get_best_available_format(video_url, preferred_format='mp4'):
    """Get the best available format for a video"""
    try:
        cmd = [
            'yt-dlp',
            '--list-formats',
            '--no-warnings',
            '--quiet',
            '--no-check-certificates',
            video_url
        ]
        
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=60,
            encoding='utf-8',
            errors='replace'
        )
        
        if result.returncode == 0:
            # Parse the output to find the best available format
            lines = result.stdout.split('\n')
            best_format = None
            
            for line in lines:
                if preferred_format in line.lower() and 'mp4' in line.lower():
                    # Look for format ID (first number in the line)
                    parts = line.split()
                    if parts and parts[0].isdigit():
                        best_format = parts[0]
                        break
            
            return best_format
        else:
            return None
    except Exception as e:
        print(f"Error getting best format for {video_url}: {e}")
        return None


def download_videos(video_entries, output_path, channel_name, quality, file_format):
    os.makedirs(output_path, exist_ok=True)
    start_index = get_existing_index(output_path) + 1

    total_videos = len(video_entries)
    progress_bar = tqdm(total=total_videos, desc="Downloading", unit="video")

    threads = []

    for i, entry in enumerate(video_entries):
        index = start_index + i
        thread = threading.Thread(target=download_video, args=(
            entry['id'], entry.get('title', 'Unknown Title'), output_path,
            channel_name, quality, file_format, index))
        thread.start()
        threads.append(thread)

    for thread in threads:
        thread.join()
        progress_bar.update(1)

    progress_bar.close()


def main():
    try:
        print("YouTube Shorts Bulk Downloader")
        print("=" * 40)
        
        # Check yt-dlp installation first
        print("Checking yt-dlp installation...")
        if not check_yt_dlp_installation():
            print("Please install yt-dlp and try again.")
            return
        
        print("\n" + "=" * 40)
        
        channel_url = input("Enter the YouTube channel URL: ").strip()
        
        if not channel_url:
            print("No URL provided. Exiting.")
            return

        print("Fetching video list for preview...")
        all_video_entries, channel_name = get_short_links(channel_url)

        if not all_video_entries:
            print("No videos found or failed to fetch links.")
            return

        print(f"\nTotal videos found on channel '{channel_name}': {len(all_video_entries)}")

        preview_count = min(len(all_video_entries), 10)
        print(f"\nPreviewing first {preview_count} videos:")
        for i, entry in enumerate(all_video_entries[:preview_count], start=1):
            title = entry.get('title', 'Unknown Title')
            # Truncate long titles for display
            if len(title) > 80:
                title = title[:77] + "..."
            print(f"{i}. {title}")

        confirm_preview = input("\nDo you want to continue? (y/n): ").strip().lower()
        if confirm_preview != 'y':
            print("Operation cancelled.")
            return

        max_videos_input = input(f"Enter the number of videos to download (1-{len(all_video_entries)}), leave blank for all: ").strip()
        
        try:
            max_videos = int(max_videos_input) if max_videos_input.isdigit() else None
            if max_videos is not None and (max_videos < 1 or max_videos > len(all_video_entries)):
                print(f"Invalid number. Using all {len(all_video_entries)} videos.")
                max_videos = None
        except ValueError:
            print("Invalid input. Using all videos.")
            max_videos = None

        video_entries, _ = get_short_links(channel_url, max_videos)
        if not video_entries:
            print("No videos found or failed to fetch links.")
            return

        print("\nQuality options:")
        print("1. best - Best available quality (recommended)")
        print("2. worst - Smallest file size")
        print("3. 137+140 - 1080p video + audio (may not be available for all videos)")
        print("4. 136+140 - 720p video + audio (may not be available for all videos)")
        print("5. 135+140 - 480p video + audio (may not be available for all videos)")
        
        quality_input = input("Enter quality choice (1-5, default: 1): ").strip()
        
        quality_map = {
            '1': 'best',
            '2': 'worst', 
            '3': '137+140',
            '4': '136+140',
            '5': '135+140'
        }
        
        quality = quality_map.get(quality_input, 'best')
        print(f"Selected quality: {quality}")

        file_format = input("Enter file format (MP4/WEBM, default: MP4): ").strip().lower()
        file_format = file_format if file_format in ['mp4', 'webm'] else 'mp4'

        output_directory = os.path.join(os.getcwd(), "new_week")
        os.makedirs(output_directory, exist_ok=True)

        print(f"\nVideos to Download ({len(video_entries)} total):")
        for i, entry in enumerate(video_entries, start=1):
            title = entry.get('title', 'Unknown Title')
            if len(title) > 60:
                title = title[:57] + "..."
            print(f"{i}. {title}")

        confirm = input("\nProceed with download? (y/n): ").strip().lower()
        if confirm != 'y':
            print("Download canceled.")
            return

        print(f"Starting download in {output_directory}...")
        print("Note: Caption files will be created for all videos, even if download fails.")
        download_videos(video_entries, output_directory, channel_name, quality, file_format)
        
        print("\nDownload process completed!")
        print(f"Check the 'new_week' folder for downloaded videos and caption files.")
        print("Any errors were logged to 'download_errors.log'")
        
    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user.")
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")
        with open("download_errors.log", "a", encoding="utf-8") as log_file:
            log_file.write(f"Unexpected error in main: {e}\n")
        print("Check 'download_errors.log' for details.")


if __name__ == "__main__":
    main()
