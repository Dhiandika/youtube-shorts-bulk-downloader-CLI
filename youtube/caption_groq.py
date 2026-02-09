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

# Import Groq Library
from groq import Groq, RateLimitError, APIError, APIConnectionError

# === SYSTEM INSTRUCTION (HARDCODED) ===
# Prompt ini sudah digabung dengan aturan strict source & pov
SYSTEM_INSTRUCTION_TEXT = """
Role: You are the admin of a popular fan page for Hololive (Instagram, TikTok, Facebook). You are a dedicated "Holofans" who speaks the language of the community. You are NOT a corporate marketer.

Task: Write engaging, natural, and human-sounding English captions for short VTuber clips based on the description I provide.

📌 CRITICAL CLIP SOURCE RULE (MUST FOLLOW):
1. Look for the line "YouTube: <ChannelName>" in the user's input.
2. If found, you MUST use that exact ChannelName in the clip source.
   - Input: "YouTube: HoloClips" -> Output: "clip source: HoloClips [YouTube]"
3. ONLY if no channel is provided, use the VTuber's name.

📌 Output Format (MUST FOLLOW EXACTLY):
<Caption text>

clip source: <Source Name> [YouTube]

#<hashtags>

✍️ Writing Style & Tone Rules:
- Voice: Casual, friendly, spontaneous, and "Internet native" (like a fan posting on X/Twitter).
- Vibe: Use short, punchy sentences. React to the clip rather than describing it.
- Perspective: Write in **Third-Person** or **General Community POV**. NEVER use "I", "Me", "My".
- Reaction Types:
    - Funny: "LMAO", "I can't with her", "Kusa", "Yabe", "My sides hurt".
    - Cute/Wholesome: "Teetee", "So precious", "My heart melted", "Diabetes", "Must protect".
    - Fail/Clumsy: "Pon", "She's trying her best", "Sasuga Pon-queen".
    - Cool: "Sheesh", "God gamer", "Built different".
- Emojis: Use naturally, max 1–2 emojis. Use specific talent emojis if possible (e.g., 🦈 for Gura, 👯 for Fuwamoco, ☄️ for Suisei).

🚫 Strict Restrictions (Critical):
- NEVER say: "In this video", "This clip shows", "Watch till the end", "Caption for...", or "Here we see".
- NEVER use: Quotation marks around the whole text, bold text (**), or markdown formatting in the caption.
- NEVER include: The word "hashtag:" or "Title:".
- NO Context Dumping: Do not explain who the talent is. Fans already know. Just react!
🧠 HOLOLIVE KNOWLEDGE BASE (Use for Context):

--- SLANG & TERMINOLOGY ---
- **Kusa/WWWW**: LOL/Laughter[cite: 435].
- **Teetee**: Wholesome/Precious moment between talents[cite: 485].
- **Pon/Ponkotsu**: Clumsy/Fail moment[cite: 473].
- **Yabai**: Dangerous/Risky/Sus[cite: 502].
- **Gachikoi**: Fans truly in love with the talent[cite: 415].
- **Oshi**: The talent you support the most[cite: 463].

--- TALENT IDENTITIES & HASHTAGS ---

**HOLOLIVE JP (Generations 0-6)** [#hololiveJP]
- **Tokino Sora** (🐻): The Idol. "Sora-mama". #TokinoSora[cite: 159].
- **Suisei** (☄️): Blue Comet, Tetris god, psychopath in games. #HoshimachiSuisei[cite: 168].
- **Miko** (🌸): "Elite" gamer, GTA lover, distinct "Nye" speech. #SakuraMiko[cite: 171].
- **Fubuki** (🌽): Fox (not cat), Friend-zone master. "Yabe". #ShirakamiFubuki[cite: 180].
- **Aqua** (⚓): Gaming maid, shy/introvert (Baqua). #MinatoAqua[cite: 185].
- **Subaru** (🚑): Duck, tomboy, loud projection. #OozoraSubaru[cite: 193].
- **Korone** (🥐): Doggo, collects fingers (Yubi Yubi), endurance streamer. #InugamiKorone.
- **Pekora** (👯): Rabbit, war criminal (joke), distinctive laugh "PEKO". #UsadaPekora[cite: 202].
- **Marine** (🏴‍☠️): Pirate captain, "Ahoy", acts older/boomer (Senchou). #HoushouMarine[cite: 208].
- **Kanata** (💫): Angel (Gorilla strength). #AmaneKanata[cite: 210].
- **Towa** (👾): Devil (TMT - Towa Maji Tenshi/Angel). #TokoyamiTowa[cite: 216].
- **Lamy** (☃️): Snow elf, loves sake/alcohol. #YukihanaLamy[cite: 220].
- **Koyori** (🧪): Pink Coyote, scientist, talks fast. #HakuiKoyori[cite: 228].
- **Chloe** (🎣): Orca, stinky/doesn't bathe (joke), Pon. #SakamataChloe[cite: 230].

**HOLOLIVE ID (Generations 1-3)** [#hololiveID]
- **Risu** (🐿️): Squirrel, NNN queen, Prisuners. #AyundaRisu[cite: 239].
- **Moona** (🔮): Moon goddess, NPC energy, Hoshinova. #MoonaHoshinova[cite: 241].
- **Ollie** (🧟‍♀️): Zombie, loud, hyperactive, ZOMBOID. #KureijiOllie[cite: 245].
- **Kaela** (🔨): Blacksmith, grinder (no sleep), "Get some help". #KaelaKovalskia[cite: 253].
- **Kobo** (☔): Rain shaman, Kusogaki (brat), "Ame Ampas". #KoboKanaeru[cite: 255].

**HOLOLIVE EN (Myth, Promise, Advent, Justice)** [#hololiveEN]
- **Calli** (💀): Reaper, rapper, Dad vibes. #MoriCalliope[cite: 258].
- **Kiara** (🐔): Phoenix, KFP CEO, "Am I a joke to you?". #TakanotsumeKiara[cite: 260].
- **Ina** (🐙): Priestess, comfy vibes, puns (Inaff). #NinomaeInanis[cite: 262].
- **Gura** (🔱): Shark, "a", goofy, trident. #GawrGura[cite: 264].
- **Amelia** (🔎): Detective, Time traveler, Gremlin, Ground pound. #WatsonAmelia[cite: 266].
- **IRyS** (💎): Nephilim (Hope), "YabaIRyS". #IRyS[cite: 268].
- **Kronii** (⏳): Time warden, narcissist, "GWAK". #OuroKronii[cite: 274].
- **Mumei** (🪶): Owl, forgets everything, Civilization (scary). #NanashiMumei[cite: 276].
- **Bae** (🎲): Chaos rat, Zoomer energy. #HakosBaelz[cite: 278].
- **Shiori** (👁️‍🗨️): Goth librarian, weird tangents. #ShioriNovella[cite: 280].
- **Bijou** (🗿): Rock/Jewel, Moai, Koseki Biboo. #KosekiBijou[cite: 282].
- **Nerissa** (🎼): Raven, soup lover, great singer. #NerissaRavencroft[cite: 284].
- **FUWAMOCO** (🐾): Twin dogs, "Bau Bau", synchronized. #FuwawaAbyssgard #MococoAbyssgard[cite: 286, 289].
- **Raora** (🐱): Panther, Italian, artist, "Godines". #RaoraPanthera[cite: 298].
- **Cecilia** (🍵): Automaton, "For Justice". #CeciliaImmergreen[cite: 296].

**HOLOLIVE DEV_IS (ReGLOSS, FLOW GLOW)** [#hololiveDEV_IS]
- **Ao** (🖋️): Blue Oni, cool but huge Pon. #HiodoshiAo[cite: 301].
- **Raden** (🐚): Art lover, Rakugo, sophisticated yapper. #JuufuuteiRaden[cite: 307].
- **Kanade** (🎹): Bratty vibe, great singer. #OtonoseKanade[cite: 303].

**NOTABLE ALUMNI/OTHERS**
- **Coco** (🐉): Dragon, legendary, "Good Morning Motherf*ckers". #KiryuCoco[cite: 212].
- **Aqua** (⚓): Legendary gamer maid. #MinatoAqua[cite: 333].
- **Rushia** (🦋): Necromancer, scream, cutting board (flat).[cite: 331].

🏷️ Hashtag Strategy:
- Hashtags go on the LAST line only.
- NO emojis in hashtags.
- Required Tags: Talent Name (e.g., #usadapekora), Branch (#hololiveJP/EN/ID), #hololive, #vtuber.
- Optional Tags: #anime, #fyp, #vtuberclips.
"""

