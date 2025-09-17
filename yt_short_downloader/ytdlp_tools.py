import subprocess
from typing import Optional
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from .utils import normalize_upload_date

__all__ = [
    "check_yt_dlp_installation",
    "test_video_accessibility",
    "get_available_formats",
    "get_best_available_format",
    "fetch_upload_date_by_id",       # NEW
    "enrich_missing_upload_dates",   # NEW
]


def check_yt_dlp_installation() -> bool:
    """Cek apakah yt-dlp terpasang dan bisa dipanggil."""
    try:
        result = subprocess.run(
            ['yt-dlp', '--version'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            print(f"yt-dlp version: {result.stdout.strip()}")
            return True
        print("yt-dlp terpasang tapi tidak berjalan dengan benar")
        return False
    except FileNotFoundError:
        print("yt-dlp tidak ditemukan. Install dengan: pip install yt-dlp")
        return False
    except subprocess.TimeoutExpired:
        print("Pengecekan yt-dlp timeout")
        return False
    except Exception as e:
        print(f"Error checking yt-dlp: {e}")
        return False


def test_video_accessibility(video_url: str) -> bool:
    try:
        cmd = [
            'yt-dlp',
            '--no-download', '--no-warnings', '--quiet', '--no-check-certificates',
            '--extractor-args', 'youtube:player_client=android',
            '--user-agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            video_url,
        ]
        result = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=30, encoding='utf-8', errors='replace'
        )
        return result.returncode == 0
    except Exception as e:
        print(f"Error testing video accessibility: {e}")
        return False


def get_available_formats(video_url: str) -> Optional[str]:
    try:
        cmd = ['yt-dlp', '--list-formats', '--no-warnings', '--quiet', '--no-check-certificates', video_url]
        result = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=60, encoding='utf-8', errors='replace'
        )
        if result.returncode == 0:
            return result.stdout
        return None
    except Exception as e:
        print(f"Error getting formats for {video_url}: {e}")
        return None


def get_best_available_format(video_url: str, preferred_format: str = 'mp4') -> Optional[str]:
    try:
        cmd = ['yt-dlp', '--list-formats', '--no-warnings', '--quiet', '--no-check-certificates', video_url]
        result = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=60, encoding='utf-8', errors='replace'
        )
        if result.returncode != 0:
            return None
        lines = result.stdout.split('\n')
        for line in lines:
            low = line.lower()
            if preferred_format in low and 'mp4' in low:
                parts = line.split()
                if parts and parts[0].isdigit():
                    return parts[0]
        return None
    except Exception as e:
        print(f"Error getting best format for {video_url}: {e}")
        return None


# ====== Upload date enrichment helpers ======

def fetch_upload_date_by_id(video_id: str) -> Optional[str]:
    """Ambil upload_date satu video via yt-dlp JSON. Return 'YYYY-MM-DD' atau None."""
    try:
        url = f"https://www.youtube.com/shorts/{video_id}"
        command = [
            'yt-dlp', url,
            '--skip-download', '--dump-single-json',
            '--no-check-certificate', '--restrict-filenames', '--ignore-no-formats-error',
        ]
        res = subprocess.run(command, capture_output=True, text=True, check=True, timeout=45)
        data = json.loads(res.stdout)
        return normalize_upload_date(data.get('upload_date'))
    except Exception:
        return None


def enrich_missing_upload_dates(entries: list[dict], max_tasks: int = 25, workers: int = 5) -> None:
    """
    Isi upload_date yang kosong untuk sebagian kecil entries (max_tasks) secara paralel.
    Mencegah enrichment masif yang bikin kelihatan seperti 'fetching terus'.
    """
    todo_idx = [i for i, e in enumerate(entries) if not normalize_upload_date(e.get('upload_date'))][:max_tasks]
    if not todo_idx:
        return
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futmap = {ex.submit(fetch_upload_date_by_id, entries[i].get('id')): i for i in todo_idx}
        for fut in as_completed(futmap):
            i = futmap[fut]
            try:
                up = fut.result()
                if up:
                    entries[i]['upload_date'] = up
            except Exception:
                # enrichment opsional; abaikan error
                pass
