import json
import os
import subprocess
from typing import Optional, Dict, Any, List, Tuple

__all__ = [
    "check_yt_dlp_installation",
    "get_available_formats",
    "detect_best_hd_selector",
    "probe_resolution",
    "probe_resolution_bitrate",
    "upscale_video_if_needed",
    "enhance_video",
]

# ---------- basic ----------

def check_yt_dlp_installation() -> bool:
    try:
        r = subprocess.run(['yt-dlp','--version'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=10, encoding='utf-8', errors='replace')
        if r.returncode == 0:
            print("yt-dlp:", r.stdout.strip())
            return True
        return False
    except Exception:
        return False

def get_available_formats(video_url: str, extractor_args: Optional[str]=None) -> Optional[List[Dict[str,Any]]]:
    try:
        cmd = ['yt-dlp', '-J', '--no-warnings', '--quiet', '--no-check-certificates', video_url]
        if extractor_args:
            cmd += ['--extractor-args', extractor_args]
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=60, encoding='utf-8', errors='replace')
        if r.returncode != 0 or not r.stdout.strip():
            return None
        data = json.loads(r.stdout)
        return data.get('formats') or []
    except Exception:
        return None

# ---------- HD scanner (multi-client) ----------

_CLIENTS = [
    "youtube:player_client=android",
    "youtube:player_client=web",
    "youtube:player_client=ios",
    "youtube:player_client=tv",
    "youtube:player_client=android;formats=incomplete",
    "youtube:player_client=web;formats=incomplete",
]

def detect_best_hd_selector(
    video_url: str,
    min_height: int = 1080,
    prefer_codecs: Tuple[str,...] = ("av01","vp9","h264"),
) -> Optional[str]:
    """
    Cari kombinasi <video+audio> TERBAIK (≥ min_height).
    - Sapu beberapa player_client (android/web/ios/tv) + formats=incomplete.
    - Bangun selector berdasar format_id spesifik.
    - Urutan skor: height >> fps >> codec (av1>vp9>h264) >> tbr.
    """
    best_pair: Optional[Tuple[float, str]] = None

    def rank_codec(v: str) -> int:
        vv = (v or "").lower()
        # USER REQUEST: Prefer H.264/AVC for compatibility
        if "h264" in vv or "avc1" in vv: return 3
        if "vp9" in vv: return 2
        if "av01" in vv or "av1" in vv: return 1
        return 0

    for extargs in _CLIENTS:
        fmts = get_available_formats(video_url, extractor_args=extargs)
        if not fmts: 
            continue

        vids: List[Tuple[float, Dict[str,Any]]] = []
        auds: List[Tuple[float, Dict[str,Any]]] = []
        progs: List[Tuple[float, Dict[str,Any]]] = []

        for f in fmts:
            vcodec = f.get('vcodec')
            acodec = f.get('acodec')
            fid    = str(f.get('format_id'))
            h      = int(f.get('height') or 0)
            fps    = int(f.get('fps') or 0)
            tbr    = float(f.get('tbr') or 0.0)

            if vcodec and vcodec != 'none' and (not acodec or acodec == 'none'):
                score = h*10000 + fps*100 + rank_codec(vcodec)*50 + tbr
                vids.append((score, f))
            elif acodec and acodec != 'none' and (not vcodec or vcodec == 'none'):
                score = float(f.get('abr') or 0.0)
                auds.append((score, f))
            elif vcodec and vcodec != 'none' and acodec and acodec != 'none':
                score = h*10000 + fps*100 + rank_codec(vcodec)*50 + tbr
                progs.append((score, f))

        vids.sort(key=lambda x:x[0], reverse=True)
        auds.sort(key=lambda x:x[0], reverse=True)
        progs.sort(key=lambda x:x[0], reverse=True)

        # 1) prefer video-only ≥ min_height + audio terbaik
        for score, vf in vids:
            if int(vf.get('height') or 0) >= min_height:
                v_id = str(vf.get('format_id'))
                a_id = str((auds[0][1] if auds else {}).get('format_id', "")) if auds else ""
                if a_id:
                    sel = f"{v_id}+{a_id}"
                    pair_score = score + (auds[0][0] if auds else 0.0)
                    if (best_pair is None) or (pair_score > best_pair[0]):
                        best_pair = (pair_score, sel)
                else:
                    # tidak ada audio terpisah; coba progressive ≥ min_height
                    pass

        # 2) fallback progressive ≥ min_height
        for score, pf in progs:
            if int(pf.get('height') or 0) >= min_height:
                sel = str(pf.get('format_id'))
                if (best_pair is None) or (score > best_pair[0]):
                    best_pair = (score, sel)

    return best_pair[1] if best_pair else None

