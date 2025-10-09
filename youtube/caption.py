import os
import glob
import time
import logging
import re
from google import genai
from google.api_core import exceptions as genai_exceptions
from google.genai.types import Content, Part, GenerateContentConfig
from google.genai.errors import ClientError




PROMPT_FILE = "prompt.txt"

def load_system_instruction(prompt_file: str) -> str:
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        prompt_path = os.path.join(base_dir, prompt_file)
        with open(prompt_path, 'r', encoding='utf-8') as f:
            text = f.read().strip()
            if text:
                return text
            logging.warning(f"System instruction file '{prompt_file}' is empty. Using default.")
    except Exception as e:
        logging.warning(f"Could not read system instruction from '{prompt_file}': {e}. Using default.")
    return "System Instruction: Social Media Caption Generator for Hololive Talents"

SYSTEM_INSTRUCTION_TEXT = load_system_instruction(PROMPT_FILE)


DOWNLOADS_FOLDER = "new_week"
LOG_FILE = "debug/caption_generator.log"
CHECKPOINT_FILE = "debug/checkpoint.log"
MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
RETRIES = 3
RETRY_DELAY = 5

class QuotaExceededError(Exception):
    pass

class InvalidApiKeyError(Exception):
    pass

def _parse_retry_after_seconds(error_text: str) -> int | None:
    # Try to extract retryDelay from error details if present
    try:
        match = re.search(r"retryDelay['\"]:\s*'?(\d+)s" , error_text)
        if match:
            return int(match.group(1))
    except Exception:
        pass
    return None

# === LOGGING ===
logging.basicConfig(filename=LOG_FILE, level=logging.INFO,
                    format='%(asctime)s [%(levelname)s] %(message)s')

def extract_number(filename: str) -> int:
    match = re.search(r'\d+', filename)
    return int(match.group()) if match else float('inf')

# === GENERATE ===
def generate(prompt_text: str, api_key: str) -> str | None:
    client = genai.Client(api_key=api_key)

    try:
        contents = [
            Content(role="user", parts=[
                Part(text="hapus penggunakan kata caption di awal dan jangan menggunakan bold text atau berunsur **, IRYS Was In Pure Laughter Because of This Superchat #shorts #vtuber #hololive\n\nYoutube: Hololive Simposting")
            ]),
            Content(role="model", parts=[
                Part(text="""IRyS Cracks Up at a Hilarious Superchat! 😂🤣 Watch IRyS from Hololive English burst into laughter thanks to a particularly funny superchat! Her reactions are the best. Did you know IRyS is known for her beautiful singing and her ability to bring joy to her fans?

IRyS: Introducing IRyS, the charming Nephilim from Hololive English -Project: HOPE-! 😇✨ She is known for her amazing singing voice and sweet personality.

Clip Source: Hololive Simposting

#IRyS #hololiveEN #hololive #VTuber #hololiveEnglish #ProjectHope #Superchat #Funny #Laughter #Shorts #VTuberShorts #Clip #IRyStocrats #Singing #hololiveClips #Gaming #VirtualYoutuber #Reactions #Fun #Anime #EnglishVTuber""")
            ]),
            Content(role="user", parts=[Part(text=prompt_text)])
        ]

        config = GenerateContentConfig(
            response_mime_type="text/plain",
            system_instruction=[Part(text=SYSTEM_INSTRUCTION_TEXT)],
        )

        stream = client.models.generate_content_stream(
            model=MODEL,
            contents=contents,
            config=config,
        )

        return "".join(chunk.text for chunk in stream)

    except ClientError as e:
        # Let caller handle 429 and other client errors
        raise
    except genai_exceptions.GoogleAPICallError as e:
        logging.error(f"Google API error: {e}")
    except Exception as e:
        logging.exception("Unexpected error")
    return None

