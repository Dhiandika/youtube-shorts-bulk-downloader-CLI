import os
import re
import subprocess
from urllib.parse import urlparse

def check_yt_dlp_installation() -> bool:
    try:
        r = subprocess.run(
            ["yt-dlp", "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
        )
        if r.returncode == 0:
            print(f"yt-dlp version: {r.stdout.strip()}")
            return True
        print("yt-dlp terpasang tapi tidak berjalan dengan benar.")
        return False
    except FileNotFoundError:
        print("yt-dlp tidak ditemukan. Install dengan: pip install -U yt-dlp")
        return False
    except subprocess.TimeoutExpired:
        print("Pengecekan yt-dlp timeout.")
        return False
    except Exception as e:
        print(f"Error cek yt-dlp: {e}")
        return False

def is_tiktok_url(url: str) -> bool:
    try:
        return "tiktok.com" in urlparse(url).netloc.lower()
    except Exception:
        return False

def sanitize_filename(title: str, maxlen=120) -> str:
    title = re.sub(r"[^\x20-\x7E]", "", title)                 # non-printable
    title = re.sub(r'[<>:"/\\|?*]', "_", title)                # ganti karakter ilegal
    title = re.sub(r"[\s_]+", "_", title).strip("_")           # kompres spasi/_
    return (title[:maxlen] if len(title) > maxlen else title) or "untitled"

def validate_filename(filename: str) -> bool:
    if re.search(r'[<>:"/\\|?*\x00-\x1F\x7F-\x9F]', filename):
        return False
    if not filename.isascii():
        return False
    return len(filename) <= 255

def get_unique_filename(base_path: str, filename: str) -> str:
    path = os.path.join(base_path, filename)
    if not os.path.exists(path):
        return filename
    name, ext = os.path.splitext(filename)
    i = 1
    while True:
        candidate = f"{name}_{i}{ext}"
        if not os.path.exists(os.path.join(base_path, candidate)):
            return candidate
        i += 1

def get_existing_index(output_path: str) -> int:
    files = os.listdir(output_path)
    idxs = [int(f.split(" - ")[0]) for f in files if f.split(" - ")[0].isdigit()]
    return max(idxs, default=0)

def cleanup_partial_downloads(output_path: str, filename_prefix: str):
    try:
        for f in os.listdir(output_path):
            if f.startswith(filename_prefix) and f.endswith(".part"):
                try:
                    os.remove(os.path.join(output_path, f))
                except Exception as e:
                    print(f"Gagal hapus partial {f}: {e}")
    except Exception as e:
        print(f"Error cleanup partial: {e}")

def normalize_input_to_url_list(user_input: str):
    user_input = user_input.strip()
    if user_input.startswith("@"):
        return [f"https://www.tiktok.com/{user_input}"]
    if user_input.startswith("#"):
        tag = user_input[1:]
        return [f"https://www.tiktok.com/tag/{tag}"]
    if is_tiktok_url(user_input):
        return [user_input]
    return [f"https://www.tiktok.com/@{user_input}"]