# ---------- ffprobe/ffmpeg helpers ----------

def probe_resolution(filepath: str) -> Optional[Tuple[int, int]]:
    try:
        r = subprocess.run(
            ['ffprobe','-v','error','-select_streams','v:0',
             '-show_entries','stream=width,height','-of','csv=p=0', filepath],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=20, encoding='utf-8', errors='replace'
        )
        if r.returncode != 0 or not r.stdout.strip():
            return None
        w,h = r.stdout.strip().split(',')
        return int(w), int(h)
    except Exception:
        return None

def probe_resolution_bitrate(filepath: str) -> Optional[Tuple[int,int,int]]:
    try:
        r = subprocess.run(
            ['ffprobe','-v','error','-select_streams','v:0',
             '-show_entries','stream=width,height,bit_rate','-of','csv=p=0', filepath],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=20, encoding='utf-8', errors='replace'
        )
        if r.returncode != 0 or not r.stdout.strip():
            return None
        parts = r.stdout.strip().split(',')
        w,h = int(parts[0]), int(parts[1])
        br = int(parts[2])//1000 if len(parts)>2 and parts[2].isdigit() else 0
        return w,h,br
    except Exception:
        return None

def _has_ffmpeg_sr_filter() -> bool:
    try:
        r = subprocess.run(['ffmpeg','-filters'], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           text=True, timeout=20, encoding='utf-8', errors='replace')
        return ' sr ' in r.stdout
    except Exception:
        return False

def upscale_video_if_needed(input_path: str, target_width: int=1080, target_height: int=1920,
                            crf: int=18, preset: str="slow") -> Optional[str]:
    wh = probe_resolution(input_path)
    if not wh:
        return None
    w,h = wh
    if (w >= target_width) and (h >= target_height):
        return None
    return enhance_video(input_path, target_width, target_height, mode="quality", crf=crf, preset=preset)

def enhance_video(input_path: str, target_width: int=1080, target_height: int=1920,
                  mode: str="quality", crf: int=18, preset: str="slow") -> Optional[str]:
    if mode == "off":
        return None
    out_path = input_path.rsplit('.',1)[0] + f".enhanced_{target_width}x{target_height}.mp4"
    try:
        base = (
            f"scale={target_width}:{target_height}:flags=lanczos:force_original_aspect_ratio=decrease,"
            f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2"
        )
        if mode == "fast":
            vf = f"{base},unsharp=3:3:0.6:3:3:0.3,eq=contrast=1.03:saturation=1.03,format=yuv420p"
        else:
            if _has_ffmpeg_sr_filter():
                vf = f"{base},hqdn3d=1.5:1.5:6:6,sr=fast,unsharp=5:5:0.8:3:3:0.4,eq=contrast=1.05:saturation=1.05,format=yuv420p"
            else:
                vf = f"{base},hqdn3d=1.5:1.5:6:6,unsharp=5:5:0.8:3:3:0.4,eq=contrast=1.05:saturation=1.05,format=yuv420p"

        cmd = [
            'ffmpeg','-y','-i', input_path,
            '-vf', vf,
            '-c:v','libx264','-crf', str(crf), '-preset', preset,
            '-c:a','copy',
            out_path
        ]
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           text=True, timeout=None, encoding='utf-8', errors='replace')
        if r.returncode == 0 and os.path.exists(out_path):
            return out_path
        return None
    except Exception:
        return None
