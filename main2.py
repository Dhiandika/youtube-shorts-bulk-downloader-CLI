import os
from yt_short_downloader.config import DEFAULT_OUTPUT_DIR, DEFAULT_FILE_FORMAT
from yt_short_downloader.ytdlp_tools import check_yt_dlp_installation
from yt_short_downloader.fetch import get_short_links
from yt_short_downloader.orchestrator import download_videos_with_db
from yt_short_downloader.db import TinyStore


def _ask_quality() -> str:
    print(" Quality options: ")
    print("1. best - Best available quality (recommended)")
    print("2. worst - Smallest file size")
    print("3. 137+140 - 1080p video + audio (may not be available for all videos)")
    print("4. 136+140 - 720p video + audio (may not be available for all videos)")
    print("5. 135+140 - 480p video + audio (may not be available for all videos)")
    choice = input("Enter quality choice (1-5, default: 1): ").strip()
    return {
        '1': 'best',
        '2': 'worst',
        '3': '137+140',
        '4': '136+140',
        '5': '135+140',
    }.get(choice, 'best')


def main():
    try:
        print("YouTube Shorts Bulk Downloader")
        print("=" * 40)

        print("Checking yt-dlp installation...")
        if not check_yt_dlp_installation():
            print("Please install yt-dlp and try again.")
            return

        print(" " + "=" * 40)
        channel_url = input("Enter the YouTube channel URL: ").strip()
        if not channel_url:
            print("No URL provided. Exiting.")
            return

        # Siapkan database
        store = TinyStore()

        print("Fetching video list for preview...")
        all_video_entries, channel_name = get_short_links(channel_url)
        if not all_video_entries:
            print("No videos found or failed to fetch links.")
            return

        # Normalisasi key channel (gunakan URL dasar sebagai key)
        channel_key = channel_url.split('/about')[0]
        store.upsert_channel(channel_key=channel_key, name=channel_name, url=channel_key)

        # Tampilkan preview
        print(f" Total videos found on channel '{channel_name}': {len(all_video_entries)}")
        preview_count = min(len(all_video_entries), 10)
        print(f"  Previewing first {preview_count} videos: ")
        for i, entry in enumerate(all_video_entries[:preview_count], start=1):
            title = entry.get('title', 'Unknown Title')
            if len(title) > 80:
                title = title[:77] + "..."
            print(f"{i}. {title}")

        confirm_preview = input(" Do you want to continue ? (y/n): ").strip().lower()
        if confirm_preview != 'y':
            print("Operation cancelled.")
            return

        # Batasi jumlah video
        max_videos_input = input(
            f"Enter the number of videos to download (1-{len(all_video_entries)}), leave blank for all: "
        ).strip()
        try:
            max_videos = int(
                max_videos_input) if max_videos_input.isdigit() else None
            if max_videos is not None and (max_videos < 1 or max_videos > len(all_video_entries)):
                print(
                    f"Invalid number. Using all {len(all_video_entries)} videos.")
                max_videos = None
        except ValueError:
            print("Invalid input. Using all videos.")
            max_videos = None

        video_entries, _ = get_short_links(channel_url, max_videos)
        if not video_entries:
            print("No videos found or failed to fetch links.")
            return

        # Simpan metadata minimal ke DB dan filter yang belum diunduh
        kept_entries = []
        for e in video_entries:
            vid = e.get('id')
            title = e.get('title', 'Unknown Title')
            # bisa None, tergantung extractor
            upload_date = e.get('upload_date')
            store.upsert_video(channel_key=channel_key, video_id=vid, title=title, upload_date=upload_date)
            if not store.is_downloaded(channel_key, vid):
                kept_entries.append(e)

        skipped = len(video_entries) - len(kept_entries)
        if skipped:
            print(f"Skipping {skipped} videos already downloaded.")

        if not kept_entries:
            print("All videos for this channel are already downloaded.")
            return

        quality = _ask_quality()
        print(f"Selected quality: {quality}")

        file_format = input(
            "Enter file format (MP4/WEBM, default: MP4): ").strip().lower()
        file_format = file_format if file_format in [
            'mp4', 'webm'] else DEFAULT_FILE_FORMAT

        output_directory = os.path.join(os.getcwd(), DEFAULT_OUTPUT_DIR)
        os.makedirs(output_directory, exist_ok=True)

        print(f" Videos to Download({len(kept_entries)} total): ")
        for i, entry in enumerate(kept_entries, start=1):
            title = entry.get('title', 'Unknown Title')
            if len(title) > 60:
                title = title[:57] + "..."
            print(f"{i}. {title}")

        confirm = input("Proceed with download? (y/n): ").strip().lower()
        if confirm != 'y':
            print("Download canceled.")
            return

        print(f"Starting download in {output_directory}...")
        print("Note: Caption files will be created for all videos, even if download fails.")
        # Jalankan orkestrasi yang akan menandai DB jika sukses
        download_videos_with_db(
            video_entries=kept_entries,
            output_path=output_directory,
            channel_name=channel_name,
            quality=quality,
            file_format=file_format,
            channel_key=channel_key,
            store=store,
        )

        print(" Download process completed!")
        print(
            f"Check the '{DEFAULT_OUTPUT_DIR}' folder for downloaded videos and caption files.")
        print("Any errors were logged to 'download_errors.log'")

    except KeyboardInterrupt:
        print(" Operation cancelled by user.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        with open("download_errors.log", "a", encoding="utf-8") as log_file:
            log_file.write(f"Unexpected error in main: {e}")
        print("Check 'download_errors.log' for details.")


if __name__ == "__main__":
    main()