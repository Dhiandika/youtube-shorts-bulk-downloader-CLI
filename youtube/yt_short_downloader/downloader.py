import os
import shutil
import subprocess
import threading
import time
import random
from typing import List, Dict, Optional, Callable, Tuple

from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor

from .config import MAX_RETRIES
from .utils import create_safe_filename, validate_filename, get_unique_filename, get_existing_index
from .ytdlp_tools import (
    detect_best_hd_selector, probe_resolution_bitrate,
    upscale_video_if_needed, enhance_video,
)

__all__ = ["download_video", "download_videos"]

# ---------- logging ----------
_LOG_LOCK = threading.Lock()
def _log_error(msg: str, output_path: Optional[str]=None) -> None:
    safe = (msg or "").rstrip() + "\n"
    with _LOG_LOCK:
        try:
            with open("download_errors.log","a",encoding="utf-8",errors="replace") as f:
                f.write(safe)
        except Exception:
            pass
        if output_path:
            try:
                os.makedirs(output_path, exist_ok=True)
                with open(os.path.join(output_path,"download_errors.log"),"a",encoding="utf-8",errors="replace") as f2:
                    f2.write(safe)
            except Exception:
                pass
    print(safe, end="")

# ---------- helpers ----------
def cleanup_partial_downloads(output_path: str, filename_pattern: str) -> None:
    try:
        # Pindai file yang cocok dengan nama video, lalu hapus .part / .ytdl
        for file in os.listdir(output_path):
            if file.startswith(filename_pattern) and (file.endswith(".part") or file.endswith(".ytdl")):
                try:
                    full_p = os.path.join(output_path,file)
                    os.remove(full_p)
                except Exception as e:
                    _log_error(f"[CLEANUP] {file} -> {e}", output_path)
    except Exception as e:
        _log_error(f"[CLEANUP] scan err: {e}", output_path)

def _yt_dlp_executables() -> List[str]:
    c = []
    for name in ("yt-dlp.exe","yt-dlp_x64.exe","yt-dlp"):
        p = shutil.which(name)
        if p: c.append(p)
    here = os.getcwd()
    for name in ("yt-dlp.exe","yt-dlp_x64.exe"):
        rp = os.path.join(here,name)
        if os.path.isfile(rp): c.append(rp)
    return list(dict.fromkeys(c)) or ["yt-dlp"]

def _run_yt_dlp(args: List[str], timeout: int, output_path: Optional[str]) -> subprocess.CompletedProcess:
    last = None
    for exe in _yt_dlp_executables():
        cmd = [exe] + args
        try:
            return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True, check=True, timeout=timeout, encoding='utf-8', errors='replace')
        except subprocess.TimeoutExpired as te:
            _log_error(f"[TIMEOUT] {' '.join(cmd)}", output_path); last = te
        except subprocess.CalledProcessError as cpe:
            raise cpe
        except Exception as e:
            _log_error(f"[RUN] {exe}: {e}", output_path); last = e
    if last: raise last
    raise RuntimeError("yt-dlp execution failed.")