# === DAFTAR MODEL GROQ ===
SMART_MODEL_LIST = [
    "llama-3.3-70b-versatile",  # Prioritas Kualitas
    "llama-3.1-8b-instant",     # Prioritas Kecepatan & Limit Besar
]

# FOLDER & CONFIG
DOWNLOADS_FOLDER = "new_week/1080x1920"
LOG_FILE = "debug/groq_caption_generator.log"
CHECKPOINT_FILE = "debug/groq_checkpoint.log"

RETRIES_PER_MODEL = 2
MAX_INPUT_CHARS = 10000  # Batas karakter agar tidak error 413

# === LOGGING SETUP ===
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
    combo = os.environ.get("GROQ_API_KEYS", "")
    if combo.strip():
        keys.extend(_split_candidates(combo))
    single = os.environ.get("GROQ_API_KEY", "")
    if single.strip():
        keys.append(single.strip())
    for i in range(1, 11):
        k = os.environ.get(f"GROQ_API_KEY_{i}", "")
        if k.strip():
            keys.append(k.strip())
    seen = set()
    unique_keys = []
    for k in keys:
        if k and k not in seen:
            unique_keys.append(k)
            seen.add(k)
    return unique_keys

# === GENERATE FUNCTION (DENGAN TRUNCATE & STRICT RULES) ===
def generate(prompt_text: str, api_key: str, model_name: str) -> str | None:
    client = Groq(api_key=api_key)

    # 1. Truncate Logic (Mencegah error 413)
    if len(prompt_text) > MAX_INPUT_CHARS:
        print(f"    ✂️ Input terlalu panjang ({len(prompt_text)} chars). Memotong ke {MAX_INPUT_CHARS} chars...")
        prompt_text = prompt_text[:MAX_INPUT_CHARS] + "\n...[truncated]"

    try:
        completion = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_INSTRUCTION_TEXT
                },
                # Few-Shot Example untuk mengajarkan Source Rule & Format
                {
                    "role": "user",
                    "content": "IRyS laughing hard at a funny superchat.\n\nYouTube: Hololive Simposting"
                },
                {
                    "role": "assistant",
                    "content": """IRyS losing it over a superchat is pure serotonin 😂 Her laugh is contagious! The Nephilim has completely lost composure here lol. Protect that smile! 💎🙏

clip source: Hololive Simposting [YouTube]

#IRyS #ProjectHOPE #hololiveEN #hololive #vtuber #funny #shorts"""
                },
                # Input Real
                {
                    "role": "user",
                    "content": prompt_text
                }
            ],
            model=model_name,
            temperature=0.7,
            max_tokens=1024,
        )
        return completion.choices[0].message.content

    except RateLimitError as e:
        raise e
    except APIError as e:
        if "Request too large" in str(e) or "413" in str(e):
             logging.error(f"Input oversize: {e}")
             print("    ❌ Masih terlalu besar (413). Skip file ini.")
             return None
        logging.error(f"Groq API Error: {e}")
        raise e
    except Exception as e:
        logging.exception("Unexpected error in generate")
        raise e

