import subprocess
from typing import Optional

__all__ = [
    "check_yt_dlp_installation",
    "test_video_accessibility",
    "get_available_formats",
    "get_best_available_format",
]


def check_yt_dlp_installation() -> bool:
    try:
        result = subprocess.run(
            ['yt-dlp', '--version'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
            encoding='utf-8',     # penting
            errors='replace',     # penting
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
    
    