import os
import glob
import time
import logging
import re
import pathlib
from typing import List, Tuple, Optional

# === Load .env ===
try:
    from dotenv import load_dotenv
    BASE_DIR = pathlib.Path(__file__).resolve().parent
    dotenv_path = BASE_DIR / ".env"
    load_dotenv(dotenv_path=dotenv_path, override=False)
except Exception:
    pass

from google import genai
from google.api_core import exceptions as genai_exceptions
from google.genai.types import Content, Part, GenerateContentConfig
from google.genai.errors import ClientError

PROMPT_FILE = "prompt.txt"

# === KONFIGURASI MODEL & RATE LIMIT (Berdasarkan Screenshot) ===
# Kita hanya pakai 2 model ini sesuai limit Free Tier
SMART_MODEL_LIST = [
    "gemini-2.5-flash",       # Limit: 5 RPM, 20 RPD
    "gemini-2.5-flash-lite"   # Limit: 10 RPM, 20 RPD
]

# Set tracking untuk resource yang habis kuota hariannya
# Format: set("API_KEY_LAST4_CHARS:MODEL_NAME")
EXHAUSTED_RESOURCES = set()

# === SYSTEM INSTRUCTION ===
DEFAULT_SYSTEM_INSTRUCTION = """
Role: You are the admin of a massive Hololive fan community page.

Task: Write engaging, viral-style captions for clips.

📌 PERSPECTIVE RULE (CRITICAL):
1. Write in **Third-Person** (She/He/They) or **General Community POV**.
2. **NEVER** use First-Person Singular pronouns like "I", "Me", "My", "Mine".
3. Focus on the *content* of the video, not your personal feelings.

📌 CLIP SOURCE RULE:
1. Look for "YouTube: <ChannelName>" in input.
2. Output MUST be "clip source: <ChannelName> [YouTube]".
3. Do NOT replace ChannelName with the VTuber's name.

📌 Output Format:
<Caption text>

clip source: <Source Channel Name> [YouTube]

#<hashtags>

✍️ Tone: Hype, funny, or wholesome. Use internet slang naturally (kusa, teetee, lol). Max 1-2 emojis.
"""

def load_system_instruction(prompt_file: str) -> str:
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        prompt_path = os.path.join(base_dir, prompt_file)
        if os.path.exists(prompt_path):
            with open(prompt_path, 'r', encoding='utf-8') as f:
                text = f.read().strip()
                if text:
                    return text
    except Exception:
        pass
    return DEFAULT_SYSTEM_INSTRUCTION

SYSTEM_INSTRUCTION_TEXT = load_system_instruction(PROMPT_FILE)

DOWNLOADS_FOLDER = "new_week/1080x1920"
LOG_FILE = "debug/caption_generator.log"
CHECKPOINT_FILE = "debug/checkpoint.log"

# === LOGGING ===
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
logging.basicConfig(filename=LOG_FILE, level=logging.INFO,
                    format='%(asctime)s [%(levelname)s] %(message)s')

def extract_number(filename: str) -> int:
    match = re.search(r'\d+', filename)
    return int(match.group()) if match else float('inf')

# === API KEYS LOADER ===
def _split_candidates(s: str) -> List[str]:
    raw = re.split(r"[,\s;]+", s.strip())
    return [x.strip() for x in raw if x.strip()]

def load_api_keys() -> List[str]:
    keys: List[str] = []
    combo = os.environ.get("GEMINI_API_KEYS", "")
    if combo.strip():
        keys.extend(_split_candidates(combo))
    single = os.environ.get("GEMINI_API_KEY", "")
    if single.strip():
        keys.append(single.strip())
    for i in range(1, 11):
        k = os.environ.get(f"GEMINI_API_KEY_{i}", "")
        if k.strip():
            keys.append(k.strip())
    
    seen = set()
    unique_keys = []
    for k in keys:
        if k and k not in seen:
            unique_keys.append(k)
            seen.add(k)
    return unique_keys

# === GENERATE FUNCTION ===
def generate(prompt_text: str, api_key: str, model_name: str) -> str | None:
    client = genai.Client(api_key=api_key)

    try:
        contents = [
            Content(role="user", parts=[
                Part(text="IRyS laughing hard at a funny superchat.\n\nYouTube: Hololive Simposting")
            ]),
            Content(role="model", parts=[
                Part(text="""IRyS losing it over a superchat is pure serotonin 😂 Her laugh is contagious! The Nephilim has completely lost composure here lol. Protect that smile! 💎🙏

clip source: Hololive Simposting [YouTube]

#IRyS #ProjectHOPE #hololiveEN #hololive #vtuber #funny #shorts""")
            ]),
            Content(role="user", parts=[Part(text=prompt_text)])
        ]

        config = GenerateContentConfig(
            response_mime_type="text/plain",
            system_instruction=[Part(text=SYSTEM_INSTRUCTION_TEXT)],
            temperature=0.7,
        )

        stream = client.models.generate_content_stream(
            model=model_name,
            contents=contents,
            config=config,
        )

        return "".join(chunk.text for chunk in stream)

    except ClientError as e:
        raise
    except genai_exceptions.GoogleAPICallError as e:
        raise 
    except Exception as e:
        logging.exception("Unexpected error")
        raise
    return None