def generate_with_retry(prompt_text: str, api_key: str) -> str | None:
    for attempt in range(1, RETRIES + 1):
        try:
            return generate(prompt_text, api_key)
        except ClientError as e:
            error_text = str(e)
            status_code = getattr(e, "status_code", None)

            if status_code == 400 or "API_KEY_INVALID" in error_text:
                logging.error(f"Invalid API key: {e}")
                raise InvalidApiKeyError("Invalid or expired API key")
            elif status_code == 429 or "RESOURCE_EXHAUSTED" in error_text:
                if "GenerateRequestsPerDayPerProjectPerModel-FreeTier" in error_text:
                    logging.error("Daily quota exceeded. Aborting.")
                    raise QuotaExceededError("Daily quota exceeded")
                retry_after = _parse_retry_after_seconds(error_text)
                if retry_after is None:
                    retry_after = min(RETRY_DELAY * (2 ** (attempt - 1)), 60)
                print(f"⏳ Rate limited (429). Retrying in {retry_after}s... (Attempt {attempt}/{RETRIES})")
                time.sleep(retry_after)
                continue
            else:
                logging.error(f"Unhandled Client error: {e}")
        except (genai_exceptions.GoogleAPICallError, genai_exceptions.ServerError) as e:
            # Catch 503 UNAVAILABLE, 500 INTERNAL_SERVER_ERROR, etc.
            logging.warning(f"Server or API error: {e}. Retrying... (Attempt {attempt}/{RETRIES})")
            delay = min(RETRY_DELAY * (2 ** (attempt - 1)), 60)
            print(f"⚠️ Temporary server error. Retrying in {delay}s... (Attempt {attempt}/{RETRIES})")
            time.sleep(delay)
            continue
        except Exception as e:
            logging.exception(f"An unexpected error occurred: {e}")
            break # Hentikan loop jika error tidak diketahui
    return None

def save_checkpoint(filename: str):
    with open(CHECKPOINT_FILE, 'a', encoding='utf-8') as f:
        f.write(filename + '\n')

def load_checkpoint() -> set:
    if not os.path.exists(CHECKPOINT_FILE):
        return set()
    with open(CHECKPOINT_FILE, 'r', encoding='utf-8') as f:
        return set(line.strip() for line in f)

# === MAIN ===
def main():
    print("\U0001F4C2 Hololive Caption Generator with Range & Checkpoint\n")

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        api_key = input("\U0001F511 Enter your Gemini API Key: ").strip()
    if not api_key:
        print("\u274C API key is required.")
        return

    if not os.path.isdir(DOWNLOADS_FOLDER):
        print(f"\u274C Folder '{DOWNLOADS_FOLDER}' not found.")
        return

    txt_files = sorted(glob.glob(os.path.join(DOWNLOADS_FOLDER, "*.txt")),
                       key=lambda x: extract_number(os.path.basename(x)))
    total_files = len(txt_files)

    if total_files == 0:
        print("\u274C No .txt files found.")
        return

    print(f"\U0001F4E6 Total .txt files detected: {total_files}")
    range_input = input("\U0001F522 Enter range to process (e.g., 50-100): ").strip()
    match = re.match(r"(\d+)-(\d+)", range_input)
    if not match:
        print("\u274C Invalid range format. Use start-end (e.g., 50-100).")
        return

    start_idx, end_idx = int(match.group(1)), int(match.group(2))
    if start_idx < 1 or end_idx > total_files or start_idx > end_idx:
        print(f"\u274C Invalid range. Must be between 1 and {total_files}")
        return

    # Adjust for 0-based indexing
    selected_files = txt_files[start_idx - 1:end_idx]

    print(f"\n\U0001F680 Processing files {start_idx} to {end_idx}...\n")

    processed = load_checkpoint()

    for idx, file_path in enumerate(selected_files, start=start_idx):
        filename = os.path.basename(file_path)
        print(f"[{idx}] \U0001F504 Processing: {filename}")
        try:
            if filename in processed:
                print(f"  \u23ED\uFE0F Skipped (already processed): {filename}")
                continue
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()

            if not content:
                print(f"  \u26A0\uFE0F Skipped empty file: {filename}")
                continue

            try:
                new_content = generate_with_retry(content, api_key)
            except QuotaExceededError:
                print("  \u274C Daily quota exceeded. Stopping now. You can rerun later to resume.")
                break
            except InvalidApiKeyError:
                print("  \u274C API key invalid or expired. Please set a valid GEMINI_API_KEY and rerun to resume.")
                break
            if new_content:
                with open(file_path, 'w', encoding='utf-8') as f_out:
                    f_out.write(new_content)
                print(f"  \u2705 Updated: {filename}")
                save_checkpoint(filename)
                processed.add(filename)
            else:
                print(f"  \u274C Failed to generate: {filename}")
                logging.error(f"Failed to generate caption for: {filename}")

        except Exception as e:
            print(f"  \u274C Error on {filename}: {e}")
            logging.exception(f"Error processing {filename}")

if __name__ == "__main__":
    main()
