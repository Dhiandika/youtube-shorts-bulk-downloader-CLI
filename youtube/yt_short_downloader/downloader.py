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
from .pytube_downloader import download_pytube

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
    
    # Format Strings (Prioritize 1080p > 720p, AVC > VP9)
    # Chain: 1080p AVC -> 1080p Any -> 720p AVC -> 720p Any
    # STRICT: Never accept < 720p
    FMT_CHAIN = (
        "bv*[height>=1080][vcodec^=avc]+ba[ext=m4a]/"  # 1. 1080p AVC
        "bv*[height>=1080]+ba/"                        # 2. 1080p Any
        "bv*[height>=720][vcodec^=avc]+ba[ext=m4a]/"   # 3. 720p AVC
        "bv*[height>=720]+ba"                          # 4. 720p Any
    )

    strategies = [
        # STRATEGY 1: "The Clean Android" (Default)
        {
            "name": "Android Mobile API (HD Only)",
            "args": [
                '-f', FMT_CHAIN,
                '--extractor-args', 'youtube:player_client=android'
            ]
        },

        # STRATEGY 2: "Android Creator"
        {
            "name": "Android Creator API (HD Only)",
            "args": [
                '-f', FMT_CHAIN,
                '--extractor-args', 'youtube:player_client=android_creator'
            ]
        },
        
        # STRATEGY 3: "Web Client"
        {
            "name": "Web Client (HD Only)", 
            "args": [
                '-f', FMT_CHAIN,
                '--extractor-args', 'youtube:player_client=web,-ios' 
            ]
        },

        # STRATEGY 4: "TV Client"
        {
            "name": "TV Client API (HD Only)",
            "args": [
                '-f', FMT_CHAIN,
                '--extractor-args', 'youtube:player_client=tv'
            ]
        },
        
        # STRATEGY 5: "Force IPv4"
        {
            "name": "IPv4 + Single Thread",
            "args": [
                '-f', FMT_CHAIN,
                '--force-ipv4',
                '-N', '1' 
            ]
        },

        # STRATEGY 6: "Cookie Injection"
        {
            "name": "Chrome Cookies (Authenticated)",
            "args": [
                '-f', FMT_CHAIN,
                '--cookies-from-browser', 'chrome',
                '--force-ipv4'
            ]
        },
        
        # STRATEGY 7: "The Tank"
        {
            "name": "Pre-merged Legacy (HD Only)",
            "args": [
                '-f', "b[height>=1080]/b[height>=720]", # STRICT NO 'b' fallback
                '--rm-cache-dir',
                '--force-ipv4'
            ]
        },

        # STRATEGY 8: "IOS Client"
        {
            "name": "IOS Client (HD Only)",
            "args": [
                '-f', FMT_CHAIN,
                '--extractor-args', 'youtube:player_client=ios'
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
    last_file_path = None
    
    try:
        # GLOBAL RETRY LOOP
        for strat in strategies:
            if success: break
            
            s_name = strat["name"]
            s_args = strat["args"]
            
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

                last_file_path = final_file
                
                # 3. VALIDATE RESOLUTION & QUALITY
                # STRICT RULE: 
                # - If < 720p: REJECT & DELETE.
                # - If >= 720p and < 1080p: UPSCALE.
                # - If >= 1080p: KEEP.
                
                whb = probe_resolution_bitrate(final_file)
                if whb:
                    w, h, br = whb
                    short_dim = min(w, h)
                    
                    if short_dim < 720:
                        # REJECT 360p/480p
                        _log_error(f"[REJECT] Got {w}x{h} (< 720p). Trash. Strategy {s_name} failed.", output_path)
                        try: os.remove(final_file)
                        except: pass
                        _purge_tmp_parts()
                        time.sleep(1)
                        continue # Try next strategy
                    
                    elif short_dim < 1000: # 720p - 999p range
                        # UPSCALE ALLOWED (720 -> 1080)
                        _log_error(f"[INFO] Got {w}x{h} (720p). Upscaling to 1080p...", output_path)
                        try:
                            up_path = upscale_video_if_needed(final_file, 1080)
                            if up_path and os.path.exists(up_path):
                                if up_path != final_file:
                                    try: os.remove(final_file)
                                    except: pass
                                final_file = up_path
                                last_file_path = final_file
                        except Exception as e:
                            _log_error(f"[UPSCALE FAIL] {e}. Keeping 720p original.", output_path)
                    
                    # 4. CONVERT VP9 -> H.264 IF NEEDED (Same logic as before)
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
                            last_file_path = final_file
                            
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
        cleanup_partial_downloads(output_path, f"{index:02d} - {safe_title}")

    # --- PYTUBE FALLBACK (Last Resort) ---
    if not success:
        _log_error(f"[WARN] yt-dlp strategies exhaustion. Attempting Pytube Fallback...", output_path)
        # Construct filename similar to what we wanted
        # We need a safe filename without extension for pytube wrapper
        pytube_prefix = f"{index:02d} - {safe_title} - {safe_channel}"
        
        try:
            if download_pytube(video_url, output_path, pytube_prefix):
                 # We need to set last_file_path so the final check passes
                 # Pytube saves as .mp4
                 expected_pytube_file = os.path.join(output_path, f"{pytube_prefix}.mp4")
                 
                 if os.path.exists(expected_pytube_file):
                     # === VALIDATION BLOCK (Must match main loop logic) ===
                     final_file = expected_pytube_file
                     whb = probe_resolution_bitrate(final_file)
                     
                     pytube_success = True
                     if whb:
                        w, h, br = whb
                        short_dim = min(w, h)
                        
                        # 1. Reject Low Res (< 720p)
                        if short_dim < 720:
                            _log_error(f"[REJECT-PYTUBE] Got {w}x{h} (< 720p). Trash.", output_path)
                            try: os.remove(final_file)
                            except: pass
                            pytube_success = False
                        
                        # 2. Upscale (720 -> 1080)
                        elif short_dim < 1000:
                            _log_error(f"[INFO-PYTUBE] Got {w}x{h} (720p). Upscaling...", output_path)
                            try:
                                up_path = upscale_video_if_needed(final_file, 1080)
                                if up_path and os.path.exists(up_path):
                                    if up_path != final_file:
                                        try: os.remove(final_file)
                                        except: pass
                                    final_file = up_path
                            except Exception as e:
                                _log_error(f"[UPSCALE FAIL] {e}. Keeping original.", output_path)

                        # 3. Ratio Check (9:16 Enforcement)
                        if pytube_success:
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
                             except ImportError:
                                pass # cek_resolusi might not be available
                             except Exception as e:
                                _log_error(f"[RATIO CHECK FAIL] {e}", output_path)

                     if pytube_success:
                         success = True
                         last_file_path = final_file
                         _SESSION.note_success()
                         _log_error(f"[SUCCESS] Pytube Saved & Validated: {last_file_path}", output_path)
                     else:
                         _log_error(f"[FAIL] Pytube validation failed.", output_path)

        except Exception as e:
            _log_error(f"[PYTUBE FAIL] {e}", output_path)


    # --- FINAL SAFETY CHECK ---
    # Ensure file ACTUALLY exists before reporting success
    if success:
        if not (last_file_path and os.path.exists(last_file_path) and os.path.getsize(last_file_path) > 1000):
            success = False
            _log_error(f"[FATAL] Phantom Success detected. File missing: {last_file_path}", output_path)

    if not success:
        # LOG SKIP
        try:
            with open(os.path.join(output_path, "skipped.txt"), "a", encoding="utf-8") as fs:
                fs.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] SKIP {video_id} - {video_title} - {video_url}\n")
        except: pass

    return success


def download_videos(
    video_entries: List[Dict], output_path: str, channel_name: str,
    quality: str, file_format: str,
    preassigned_indices: Optional[List[int]]=None,
    on_success: Optional[Callable[[Dict,int],None]]=None,
    max_workers: int = 3,
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