# === SMART FALLBACK LOGIC ===
def generate_with_smart_fallback(prompt_text: str, api_keys: List[str], start_idx: int = 0) -> Tuple[Optional[str], Optional[int]]:
    if not api_keys:
        return None, None

    n = len(api_keys)
    for offset in range(n):
        key_idx = (start_idx + offset) % n
        current_key = api_keys[key_idx]
        masked_key = f"****{current_key[-4:]}"
        
        print(f"🔐 Key #{key_idx+1}: {masked_key}")

        for model_name in SMART_MODEL_LIST:
            print(f"  👉 Trying Model: {model_name}...")
            
            for attempt in range(1, RETRIES_PER_MODEL + 1):
                try:
                    result = generate(prompt_text, current_key, model_name)
                    if result:
                        return result, key_idx
                    
                except RateLimitError as e:
                    print(f"    ⏳ Rate Limited (429) on {model_name}.")
                    if "requests per day" in str(e).lower():
                        print(f"    ⛽ Daily Limit hit for {model_name}. Switching model...")
                        break 
                    retry_time = 5 * attempt
                    print(f"    ⏳ Cooling down {retry_time}s...")
                    time.sleep(retry_time)
                    continue

                except APIConnectionError:
                    print("    ⚠️ Connection error. Retrying...")
                    time.sleep(2)
                    continue

                except Exception as e:
                    print(f"    ❌ Error: {e}")
                    if "authentication" in str(e).lower() or "invalid api key" in str(e).lower():
                        print("    ❌ Invalid Key. Switching Key.")
                        break 
                    break 
            
            if "invalid api key" in str(locals().get('e', '')).lower():
                break

        print(f"  ⚠️ All models failed for Key #{key_idx+1}. Trying next key...\n")

    return None, None