def _base_args() -> List[str]:
    return [
        '--no-warnings','--quiet','--ignore-errors',
        '--no-check-certificates','--no-playlist','--ignore-config',
        '--no-call-home','--geo-bypass',
        # '--force-ipv4', # Kadang ipv6 lebih baik untuk menghindari block ipv4 range
        '--no-cache-dir',
        '--retries','3',
        '--fragment-retries','3',
        '--retry-sleep','5',
        # Hapus concurrent-fragments & -N yang agresif
        '--add-header','Accept-Language: en-US,en;q=0.9',
        '--add-header','Referer: https://www.youtube.com/',
        '--user-agent','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    ]

def _find_final_output(output_dir: str, out_template: str) -> Optional[str]:
    if "%(ext)s" not in out_template:
        return out_template if os.path.exists(out_template) else None
    prefix = os.path.basename(out_template.replace("%(ext)s",""))
    cand = [os.path.join(output_dir,f) for f in os.listdir(output_dir)
            if f.startswith(prefix) and not f.endswith(".part")]
    if not cand: return None
    cand.sort(key=lambda p: os.path.getsize(p), reverse=True)
    return cand[0]

def _rm_tree(path: str) -> None:
    try:
        if os.path.isdir(path): shutil.rmtree(path, ignore_errors=True)
    except Exception:
        pass

# ---------- adaptive session state ----------
class _SessionState:
    def __init__(self):
        self.lock = threading.Lock()
        self.consec_403 = 0
        self.jitter_base = (0.15, 0.5)  # detik
        self.is_strict = False  # New: adaptive strict mode

    def note_403(self):
        with self.lock:
            self.consec_403 += 1
            if self.consec_403 >= 3:
                self.is_strict = True  # Activate strict mode quickly

    def note_success(self):
        with self.lock:
            self.consec_403 = 0

    def maybe_pause(self, output_path: Optional[str]):
        with self.lock:
            if self.consec_403 >= 5:
                _log_error("[CB] too many 403/fragment recently — pausing 20s", output_path)
                self.consec_403 = 0
                time.sleep(20)

_SESSION = _SessionState()

# ---------- main ----------
def download_video(
    video_id: str, video_title: str, output_path: str,
    channel_name: str, quality: str, file_format: str, index: int,
    force_min_height: int = 1080,  # FORCE 1080P STRICT
    enhance_mode: str = "quality",
    quality_floor: int = 1080      # ANTI 360P, only accept 1080p+
) -> bool:

    # jitter kecil per-job untuk kurangi spike request
    time.sleep(random.uniform(*_SESSION.jitter_base))

    video_url = f"https://www.youtube.com/watch?v={video_id}"

    safe_title   = create_safe_filename(video_title, 80)
    safe_channel = create_safe_filename(channel_name, 50)

    filename_base = f"{index:02d} - {safe_title} - {safe_channel}.%(ext)s"
    if not validate_filename(f"{index:02d} - {safe_title} - {safe_channel}"):
        filename_base = f"{index:02d} - video_{video_id}.%(ext)s"

    out_name  = get_unique_filename(output_path, filename_base)
    file_path = os.path.join(output_path, out_name)

    cleanup_partial_downloads(output_path, f"{index:02d} - {safe_title}")

    # caption
    try:
        capfile = get_unique_filename(output_path, f"{index:02d} - {safe_title} - {safe_channel}.txt")
        with open(os.path.join(output_path, capfile), "w", encoding="utf-8", errors="replace") as f:
            # ADDED: Link to video
            f.write(f"{video_title} #shorts\n\nYouTube: {channel_name}\nLink: {video_url}")
    except Exception as e:
        _log_error(f"[CAPTION] {e}", output_path)

    timeout  = 1200 # Increased timeout
    
    # tmp dir unik per video (hindari tabrakan .part)
    tmp_root = os.path.join(output_path, ".tmp")
    os.makedirs(tmp_root, exist_ok=True)
    tmp_dir  = os.path.join(tmp_root, f"{index:06d}")
    os.makedirs(tmp_dir, exist_ok=True)

    # ---------------------------------------------------------
    # MAJOR STRATEGY OVERHAUL (Anti-403 & 1080p Enforcement)
    # ---------------------------------------------------------
    
    # Format Strings
    FMT_1080_AVC   = "bv*[height>=1080][vcodec^=avc]+ba[ext=m4a]"  # Best (Native)
    FMT_1080_ANY   = "bv*[height>=1080]+ba"                        # Accept VP9 (Will convert)
    FMT_1080_MERGED= "b[height>=1080]"                             # Pre-merged
    FMT_720_AVC    = "bv*[height>=720][vcodec^=avc]+ba"            # Fallback

    strategies = [
        # STRATEGY 1: "The Clean Android"
        {
            "name": "Android Mobile API",
            "args": [
                '-f', f"{FMT_1080_AVC}/{FMT_1080_ANY}",
                '--extractor-args', 'youtube:player_client=android'
            ]
        },
        
        # STRATEGY 2: "Browser Bypass" (No iOS)
        {
            "name": "Web Client (Limit iOS)", 
            "args": [
                '-f', f"{FMT_1080_AVC}/{FMT_1080_ANY}",
                '--extractor-args', 'youtube:player_client=web,-ios' 
            ]
        },
        
        # STRATEGY 3: "Force IPv4 + Single Thread"
        {
            "name": "IPv4 + Single Thread",
            "args": [
                '-f', f"{FMT_1080_AVC}/{FMT_1080_ANY}",
                '--force-ipv4',
                '-N', '1' 
            ]
        },

        # STRATEGY 4: "Cookie Injection" (Chrome) 
        {
            "name": "Chrome Cookies (Authenticated)",
            "args": [
                '-f', f"{FMT_1080_AVC}/{FMT_1080_ANY}",
                '--cookies-from-browser', 'chrome',
                '--force-ipv4'
            ]
        },
        
        # STRATEGY 5: "The Tank" (Pre-merged + No Cache)
        {
            "name": "Pre-merged Legacy + No Cache",
            "args": [
                '-f', f"{FMT_1080_MERGED}/{FMT_1080_ANY}/{FMT_720_AVC}",
                '--rm-cache-dir',
                '--force-ipv4'
            ]
        }
    ]

    # Helper cleaning
    def _purge_tmp_parts():
        try:
            for fp in os.listdir(tmp_dir):
                if fp.endswith(".part") or fp.endswith(".ytdl"):
                    try: os.remove(os.path.join(tmp_dir, fp))
                    except: pass
        except: pass

    success = False
    
    try:
        # GLOBAL RETRY LOOP
        for strat in strategies:
            if success: break
            
            s_name = strat["name"]
            s_args = strat["args"]
            
            # _log_error(f"[ATTEMPT] Strategy: {s_name}...", output_path)
            
            args = (
                _base_args()
                + ['--paths', f'temp:{tmp_dir}']
                + s_args
                + ['--output', file_path, video_url]
            )
            
            try:
                # 1. EXECUTE
                _run_yt_dlp(args, timeout=timeout, output_path=output_path)
                
                # 2. VERIFY OUTPUT
                final_file = _find_final_output(output_path, file_path)
                
                if not final_file or os.path.getsize(final_file) < 1000:
                    _purge_tmp_parts()
                    continue # Silent fail, next strategy
                
                # 3. VALIDATE RESOLUTION & QUALITY
                whb = probe_resolution_bitrate(final_file)
                if whb:
                    w, h, br = whb
                    short_dim = min(w, h)
                    
                    # REJECT 360p/480p (Anything < 720p)
                    is_trash = short_dim < 400
                    
                    if is_trash:
                        _log_error(f"[REJECT] {s_name} -> {w}x{h} (TRASH). Deleting...", output_path)
                        try: os.remove(final_file)
                        except: pass
                        _purge_tmp_parts()
                        time.sleep(2)
                        continue
                    
                    # 4. CONVERT VP9 -> H.264 IF NEEDED
                    try:
                        import sys
                        current_dir = os.path.dirname(os.path.abspath(__file__)) 
                        parent_dir = os.path.dirname(current_dir)
                        if parent_dir not in sys.path: sys.path.append(parent_dir)
                        import cek_resolusi
                        
                        new_path, converted = cek_resolusi.check_and_convert_video(
                            final_file, target_mode='reels', force=False
                        )
                        
                        if converted and os.path.exists(new_path):
                            final_file = new_path
                            
                    except Exception as e:
                        pass

                success = True
                _SESSION.note_success()
                
            except subprocess.CalledProcessError as e:
                err_msg = (e.stderr or "") + (e.stdout or "")
                if "HTTP Error 403" in err_msg:
                    _SESSION.note_403()
                
                _purge_tmp_parts()
                time.sleep(random.uniform(2, 4))
                continue
                
            except Exception as e:
                _purge_tmp_parts()
                continue
                
    finally:
        _rm_tree(tmp_dir)
        # Final FORCE cleanup untuk file .part yang bandel di folder utama
        cleanup_partial_downloads(output_path, f"{index:02d} - {safe_title}")

    return success


def download_videos(
    video_entries: List[Dict], output_path: str, channel_name: str,
    quality: str, file_format: str,
    preassigned_indices: Optional[List[int]]=None,
    on_success: Optional[Callable[[Dict,int],None]]=None,
    max_workers: int = 1,
) -> None:
    os.makedirs(output_path, exist_ok=True)

    if preassigned_indices is not None:
        if len(preassigned_indices) != len(video_entries):
            raise ValueError("preassigned_indices length must match video_entries length")
        indices = preassigned_indices
    else:
        start_index = get_existing_index(output_path) + 1
        indices = [start_index + i for i in range(len(video_entries))]

    total = len(video_entries)
    pbar = tqdm(total=total, desc="Downloading", unit="video", ascii=True)

    def _task(entry: Dict, idx: int) -> bool:
        # jitter awal antar-task
        time.sleep(random.uniform(0.15, 0.5))
        ok = download_video(
            entry['id'], entry.get('title','Unknown Title'),
            output_path, channel_name, quality, file_format, idx,
            force_min_height=1080, enhance_mode="quality", quality_floor=1080
        )
        if ok and on_success:
            try: on_success(entry, idx)
            except Exception as e: _log_error(f"[CALLBACK] {e}", output_path)
        return ok

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [ex.submit(_task, e, idx) for e, idx in zip(video_entries, indices)]
        for fut in futures:
            try:
                fut.result()
            except Exception as e:
                _log_error(f"[THREAD] {e}", output_path)
            finally:
                pbar.update(1)

    pbar.close()
