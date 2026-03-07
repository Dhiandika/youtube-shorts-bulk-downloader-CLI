import os
import sys
import shutil
import subprocess
from pathlib import Path
from typing import Optional

# Try importing pytubefix, handle failure gracefully
try:
    from pytubefix import YouTube
    from pytubefix.exceptions import PytubeFixError
    PYTUBE_AVAILABLE = True
except ImportError:
    PYTUBE_AVAILABLE = False

# ANSI colors (simplified)
TAG_INFO = "[INFO]"
TAG_WARN = "[WARN]"
TAG_ERR = "[ERR]"
TAG_OK = "[OK]"

def is_ffmpeg_available() -> bool:
    """Return True if ffmpeg is available on PATH."""
    return shutil.which("ffmpeg") is not None

def resolution_value(stream) -> int:
    """Return the numeric resolution (e.g. '1080p' -> 1080) or 0 if unknown."""
    if not stream or not getattr(stream, "resolution", None):
        return 0
    try:
        return int(stream.resolution.replace("p", ""))
    except ValueError:
        return 0

def download_pytube(url: str, output_dir: str, filename_prefix: str = None) -> bool:
    """
    Download a video using pytubefix (Fallback Engine).
    Tries Adaptive (1080p+) + FFmpeg merge first, then Progressive.
    Returns True if successful, False otherwise.
    """
    if not PYTUBE_AVAILABLE:
        print(f"  {TAG_WARN} pytubefix not installed. Skipping Pytube fallback.")
        return False

    output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)

    try:
        print(f"  {TAG_INFO} [Pytube] Fetching info for {url}...")
        yt = YouTube(url)
        
        # Determine filename
        if filename_prefix:
            base_name = filename_prefix
        else:
            safe_title = yt.title.replace("/", "_").replace("\\", "_")
            base_name = safe_title

        final_filename = f"{base_name}.mp4"
        final_path = output_dir_path / final_filename

        # STRATEGY 1: ADAPTIVE (High Quality + FFmpeg)
        if is_ffmpeg_available():
            try:
                # Get Best Video (Adaptive)
                video_stream = (
                    yt.streams
                    .filter(adaptive=True, file_extension="mp4", only_video=True)
                    .order_by("resolution")
                    .desc()
                    .first()
                )
                
                # Get Best Audio (Adaptive)
                audio_stream = (
                    yt.streams
                    .filter(adaptive=True, only_audio=True)
                    .order_by("abr")
                    .desc()
                    .first()
                )

                if video_stream and audio_stream:
                    res = resolution_value(video_stream)
                    print(f"  {TAG_INFO} [Pytube] Found Adaptive Stream: {res}p")
                    
                    if res >= 720: # Only bother merging if it's HD
                        print(f"  {TAG_INFO} [Pytube] Downloading Video & Audio separately...")
                        
                        # Temp filenames
                        vid_tmp = output_dir_path / f"temp_v_{base_name}.mp4"
                        aud_tmp = output_dir_path / f"temp_a_{base_name}.m4a"
                        
                        # Download Video
                        video_stream.download(output_path=str(output_dir_path), filename=vid_tmp.name)
                        # Download Audio
                        audio_stream.download(output_path=str(output_dir_path), filename=aud_tmp.name)
                        
                        print(f"  {TAG_INFO} [Pytube] Merging with FFmpeg...")
                        
                        # Merge command: ffmpeg -i v -i a -c:v copy -c:a aac output
                        cmd = [
                            "ffmpeg", "-y", "-v", "error",
                            "-i", str(vid_tmp),
                            "-i", str(aud_tmp),
                            "-c:v", "copy",
                            "-c:a", "aac",
                            str(final_path)
                        ]
                        
                        subprocess.run(cmd, check=True)
                        
                        # Cleanup temp
                        if vid_tmp.exists(): vid_tmp.unlink()
                        if aud_tmp.exists(): aud_tmp.unlink()
                        
                        if final_path.exists() and final_path.stat().st_size > 1024:
                            print(f"  {TAG_OK} [Pytube] Adaptive Download Success ({res}p)!")
                            return True
            except Exception as e:
                print(f"  {TAG_WARN} [Pytube] Adaptive failed: {e}. Fallback to Progressive.")
                # Cleanup potential leftovers
                # (Assuming cleanup logic elsewhere handles this safely)
                pass

        # STRATEGY 2: PROGRESSIVE (Fallback, usually 360p or 720p)
        progressive_stream = (
            yt.streams
            .filter(progressive=True, file_extension="mp4")
            .order_by("resolution")
            .desc()
            .first()
        )
        
        if not progressive_stream:
             print(f"  {TAG_WARN} No progressive stream found.")
             return False
             
        res = resolution_value(progressive_stream)
        print(f"  {TAG_INFO} [Pytube] Downloading Progressive: {res}p")
        
        progressive_stream.download(
            output_path=str(output_dir_path),
            filename=final_filename
        )
        
        if final_path.exists() and final_path.stat().st_size > 1024:
             print(f"  {TAG_OK} [Pytube] Success!")
             return True
        else:
             print(f"  {TAG_ERR} Downloaded file is empty/missing.")
             return False

    except Exception as e:
        print(f"  {TAG_ERR} [Pytube] Error: {e}")
        return False
