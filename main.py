import os
import yt_dlp
import subprocess
import threading
from tqdm import tqdm
import time

MAX_RETRIES = 3  # Jumlah maksimum percobaan ulang jika gagal

def get_short_links(channel_url, max_videos=None):
    ydl_opts = {
        'quiet': True,
        'extract_flat': True,
        'playlistend': max_videos if max_videos else None,
    }

    if '/@' in channel_url:
        channel_username = channel_url.split('/@')[1].split('/')[0]
        channel_url = f'https://www.youtube.com/@{channel_username}/shorts'
    else:
        channel_url = channel_url.split('/about')[0]  
        channel_url = channel_url.split('/community')[0]  
        channel_url = channel_url.split('/playlist')[0]  
        channel_url = channel_url.split('/playlists')[0]  
        channel_url = channel_url.split('/streams')[0]  
        channel_url = channel_url.split('/featured')[0]  
        channel_url = channel_url.split('/videos')[0]  
        channel_url += '/shorts'

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        result = ydl.extract_info(channel_url, download=False)
        if 'entries' in result:
            video_entries = result['entries'][:max_videos] if max_videos else result['entries']
            channel_name = result.get('uploader', channel_username)
            return video_entries, channel_name
        else:
            print("No videos found on the channel.")
            return [], ""

def download_video(video_id, video_title, output_path, channel_name, quality, file_format, index):
    video_url = f"https://www.youtube.com/shorts/{video_id}"
    filename = f"{index+1:02d} - {video_title}.{file_format}"
    file_path = os.path.join(output_path, filename)

    # Cek jika file sudah ada
    if os.path.exists(file_path):
        print(f"Skipping (Already exists): {file_path}")
        return True

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            subprocess.run(
                ['yt-dlp', '-f', quality, '--output', file_path, video_url],
                check=True
            )
            print(f"Downloaded successfully: {video_url}")

            # Simpan caption
            caption_text = f"{video_title} #shorts #vtuber #hololive\n\nYoutube: {channel_name}"
            caption_file = os.path.join(output_path, f"{index+1:02d} - {video_title}.txt")
            with open(caption_file, 'w', encoding='utf-8') as f:
                f.write(caption_text)

            return True
        except subprocess.CalledProcessError:
            print(f"Retrying {video_url} ({attempt}/{MAX_RETRIES})...")
            time.sleep(2 ** attempt)  # Retry dengan delay eksponensial

    print(f"Failed to download: {video_url}")
    return False

def remove_duplicates(output_path):
    files = os.listdir(output_path)
    seen = set()
    for file in files:
        if file.endswith((".mp4", ".webm")):
            name = os.path.splitext(file)[0]
            if name in seen:
                os.remove(os.path.join(output_path, file))
                print(f"Removed duplicate: {file}")
            else:
                seen.add(name)

def download_videos(video_entries, output_path, channel_name, quality, file_format):
    os.makedirs(output_path, exist_ok=True)

    total_videos = len(video_entries)
    failed_downloads = []
    progress_bar = tqdm(total=total_videos, desc="Downloading", unit="video")

    def worker(index, video):
        video_id = video['id']
        video_title = video.get('title', 'Unknown Title')
        success = download_video(video_id, video_title, output_path, channel_name, quality, file_format, index)
        if not success:
            failed_downloads.append(video_id)
        progress_bar.update(1)

    threads = []
    for index, entry in enumerate(video_entries):
        thread = threading.Thread(target=worker, args=(index, entry))
        thread.start()
        threads.append(thread)

    for thread in threads:
        thread.join()

    progress_bar.close()
    remove_duplicates(output_path)

    print("\nDownload Summary:")
    print(f"Total videos downloaded: {total_videos - len(failed_downloads)}/{total_videos}")
    if failed_downloads:
        print("Failed downloads:")
        for vid in failed_downloads:
            print(f"- https://www.youtube.com/shorts/{vid}")

def main():
    channel_url = input("Enter the YouTube channel URL: ").strip()
    max_videos = input("Enter the number of videos to download (leave blank for all): ").strip()
    max_videos = int(max_videos) if max_videos.isdigit() else None

    quality = input("Enter video quality (default: best): ").strip()
    quality = quality if quality else 'best'

    file_format = input("Enter file format (MP4/WEBM, default: MP4): ").strip().lower()
    file_format = file_format if file_format in ['mp4', 'webm'] else 'mp4'

    video_entries, channel_name = get_short_links(channel_url, max_videos)
    if not video_entries:
        print("No videos found or failed to fetch links.")
        return

    output_directory = os.path.join(os.getcwd(), "downloads")
    os.makedirs(output_directory, exist_ok=True)

    print("\nVideo Preview:")
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