# === UTILS ===
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
    print("\U0001F4C2 Hololive Caption Generator (Groq Hardcoded)\n")

    api_keys = load_api_keys()

    if not api_keys:
        manual = input("\U0001F511 Enter your GROQ API Key: ").strip()
        if not manual:
            print("❌ No API key provided.")
            return
        api_keys = [manual]

    print(f"🔑 Loaded {len(api_keys)} API key(s).")
    print(f"🤖 Models: {SMART_MODEL_LIST}")

    if not os.path.isdir(DOWNLOADS_FOLDER):
        print(f"❌ Folder '{DOWNLOADS_FOLDER}' not found.")
        return

    txt_files = sorted(glob.glob(os.path.join(DOWNLOADS_FOLDER, "*.txt")),
                       key=lambda x: extract_number(os.path.basename(x)))
    
    print(f"📦 Total files: {len(txt_files)}")
    
    range_input = input("🔢 Enter range (e.g., 1-283): ").strip()
    match = re.match(r"(\d+)-(\d+)", range_input)
    if not match:
        print("❌ Invalid range.")
        return

    start_idx, end_idx = int(match.group(1)), int(match.group(2))
    selected_files = txt_files[start_idx - 1:end_idx]

    print(f"\n🚀 Processing {len(selected_files)} files...\n")

    processed = load_checkpoint()
    current_key_idx = 0

    for idx, file_path in enumerate(selected_files, start=start_idx):
        filename = os.path.basename(file_path)
        print(f"[{idx}] 📄 Processing: {filename}")
        
        if filename in processed:
            print(f"  ⏭️  Skipped (Already done)")
            continue

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            
            if not content:
                print("  ⚠️ Empty file.")
                continue

            new_content, used_idx = generate_with_smart_fallback(content, api_keys, start_idx=current_key_idx)

            if new_content:
                with open(file_path, 'w', encoding='utf-8') as f_out:
                    f_out.write(new_content)
                print(f"  ✅ Success!")
                save_checkpoint(filename)
                processed.add(filename)
                
                if used_idx is not None:
                    current_key_idx = used_idx
                
                time.sleep(1) 
            else:
                print(f"  ❌ Failed (All limits exhausted)")

        except Exception as e:
            print(f"  ❌ Error reading/writing file: {e}")

if __name__ == "__main__":
    main()