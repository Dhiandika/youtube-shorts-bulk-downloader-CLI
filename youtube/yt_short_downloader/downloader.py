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
        for file in os.listdir(output_path):
            if file.startswith(filename_pattern) and file.endswith(".part"):
                try:
                    os.remove(os.path.join(output_path,file))
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
        '--no-call-home','--geo-bypass','--force-ipv4','--no-cache-dir',
        '--fragment-retries','50','--retries','10','--retry-sleep','2',
        '--concurrent-fragments','16','--http-chunk-size','10M',
        '-N','12','--force-overwrites',
        '--add-header','Accept-Language: en-US,en;q=0.9',
        '--add-header','Referer: https://www.youtube.com/',
        '--user-agent','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0 Safari/537.36',
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
    def note_403(self):
        with self.lock:
            self.consec_403 += 1
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
    force_min_height: int = 720,  # target minimal
    enhance_mode: str = "quality",
    quality_floor: int = 720      # kalau hasil < floor, coba strategi lain dulu (anti turun 360)
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
            f.write(f"{video_title} #shorts\n\nYouTube: {channel_name}")
    except Exception as e:
        _log_error(f"[CAPTION] {e}", output_path)

    timeout  = 900
    base     = _base_args()

    # tmp dir unik per video (hindari tabrakan .part)
    tmp_root = os.path.join(output_path, ".tmp")
    os.makedirs(tmp_root, exist_ok=True)
    tmp_dir  = os.path.join(tmp_root, f"{index:06d}")
    os.makedirs(tmp_dir, exist_ok=True)

    # 1) deteksi selector HD spesifik (≥ force_min_height)
    hd_sel = detect_best_hd_selector(video_url, min_height=force_min_height)

    # 2) fallback “bestvideo+bestaudio / best”
    base_fallbacks = [
        ['-f', f"bv*[height>=?{force_min_height}]+ba/best"],
        ['-f', "bv*+ba/best"],
        # 'best' kita taruh PALING AKHIR sekali (quality floor akan menghalangi jatuh ke 360 terlalu dini)
    ]

    # client rotasi (diperluas)
    _CLIENTS = [
        "youtube:player_client=android",
        "youtube:player_client=web",
        "youtube:player_client=ios",
        "youtube:player_client=tv",
        "youtube:player_client=web_safari",
        "youtube:player_client=web_embedded",
        "youtube:player_client=android;formats=incomplete",
        "youtube:player_client=web;formats=incomplete",
    ]

    strategies: List[List[str]] = []
    if hd_sel:
        strategies.append(['-f', hd_sel])  # persis logika asli
        for client in _CLIENTS:
            strategies.append(['-f', hd_sel, '--extractor-args', client])
    # fallback dengan berbagai client
    strategies.extend(base_fallbacks)
    for client in _CLIENTS:
        for bf in base_fallbacks:
            strategies.append(bf + ['--extractor-args', client])
    # 'best' benar-benar terakhir
    strategies.append(['-f', "best"])

    chunk_sizes = ["10M","5M","1M"]
    connections = ["12","4","1"]

    def _purge_tmp_parts():
        try:
            for fp in os.listdir(tmp_dir):
                if fp.endswith(".part") or fp.endswith(".ytdl"):
                    try: os.remove(os.path.join(tmp_dir, fp))
                    except Exception: pass
        except Exception:
            pass

    def _attempt_with(args_extra: List[str]) -> Tuple[bool, Optional[str]]:
        for chunk in chunk_sizes:
            for conn in connections:
                _SESSION.maybe_pause(output_path)
                args = (
                    base
                    + ['--paths', f'temp:{tmp_dir}']
                    + ['--http-chunk-size', chunk, '-N', conn]
                    + args_extra
                    + ['--output', file_path, video_url]
                )
                _log_error(f"[TRY] {' '.join(args)}", output_path)
                try:
                    _run_yt_dlp(args, timeout=timeout, output_path=output_path)
                except subprocess.CalledProcessError as e:
                    err = (e.stderr or "") + (e.stdout or "")
                    if ("HTTP Error 403" in err) or ("fragment" in err.lower()) or ("Requested format is not available" in err):
                        _SESSION.note_403()
                        _log_error(f"[RETRY] chunk={chunk} N={conn} reason=403/fragment/format", output_path)
                        _purge_tmp_parts()
                        continue
                    raise

                # sukses download
                final_file = _find_final_output(output_path, file_path)
                if not final_file or os.path.getsize(final_file) < 1000:
                    _purge_tmp_parts()
                    raise Exception("Downloaded file missing/too small.")

                _SESSION.note_success()

                # quality gate — cegah “jatuh ke 360” bila masih ada strategi lain
                whb = probe_resolution_bitrate(final_file)
                if whb:
                    w,h,br = whb
                    if (w < quality_floor) or (h < (quality_floor * 16 // 9)):  # approx portrait/landscape guard
                        _log_error(f"[QUALITY-FLOOR] got {w}x{h} (<{quality_floor}w). Will try other strategies first.", output_path)
                        # hapus file hasil ini agar strategi lain bisa jalan
                        try: os.remove(final_file)
                        except Exception: pass
                        _purge_tmp_parts()
                        # lanjut ke kombinasi berikutnya
                        continue

                    # Enhance bila mutu rendah (bitrate kecil) atau resolusi masih di bawah target akhir
                    low_res = (w < force_min_height)
                    low_br  = (br and br < 1500)  # kbps
                    if low_res or low_br:
                        enh = enhance_video(final_file, 1080, 1920, mode=enhance_mode, crf=18, preset="slow")
                        if enh:
                            _log_error(f"[ENHANCE] {final_file} -> {enh}", output_path)
                return True, final_file
        return False, None

    try:
        for attempt in range(1, MAX_RETRIES+1):
            for idx, strat in enumerate(strategies, start=1):
                try:
                    ok, fpath = _attempt_with(strat)
                    if ok:
                        print(f"Downloaded successfully: {video_url}")
                        return True
                except subprocess.CalledProcessError as e:
                    err = (e.stderr or "") + (e.stdout or "")
                    _log_error(f"[ATTEMPT-{attempt}] var#{idx} CPE\n{err}", output_path)
                    continue
                except subprocess.TimeoutExpired:
                    _log_error(f"[ATTEMPT-{attempt}] var#{idx} TIMEOUT", output_path)
                    continue
                except Exception as e:
                    _log_error(f"[ATTEMPT-{attempt}] var#{idx} ERR {e}", output_path)
                    continue
            # backoff antar attempt (exponential + jitter)
            time.sleep((2**attempt) + random.uniform(0.25, 0.75))
    finally:
        _rm_tree(tmp_dir)

    # LAST resort — izinkan best walau di bawah floor, lalu enhance
    try:
        simple_name = get_unique_filename(output_path, f"{index:02d} - video_{video_id}.%(ext)s")
        simple_path = os.path.join(output_path, simple_name)
        args_final  = _base_args() + ['--paths', f'temp:{tmp_dir}', '-f','best','--output', simple_path, video_url]
        _log_error(f"[FINAL] {' '.join(args_final)}", output_path)
        _run_yt_dlp(args_final, timeout=timeout, output_path=output_path)
        final2 = _find_final_output(output_path, simple_path)
        if final2:
            whb = probe_resolution_bitrate(final2)
            if whb:
                w,h,br = whb
                if (w < force_min_height) or (h < force_min_height):
                    enh = enhance_video(final2, 1080, 1920, mode=enhance_mode, crf=18, preset="slow")
                    if enh:
                        _log_error(f"[FINAL-ENHANCE] {final2} -> {enh}", output_path)
        return True
    except Exception as e:
        _log_error(f"[FINAL] fail {e}", output_path)
        return False


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
            force_min_height=720, enhance_mode="quality", quality_floor=720
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