# === SMART FALLBACK LOGIC WITH COOLDOWN ===
def generate_with_smart_fallback(prompt_text: str, api_keys: List[str], start_idx: int = 0) -> Tuple[Optional[str], Optional[int]]:
    if not api_keys:
        return None, None

    n = len(api_keys)
    
    # Loop Key (Round Robin)
    for offset in range(n):
        key_idx = (start_idx + offset) % n
        current_key = api_keys[key_idx]
        masked_key = f"****{current_key[-4:]}"
        
        # Loop Model
        for model_name in SMART_MODEL_LIST:
            # Cek apakah resource ini sudah habis jatah hariannya?
            resource_id = f"{masked_key}:{model_name}"
            if resource_id in EXHAUSTED_RESOURCES:
                continue # Skip resource yang sudah mati

            print(f"🔐 Key {masked_key} | 🤖 {model_name}...")
            
            # Retry max 3 kali untuk Rate Limit RPM
            for attempt in range(1, 4):
                try:
                    result = generate(prompt_text, current_key, model_name)
                    if result:
                        # === COOLDOWN SUKSES ===
                        # RPM Flash adalah 5, jadi idealnya tunggu 12 detik.
                        # RPM Flash-Lite adalah 10, jadi idealnya tunggu 6 detik.
                        # Kita ambil aman rata-rata 10 detik agar akun aman.
                        print("    ⏳ Cooldown 10s (Safety)...")
                        time.sleep(10)
                        return result, key_idx
                    
                except ClientError as e:
                    error_text = str(e)
                    status_code = getattr(e, "status_code", None)
                    
                    # 1. Handle Daily Quota (20 req/day)
                    if status_code == 429 or "RESOURCE_EXHAUSTED" in error_text:
                        if "GenerateRequestsPerDay" in error_text or "QUOTA_EXCEEDED" in error_text or "limit: 0" in error_text:
                            print(f"    ⛽ Daily Quota HABIS untuk {resource_id}. Marking as exhausted.")
                            EXHAUSTED_RESOURCES.add(resource_id) # Tandai mati
                            break # Ganti model/key
                        
                        # 2. Handle Rate Limit RPM (Per Menit)
                        else:
                            # Jika kena RPM limit, kita tunggu lebih lama
                            wait_time = 20 * attempt
                            print(f"    ⏳ RPM Limit hit. Waiting {wait_time}s...")
                            time.sleep(wait_time)
                            continue # Retry model yang sama
                    
                    elif status_code == 404:
                         print(f"    ❌ Model not found (404).")
                         break # Ganti model

                    else:
                        print(f"    ⚠️ Error {status_code}: {e}")
                        break

                except Exception as e:
                    print(f"    ❌ Error: {e}")
                    break
            
            # Jika resource ditandai exhausted, lanjut ke model berikutnya
            if resource_id in EXHAUSTED_RESOURCES:
                continue

    print(f"  ⚠️ Gagal mendapatkan caption dengan semua Key & Model yang tersedia.\n")
    return None, None

def save_checkpoint(filename: str):
    os.makedirs(os.path.dirname(CHECKPOINT_FILE), exist_ok=True)
    with open(CHECKPOINT_FILE, 'a', encoding='utf-8') as f:
        f.write(filename + '\n')

def load_checkpoint() -> set:
    if not os.path.exists(CHECKPOINT_FILE):
        return set()
    with open(CHECKPOINT_FILE, 'r', encoding='utf-8') as f:
        return set(line.strip() for line in f)

# === MAIN ===
def main():
    print("\U0001F4C2 Hololive Caption Generator (Free Tier Optimized)\n")

    api_keys = load_api_keys()
    if not api_keys:
        manual = input("\U0001F511 Enter your Gemini API Key: ").strip()
        if not manual: return
        api_keys = [manual]

    print(f"🔑 Loaded {len(api_keys)} Keys.")
    print(f"🤖 Models: {SMART_MODEL_LIST}")

    if not os.path.isdir(DOWNLOADS_FOLDER):
        print(f"\u274C Folder '{DOWNLOADS_FOLDER}' not found.")
        return

    txt_files = sorted(glob.glob(os.path.join(DOWNLOADS_FOLDER, "*.txt")),
                       key=lambda x: extract_number(os.path.basename(x)))
    
    # Filter file yang belum diproses (exclude dari checkpoint)
    processed = load_checkpoint()
    
    # Range Input
    print(f"\U0001F4E6 Total files: {len(txt_files)}")
    range_input = input("\U0001F522 Enter range (e.g., 1-283): ").strip()
    match = re.match(r"(\d+)-(\d+)", range_input)
    if not match: return
    start, end = int(match.group(1)), int(match.group(2))
    
    selected_files = txt_files[start-1:end]
    print(f"\n\U0001F680 Processing {len(selected_files)} files...\n")

    current_key_idx = 0

    for idx, file_path in enumerate(selected_files, start=start):
        filename = os.path.basename(file_path)
        
        if filename in processed:
            continue

        print(f"[{idx}] 📄 {filename}")

        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
        if not content: continue

        new_content, used_idx = generate_with_smart_fallback(content, api_keys, start_idx=current_key_idx)

        if new_content:
            with open(file_path, 'w', encoding='utf-8') as f_out:
                f_out.write(new_content)
            print(f"  ✅ Updated.")
            save_checkpoint(filename)
            processed.add(filename)
            if used_idx is not None:
                current_key_idx = used_idx
        else:
            print(f"  🛑 Skipped (Quota Habis).")

if __name__ == "__main__":
    main()