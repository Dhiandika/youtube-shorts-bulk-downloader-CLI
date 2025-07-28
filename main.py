import os
import yt_dlp
import subprocess
import threading
from tqdm import tqdm
import time
import traceback

MAX_RETRIES = 3  # Jumlah maksimum percobaan ulang jika gagal


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
    # Hanya huruf, angka, spasi, dan karakter aman
    return re.sub(r'[^a-zA-Z0-9 _\-\(\)\[\]]+', '_', title).strip()


def download_video(video_id, video_title, output_path, channel_name, quality, file_format, index):
    video_url = f"https://www.youtube.com/shorts/{video_id}"
    safe_title = sanitize_filename(video_title)
    safe_channel = sanitize_filename(channel_name)
    filename = f"{index:02d} - {safe_title} - {safe_channel}.{file_format}"
    file_path = os.path.join(output_path, filename)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            cmd = [
                'yt-dlp',
                '--merge-output-format', file_format,
                '--output', file_path
            ]

            if quality != 'best':
                cmd.extend(['-f', quality])

            cmd.append(video_url)

            # Jalankan perintah yt-dlp
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True
            )

            if not os.path.exists(file_path) or os.path.getsize(file_path) < 1000:
                raise Exception("Downloaded file is too small or missing, might be corrupted.")

            print(f"Downloaded successfully: {video_url}")
            break

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

    # Simpan caption deskripsi
    caption_text = f"{video_title} #shorts #vtuber #hololive\n\nYoutube: {channel_name}"
    caption_file = os.path.join(output_path, f"{index:02d} - {safe_title} - {safe_channel}.txt")
    if not os.path.exists(caption_file):
        try:
            with open(caption_file, 'w', encoding='utf-8') as f:
                f.write(caption_text)
            print(f"Caption created: {caption_file}")
        except Exception as e:
            print(f"Failed to create caption file: {e}")
            with open("download_errors.log", "a", encoding="utf-8") as log_file:
                log_file.write(f"Error creating caption for {video_url}:\n{e}\n")

    return True



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
    channel_url = input("Enter the YouTube channel URL: ").strip()

    print("Fetching video list for preview...")
    all_video_entries, channel_name = get_short_links(channel_url)

    if not all_video_entries:
        print("No videos found or failed to fetch links.")
        return

    print(f"\nTotal videos found on channel '{channel_name}': {len(all_video_entries)}")

    preview_count = min(len(all_video_entries), 10)
    print(f"\nPreviewing first {preview_count} videos:")
    for i, entry in enumerate(all_video_entries[:preview_count], start=1):
        print(f"{i}. {entry.get('title', 'Unknown Title')}")

    confirm_preview = input("\nDo you want to continue? (y/n): ").strip().lower()
    if confirm_preview != 'y':
        print("Operation cancelled.")
        return

    max_videos = input(f"Enter the number of videos to download (1-{len(all_video_entries)}), leave blank for all: ").strip()
    max_videos = int(max_videos) if max_videos.isdigit() else None

    video_entries, _ = get_short_links(channel_url, max_videos)
    if not video_entries:
        print("No videos found or failed to fetch links.")
        return

    quality = input("Enter video quality (e.g., 137+140 or best, default: best): ").strip()
    quality = quality if quality else 'best'

    file_format = input("Enter file format (MP4/WEBM, default: MP4): ").strip().lower()
    file_format = file_format if file_format in ['mp4', 'webm'] else 'mp4'

    output_directory = os.path.join(os.getcwd(), "new_week")
    os.makedirs(output_directory, exist_ok=True)

    print("\nVideo to Download:")
    for i, entry in enumerate(video_entries, start=1):
        print(f"{i}. {entry.get('title', 'Unknown Title')}")

    confirm = input("\nProceed with download? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Download canceled.")
        return

    print(f"Starting download in {output_directory}...")
    download_videos(video_entries, output_directory, channel_name, quality, file_format)


if __name__ == "__main__":
    main()
