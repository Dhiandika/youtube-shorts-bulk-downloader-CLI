# console_guard.py
# Hardened console guard: cegah 'charmap' UnicodeEncodeError di Windows

import sys
import builtins
import unicodedata
import re
import os

# Pastikan runtime Python prefer UTF-8 (aman untuk subprocess/IO)
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

# Coba paksa stream ke UTF-8 + replace
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

def _console_sanitize(text) -> str:
    """
    Console-only sanitization:
      - NFKD: '𝗟' -> 'L'
      - Buang non-ASCII (emoji/simbol dekoratif) untuk menghindari 'charmap'
      - Rapikan spasi
    Tidak memodifikasi nilai asli di logikamu; hanya saat print.
    """
    if text is None:
        return ""
    s = unicodedata.normalize("NFKD", str(text))
    s = s.encode("ascii", "ignore").decode("ascii", "ignore")
    s = re.sub(r"\s+", " ", s).strip()
    return s

# Simpan print asli
__orig_print = builtins.print

def __safe_print(*args, sep=" ", end="\n", file=None, flush=False):
    out = file or sys.stdout
    # Sanitisasi semua argumen jadi ASCII aman
    safe_args = tuple(_console_sanitize(a) for a in args)
    msg = sep.join(safe_args) + end
    try:
        out.write(msg)
    except Exception:
        # Fallback: tulis bytes pakai replace supaya tidak pernah crash
        data = msg.encode(getattr(out, "encoding", None) or "utf-8", errors="replace")
        try:
            out.buffer.write(data)
        except Exception:
            sys.stdout.buffer.write(data)
    if flush:
        try:
            out.flush()
        except Exception:
            pass

# Patch global print
builtins.print = __safe_print
