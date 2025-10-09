import os
import subprocess
import threading
import time
from tqdm import tqdm
from typing import List, Dict, Optional, Callable  # ⬅️ tambahkan Callable

from .config import MAX_RETRIES
from .utils import (
    create_safe_filename, validate_filename, get_unique_filename,
    get_existing_index,
)
from .ytdlp_tools import get_best_available_format

__all__ = [
    "cleanup_partial_downloads",
    "download_video",
    "download_videos",
]


def cleanup_partial_downloads(output_path: str, filename_pattern: str) -> None:
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


def _build_base_cmd(file_format: str) -> list[str]:
    return [
        'yt-dlp',
        '--merge-output-format', file_format,
        '--no-warnings', '--quiet', '--no-check-certificates', '--ignore-errors',
        '--no-playlist', '--extractor-args', 'youtube:player_client=android',
        '--user-agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    ]


def download_video(video_id: str, video_title: str, output_path: str, channel_name: str,
                   quality: str, file_format: str, index: int) -> bool:
    video_url = f"https://www.youtube.com/shorts/{video_id}"
    safe_title = create_safe_filename(video_title, max_length=80)
    safe_channel = create_safe_filename(channel_name, max_length=50)
    filename = f"{index:02d} - {safe_title} - {safe_channel}.{file_format}"

    if not validate_filename(filename):
        print(f"Warning: Generated filename may be problematic, using fallback: {filename}")
        filename = f"{index:02d} - video_{video_id}.{file_format}"

    filename = get_unique_filename(output_path, filename)
    file_path = os.path.join(output_path, filename)

    cleanup_partial_downloads(output_path, f"{index:02d} - {safe_title}")

    # Caption file
    caption_text = f"{video_title} #shorts #vtuber #hololive\n\nYoutube: {channel_name}"
    caption_filename = f"{index:02d} - {safe_title} - {safe_channel}.txt"
    caption_filename = get_unique_filename(output_path, caption_filename)
    caption_file = os.path.join(output_path, caption_filename)

    try:
        with open(caption_file, 'w', encoding='utf-8', errors='replace') as f:
            f.write(caption_text)
        print(f"Caption created: {caption_file}")
    except Exception as e:
        print(f"Failed to create caption file: {e}")
        with open("download_errors.log", "a", encoding="utf-8") as log_file:
            log_file.write(f"Error creating caption for {video_url}:\n{e}\n")
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
            cmd = _build_base_cmd(file_format) + ['--output', file_path]
            if quality == 'best':
                cmd.extend(['-f', 'best[ext=mp4]/best'])
            elif quality == 'worst':
                cmd.extend(['-f', 'worst[ext=mp4]/worst'])
            else:
                cmd.extend(['-f', f'{quality}+bestaudio/best[ext=mp4]/best'])
            cmd.append(video_url)

            result = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                check=True, timeout=300, encoding='utf-8', errors='replace'
            )

            if not os.path.exists(file_path) or os.path.getsize(file_path) < 1000:
                raise Exception("Downloaded file is too small or missing, might be corrupted.")

            print(f"Downloaded successfully: {video_url}")
            return True

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

            if "Requested format is not available" in e.stderr or "HTTP Error 403" in e.stderr:
                print(f"Format not available for {video_url}, trying with best available format...")
                try:
                    best_format = get_best_available_format(video_url)
                    if best_format:
                        cmd_with_best = _build_base_cmd(file_format) + ['--output', file_path, '-f', best_format, video_url]
                        result = subprocess.run(
                            cmd_with_best, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            check=True, timeout=300, encoding='utf-8', errors='replace'
                        )
                        if os.path.exists(file_path) and os.path.getsize(file_path) >= 1000:
                            print(f"Downloaded successfully with best available format: {video_url}")
                            return True
                    else:
                        print(f"Could not determine best format for {video_url}")
                except Exception as format_error:
                    print(f"Best format download also failed: {format_error}")

            if attempt == MAX_RETRIES:
                try:
                    simple_filename = f"{index:02d} - video_{video_id}.{file_format}"
                    simple_file_path = os.path.join(output_path, simple_filename)
                    simple_cmd = _build_base_cmd(file_format) + ['--output', simple_file_path, '-f', 'best[ext=mp4]/best']
                    print(f"Trying with simple filename: {simple_filename}")
                    result = subprocess.run(
                        simple_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                        check=True, timeout=300, encoding='utf-8', errors='replace'
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
            error_msg = (f"Attempt {attempt} failed for {video_url}\nGeneral Error: {e}\n")
            print(error_msg)
            with open("download_errors.log", "a", encoding="utf-8") as log_file:
                log_file.write(error_msg + "\n")
            time.sleep(2 ** attempt)
    return False


def download_videos(
    video_entries: List[Dict],
    output_path: str,
    channel_name: str,
    quality: str,
    file_format: str,
    preassigned_indices: Optional[List[int]] = None,
    on_success: Optional[Callable[[Dict, int], None]] = None,   # ⬅️ NEW
) -> None:
    os.makedirs(output_path, exist_ok=True)

    if preassigned_indices is not None:
        if len(preassigned_indices) != len(video_entries):
            raise ValueError("preassigned_indices length must match video_entries length")
        indices = preassigned_indices
    else:
        start_index = get_existing_index(output_path) + 1
        indices = [start_index + i for i in range(len(video_entries))]

    total_videos = len(video_entries)
    progress_bar = tqdm(total=total_videos, desc="Downloading", unit="video", ascii=True)

    threads: list[threading.Thread] = []

    def _worker(entry: Dict, index: int):
        ok = download_video(
            entry['id'],
            entry.get('title', 'Unknown Title'),
            output_path,
            channel_name,
            quality,
            file_format,
            index,
        )
        if ok and on_success:
            try:
                on_success(entry, index)
            except Exception as cb_err:
                # jangan sampai callback bikin thread crash
                with open("download_errors.log", "a", encoding="utf-8") as log:
                    log.write(f"on_success callback error for {entry.get('id')}: {cb_err}\n")

    for entry, index in zip(video_entries, indices):
        t = threading.Thread(target=_worker, args=(entry, index))
        t.start()
        threads.append(t)

    for t in threads:
        t.join()
        progress_bar.update(1)

    progress_bar.close()

