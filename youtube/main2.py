# BARIS PALING ATAS!
import console_guard  # noqa: F401

import os
from yt_short_downloader.config import DEFAULT_OUTPUT_DIR, DEFAULT_FILE_FORMAT
from yt_short_downloader.ytdlp_tools import check_yt_dlp_installation
from yt_short_downloader.fetch import get_short_links
from yt_short_downloader.orchestrator import download_videos_with_db

# Store: pakai SQLite yang stabil. Fallback TinyDB jika modul tidak ada.
try:
    from yt_short_downloader.db_sqlite import SqliteStore as Store
except Exception:
    from yt_short_downloader.db import TinyStore as Store


def _ask_file_format(default_ff: str) -> str:
    print("\n File format options:")
    print(" - auto (recommended)")
    print(" - mkv")
    print(" - mp4  (most compatible; may remux)")
    print(" - webm")
    raw = input(f"Enter file format (default: {default_ff}): ").strip().lower()
    allowed = {'auto','mkv','mp4','webm'}
    return raw if raw in allowed else (default_ff if default_ff in allowed else 'auto')


def main():
    try:
        print("YouTube Shorts Bulk Downloader — HD-first strategy (stable workers)")
        print("="*64)
        if not check_yt_dlp_installation():
            print("Please install yt-dlp and try again."); return

        channel_url = input("Enter the YouTube channel URL (Shorts-enabled): ").strip()
        if not channel_url: print("No URL. Exiting."); return

        store = Store()  # ← sekarang SQLiteStore (atau TinyStore jika fallback)

        print("Fetching Shorts list for preview...")
        all_entries, channel_name = get_short_links(channel_url)
        if not all_entries: print("No videos found."); return

        channel_key = channel_url.split('/about')[0]
        store.upsert_channel(channel_key=channel_key, name=channel_name, url=channel_key)

        print(f" Total shorts on '{channel_name}': {len(all_entries)}")
        for i, e in enumerate(all_entries[:12], 1):
            t = e.get('title','Unknown Title')
            print(f"{i}. {t[:80] + ('...' if len(t)>80 else '')}")

        if input(" Continue? (y/n): ").strip().lower()!='y':
            print("Operation cancelled."); return

        max_in = input(f"Enter number to download (1-{len(all_entries)}), blank for all: ").strip()
        max_videos = int(max_in) if max_in.isdigit() else None
        if max_videos is not None and (max_videos<1 or max_videos>len(all_entries)):
            print("Invalid number. Use all."); max_videos=None

        entries, _ = get_short_links(channel_url, max_videos)
        if not entries: print("No videos found."); return

        kept = []
        for e in entries:
            vid = e.get('id'); title = e.get('title','Unknown Title'); up = e.get('upload_date')
            store.upsert_video(channel_key=channel_key, video_id=vid, title=title, upload_date=up)
            if not store.is_downloaded(channel_key, vid): kept.append(e)

        skipped = len(entries)-len(kept)
        if skipped: print(f"Skipping {skipped} already-downloaded items.")
        if not kept: print("All downloaded."); return

        quality = 'best'
        print(f"Selected quality: {quality} (locked)")
        file_format = _ask_file_format(DEFAULT_FILE_FORMAT)
        print(f"Selected file format: {file_format}")

        output_directory = os.path.join(os.getcwd(), DEFAULT_OUTPUT_DIR)
        os.makedirs(output_directory, exist_ok=True)

        print(f"\n Shorts to Download ({len(kept)} total): ")
        for i, e in enumerate(kept, 1):
            t = e.get('title','Unknown Title'); print(f"{i}. {t[:60] + ('...' if len(t)>60 else '')}")

        if input("Proceed with download? (y/n): ").strip().lower()!='y':
            print("Download canceled."); return

        print(f"Starting download in {output_directory}...")
        print("- Workers limited (max 3) with isolated temp dirs to avoid .part clashes.")
        print("- We'll force ≥720p if available (multi-client).")
        print("- If still low-res, we enhance/upscale to 1080×1920.")

        # Orkestrator tetap (tidak diubah)
        from yt_short_downloader.orchestrator import download_videos_with_db
        download_videos_with_db(
            video_entries=kept, output_path=output_directory,
            channel_name=channel_name, quality=quality, file_format=file_format,
            channel_key=channel_key, store=store,
        )

        print("\nDone. Check the output folder.")
        print("If HD existed, files should be ≥720×1280. If not, look for *.enhanced_1080x1920.mp4.")

    except KeyboardInterrupt:
        print("Operation cancelled.")
    except Exception as e:
        print("Unexpected error:", e)
        try:
            with open("download_errors.log","a",encoding="utf-8") as f:
                f.write(f"Unexpected error in main: {e}\n")
        except Exception:
            pass
        print("Check 'download_errors.log' for details.")

if __name__ == "__main__":
    main()
