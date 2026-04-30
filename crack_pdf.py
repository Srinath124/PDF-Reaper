"""
=============================================================
  GPU-ACCELERATED PDF PASSWORD RECOVERY
  
  Pattern  : [A-Z]{4} + DDMM  (exactly 8 characters)
  Engine   : Hashcat (GPU via CUDA/OpenCL, CPU fallback)
  Attack   : Mode 7 — Hybrid  (Mask + Wordlist)
  
  Mask     : ?u?u?u?u   → 26^4 = 456,976 prefixes
  Wordlist : dates.txt  → 366 valid DDMM entries
  Total    : 456,976 × 366 ≈ 167 million passwords

  Usage:
    python crack_pdf.py <protected.pdf>
    python crack_pdf.py <protected.pdf> --hashcat <path/to/hashcat>

  Requirements:
    pip install pikepdf
    hashcat  (https://hashcat.net/hashcat/)
=============================================================
"""

import sys
import os
import re
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Optional, Tuple

# ──────────────────────────────────────────────────────────────
#  PATHS & CONSTANTS
# ──────────────────────────────────────────────────────────────
SCRIPT_DIR    = Path(__file__).parent
HASH_FILE     = SCRIPT_DIR / "hash.txt"
DATES_FILE    = SCRIPT_DIR / "dates.txt"
POT_FILE      = SCRIPT_DIR / "hashcat.pot"
OUTPUT_FOLDER = SCRIPT_DIR / "unlocked"
DROP_FOLDER   = SCRIPT_DIR / "drop_file_here"

HASHCAT_BIN   = "hashcat"           # override with --hashcat <path>

PDF2JOHN_PATH = SCRIPT_DIR / "pdf2john.py"
PDF2JOHN_URL  = (
    "https://raw.githubusercontent.com/openwall/john"
    "/bleeding-jumbo/run/pdf2john.py"
)

# Valid days per month (include Feb-29 for leap years)
DAYS_IN_MONTH = {
    1: 31, 2: 29, 3: 31, 4: 30, 5: 31,  6: 30,
    7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31,
}


# ──────────────────────────────────────────────────────────────
#  PRETTY PRINTING
# ──────────────────────────────────────────────────────────────
def banner() -> None:
    print(r"""
  ╔═══════════════════════════════════════════════════════════╗
  ║        GPU-ACCELERATED PDF PASSWORD RECOVERY              ║
  ║                                                           ║
  ║  Pattern : [A-Z][A-Z][A-Z][A-Z] + DD + MM               ║
  ║  Engine  : Hashcat (CUDA/OpenCL)  +  CPU fallback        ║
  ║  Attack  : Hybrid Mode 7 — Mask(?u?u?u?u) + DDMM list    ║
  ║  Space   : 26^4 x 366 ≈ 167 million passwords            ║
  ╚═══════════════════════════════════════════════════════════╝
""")


def ok(msg: str)   -> None: print(f"  ✓  {msg}")
def info(msg: str) -> None: print(f"  ·  {msg}")
def warn(msg: str) -> None: print(f"  ⚠  {msg}")
def err(msg: str)  -> None: print(f"  ✗  {msg}")

def section(title: str) -> None:
    print(f"\n{'─'*60}")
    print(f"  {title}")
    print('─'*60)

def die(msg: str) -> None:
    err(msg)
    sys.exit(1)


# ──────────────────────────────────────────────────────────────
#  STAGE 1 — GPU DETECTION
# ──────────────────────────────────────────────────────────────
def detect_gpu() -> bool:
    """Return True if an NVIDIA GPU is available via nvidia-smi."""
    section("STAGE 1 · GPU DETECTION")
    rc, out, _ = run_cmd("nvidia-smi --query-gpu=name,driver_version,memory.total "
                         "--format=csv,noheader,nounits")
    if rc != 0 or not out.strip():
        warn("NVIDIA GPU not found — will use CPU (slower but still works)")
        return False

    parts = out.strip().split(",")
    gpu   = parts[0].strip() if parts else "Unknown GPU"
    drv   = parts[1].strip() if len(parts) > 1 else "?"
    mem   = parts[2].strip() if len(parts) > 2 else "?"
    try:
        mem_gb = f"{int(mem)/1024:.1f} GB"
    except Exception:
        mem_gb = f"{mem} MB"

    ok(f"GPU  : {gpu}")
    info(f"Driver : {drv}")
    info(f"Memory : {mem_gb}")
    return True


# ──────────────────────────────────────────────────────────────
#  STAGE 2 — HASHCAT VERIFICATION
# ──────────────────────────────────────────────────────────────
def verify_hashcat() -> None:
    """Confirm hashcat binary is accessible; print install help if not."""
    section("STAGE 2 · HASHCAT VERIFICATION")
    rc, out, _ = run_cmd(f'"{HASHCAT_BIN}" --version')
    if rc != 0:
        die(
            "Hashcat not found.\n\n"
            "  Install options:\n"
            "    • Download  : https://hashcat.net/hashcat/\n"
            "    • Windows   : choco install hashcat\n"
            "                  scoop install hashcat\n"
            "    • Linux/Mac : sudo apt install hashcat\n\n"
            "  Then add its folder to your PATH, or run:\n"
            "    python crack_pdf.py <file.pdf> --hashcat <path/to/hashcat>"
        )
    ok(f"Hashcat {out.strip()} ready")


# ──────────────────────────────────────────────────────────────
#  STAGE 3 — PDF HASH EXTRACTION
# ──────────────────────────────────────────────────────────────
def ensure_pdf2john() -> None:
    if PDF2JOHN_PATH.exists():
        return
    info("Downloading pdf2john.py …")
    try:
        urllib.request.urlretrieve(PDF2JOHN_URL, PDF2JOHN_PATH)
        ok(f"Saved → {PDF2JOHN_PATH}")
    except Exception as ex:
        die(
            f"Cannot download pdf2john.py: {ex}\n\n"
            f"  Manual fix:\n"
            f"    1. Open: {PDF2JOHN_URL}\n"
            f"    2. Save to: {PDF2JOHN_PATH}\n"
            f"    3. Re-run the script"
        )


def extract_hash(pdf_path: Path) -> str:
    """Extract $pdf$… hash from PDF using pdf2john."""
    section("STAGE 3 · HASH EXTRACTION")
    info(f"File : {pdf_path}")
    ensure_pdf2john()

    cmd = f'"{sys.executable}" "{PDF2JOHN_PATH}" "{pdf_path}"'
    rc, out, stderr = run_cmd(cmd)

    if rc != 0 or not out.strip():
        die(
            f"Hash extraction failed.\n"
            f"  Command : {cmd}\n"
            f"  Stderr  : {stderr or 'no output'}\n\n"
            f"  Common causes:\n"
            f"    • PDF is not password-protected\n"
            f"    • PDF file is corrupted\n"
            f"    • Unusual / unsupported encryption version"
        )

    raw = out.strip()
    # pdf2john format:  filename:$pdf$...:extra
    # Keep only the $pdf$... token
    if ":" in raw:
        for part in raw.split(":"):
            if part.startswith("$pdf$"):
                raw = part
                break

    if not raw.startswith("$pdf$"):
        die(f"Unexpected hash format: {raw[:120]}")

    HASH_FILE.write_text(raw, encoding="utf-8")
    ok(f"Hash extracted  →  {HASH_FILE}")
    info(f"Hash preview    :  {raw[:72]}…")
    return raw


# ──────────────────────────────────────────────────────────────
#  STAGE 4 — PDF VERSION → HASHCAT MODE
# ──────────────────────────────────────────────────────────────
def detect_hash_mode(hash_str: str) -> int:
    """
    Map $pdf$<version>*<revision>*… to the correct Hashcat mode.
      10400  PDF 1.1–1.3   MD5 + RC4-40
      10500  PDF 1.4–1.6   MD5 + RC4-128
      10600  PDF 1.7 L3    SHA-256 + AES-256
      10700  PDF 1.7 L8+   SHA-256/512 + AES-256
    """
    section("STAGE 4 · HASH MODE DETECTION")
    m = re.match(r"\$pdf\$(\d+)\*(\d+)\*", hash_str)
    if not m:
        warn("Could not parse PDF version — defaulting to mode 10500 (PDF 1.4–1.6)")
        return 10500

    ver, rev = int(m.group(1)), int(m.group(2))
    if ver <= 2:
        mode, label = 10400, "PDF 1.1–1.3 (RC4-40)"
    elif ver == 3 or (ver == 4 and rev < 4):
        mode, label = 10500, "PDF 1.4–1.6 (RC4-128)"
    elif ver == 4 and rev == 4:
        mode, label = 10600, "PDF 1.7 L3 (AES-256)"
    else:
        mode, label = 10700, "PDF 1.7 L8+ (AES-256)"

    ok(f"PDF version : {label}")
    ok(f"Hashcat mode: {mode}")
    return mode


# ──────────────────────────────────────────────────────────────
#  STAGE 5 — DDMM WORDLIST
# ──────────────────────────────────────────────────────────────
def build_ddmm_wordlist() -> int:
    """
    Generate all valid DDMM date strings.
    Returns the count of entries written.
    """
    section("STAGE 5 · DDMM WORDLIST GENERATION")

    dates = []
    for month in range(1, 13):
        for day in range(1, DAYS_IN_MONTH[month] + 1):
            dates.append(f"{day:02d}{month:02d}")

    # Prioritise dates where day ≤ 12 (likely to be picked by humans)
    priority = [d for d in dates if int(d[:2]) <= 12]
    rest     = [d for d in dates if int(d[:2]) > 12]
    ordered  = priority + rest

    DATES_FILE.write_text("\n".join(ordered) + "\n", encoding="utf-8")
    ok(f"Generated {len(ordered)} valid DDMM entries  →  {DATES_FILE}")
    info(f"Sample : {ordered[:5]}  …  {ordered[-3:]}")
    return len(ordered)


# ──────────────────────────────────────────────────────────────
#  STAGE 6 — HASHCAT ATTACK
# ──────────────────────────────────────────────────────────────
def build_command(hash_mode: int, gpu: bool) -> list:
    """
    Hybrid attack (mode 7):  mask × wordlist
      hashcat -a 7 <hash> <mask> <wordlist>

      -a 7 = Hybrid Mask + Wordlist:
        hashcat prepends the mask candidates to each wordlist word.
        mask     = ?u?u?u?u  → 26^4 uppercase prefixes  (LEFT side)
        wordlist = dates.txt → 366 DDMM suffixes        (RIGHT side)
        result   = AAAA + DDMM  ✓

      (Do NOT use -a 6: that mode puts the mask on the RIGHT and
       treats the first non-option argument as a wordlist FILE —
       so '?u?u?u?u' gets interpreted as a filename → Invalid argument)

    Returns a *list* of arguments so subprocess never passes them
    through a shell — this avoids Windows treating '?' as a wildcard.
    """
    # Delete stale pot so we always get a fresh result
    if POT_FILE.exists():
        try:
            POT_FILE.unlink()
        except Exception:
            pass

    args = [
        HASHCAT_BIN,
        "-m", str(hash_mode),        # hash type
        "-a", "7",                    # attack mode 7: mask (left) + wordlist (right)
        "-D", "2" if gpu else "1",   # 2=GPU, 1=CPU
        "-w", "3" if gpu else "2",   # workload profile
        "--status",                   # live status lines
        "--status-timer", "3",        # update every 3 s
        f"--potfile-path={POT_FILE}",
        "--outfile-format=2",         # plain password only
        str(HASH_FILE),
        "?u?u?u?u",                   # mask: 4 uppercase letters (NOT shell-expanded)
        str(DATES_FILE),              # wordlist: DDMM suffixes
    ]
    return args


def run_attack(hash_mode: int, num_dates: int, gpu: bool) -> Tuple[Optional[str], float]:
    """Execute hashcat and stream its output live. Return (password, elapsed)."""
    section("STAGE 6 · HASHCAT ATTACK")

    total = (26 ** 4) * num_dates
    device_label = "GPU (CUDA/OpenCL)" if gpu else "CPU (multi-thread)"

    info(f"Hash mode  : {hash_mode}")
    info(f"Attack     : Mode 7 — Mask(?u?u?u?u) prepended to DDMM wordlist")
    info(f"Device     : {device_label}")
    info(f"Total      : {total:,} password candidates")
    info(f"Est. speed : {'100M+/s (GPU)' if gpu else '~500K/s (CPU)'}")
    info(f"Est. time  : {'<3 min (GPU)' if gpu else '~6 hours (CPU)'}")

    # build_command returns a list — no shell involved, so '?' is never expanded
    args = build_command(hash_mode, gpu)
    info(f"\n  Command: {' '.join(str(a) for a in args)}\n")

    print("─"*60)
    print("  HASHCAT LIVE OUTPUT:")
    print("─"*60)

    start = time.time()
    found: Optional[str] = None

    try:
        proc = subprocess.Popen(
            args,                       # list of args → no shell wildcard expansion
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip()
            if not line:
                continue
            print(f"  {line}")
            # Detect a cracked line: 8 chars, first 4 uppercase alpha, last 4 digits
            stripped = line.strip()
            if (
                len(stripped) == 8
                and stripped[:4].isupper()
                and stripped[:4].isalpha()
                and stripped[4:].isdigit()
            ):
                found = stripped

        proc.wait()

    except KeyboardInterrupt:
        try:
            proc.terminate()
        except Exception:
            pass
        warn("Attack interrupted by user.")
        return None, time.time() - start

    elapsed = time.time() - start

    # Always check the pot-file — it is the most reliable source
    found = _read_pot(found)

    return found, elapsed


def _read_pot(fallback: Optional[str]) -> Optional[str]:
    """Read the cracked password from the hashcat pot file."""
    if not POT_FILE.exists():
        return fallback
    try:
        content = POT_FILE.read_text(encoding="utf-8", errors="replace").strip()
        if not content:
            return fallback
        # Each line: <hash>:<password>
        for line in content.splitlines():
            if ":" in line:
                pw = line.rsplit(":", 1)[-1].strip()
                if pw:
                    return pw
    except Exception:
        pass
    return fallback


# ──────────────────────────────────────────────────────────────
#  STAGE 7 — UNLOCK & SAVE PDF
# ──────────────────────────────────────────────────────────────
def unlock_and_save(pdf_path: Path, password: str) -> bool:
    """Open the encrypted PDF with pikepdf and save an unlocked copy."""
    section("STAGE 7 · UNLOCKING PDF")
    try:
        import pikepdf
    except ImportError:
        warn("pikepdf not installed — skipping unlock step.")
        info("Install with:  pip install pikepdf")
        return False

    OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_FOLDER / pdf_path.name
    try:
        with pikepdf.open(pdf_path, password=password) as pdf:
            pdf.save(out_path)
        ok(f"Unlocked PDF saved  →  {out_path}")
        return True
    except Exception as ex:
        warn(f"Could not save unlocked PDF: {ex}")
        return False


# ──────────────────────────────────────────────────────────────
#  HELPER: shell runner
# ──────────────────────────────────────────────────────────────
def run_cmd(cmd: str) -> Tuple[int, str, str]:
    try:
        r = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except Exception as ex:
        return 1, "", str(ex)


# ──────────────────────────────────────────────────────────────
#  HELPERS: formatting
# ──────────────────────────────────────────────────────────────
def fmt_time(s: float) -> str:
    if s < 60:
        return f"{s:.1f} s"
    if s < 3600:
        return f"{s/60:.1f} min"
    return f"{s/3600:.2f} h"

def fmt_speed(combos: int, s: float) -> str:
    if s <= 0:
        return "∞"
    r = combos / s
    if r >= 1_000_000:
        return f"{r/1_000_000:.1f} M/s"
    if r >= 1_000:
        return f"{r/1_000:.1f} K/s"
    return f"{r:.0f}/s"


# ──────────────────────────────────────────────────────────────
#  MAIN
# ──────────────────────────────────────────────────────────────
def main() -> int:
    # ── Fix Windows UTF-8 output ──
    try:
        import io as _io
        sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

    banner()

    # ── Parse --hashcat override ──
    global HASHCAT_BIN
    hc_env = os.environ.get("HASHCAT_BIN", "")
    if hc_env:
        HASHCAT_BIN = hc_env

    if "--hashcat" in sys.argv:
        try:
            idx = sys.argv.index("--hashcat")
            HASHCAT_BIN = sys.argv[idx + 1]
            del sys.argv[idx: idx + 2]
        except (IndexError, ValueError):
            die("Usage: python crack_pdf.py <file.pdf> [--hashcat <path>]")

    # ── Locate PDF ──
    if len(sys.argv) > 1:
        pdf_path = Path(sys.argv[1])
    else:
        pdfs = list(DROP_FOLDER.glob("*.pdf")) if DROP_FOLDER.exists() else []
        if not pdfs:
            pdfs = list(SCRIPT_DIR.glob("*.pdf"))
        if not pdfs:
            die(
                "No PDF file found.\n\n"
                f"  Usage: python crack_pdf.py <protected.pdf>\n"
                f"  Or place your PDF in: {DROP_FOLDER}\n"
            )
        pdf_path = pdfs[0]
        info(f"Auto-detected PDF: {pdf_path.name}")

    if not pdf_path.exists():
        die(f"File not found: {pdf_path}")

    info(f"Target: {pdf_path.resolve()}\n")

    # ── Pipeline ──
    gpu          = detect_gpu()
    verify_hashcat()
    hash_str     = extract_hash(pdf_path)
    hash_mode    = detect_hash_mode(hash_str)
    num_dates    = build_ddmm_wordlist()
    password, elapsed = run_attack(hash_mode, num_dates, gpu)

    # ── Results ──
    total_combos = (26 ** 4) * num_dates

    print("\n" + "═"*60)
    if password:
        dd  = password[4:6]
        mm  = password[6:8]
        print("  ✅  PASSWORD CRACKED!")
        print()
        print(f"      ┌─────────────────────────────────┐")
        print(f"      │  🔑  Password  :  {password:<15}  │")
        print(f"      │      Prefix    :  {password[:4]:<15}  │")
        print(f"      │      Day  (DD) :  {dd:<15}  │")
        print(f"      │      Month(MM) :  {mm:<15}  │")
        print(f"      │      Date      :  {dd}/{mm}            │")
        print(f"      └─────────────────────────────────┘")
        print()
        print(f"      Tried   : {total_combos:,} combinations")
        print(f"      Time    : {fmt_time(elapsed)}")
        print(f"      Speed   : {fmt_speed(total_combos, elapsed)}")
        print(f"      Device  : {'GPU' if gpu else 'CPU'}")
        print("═"*60)

        unlock_and_save(pdf_path, password)
        return 0

    else:
        print("  ❌  PASSWORD NOT FOUND")
        print()
        print(f"      Searched : {total_combos:,} combinations")
        print(f"      Time     : {fmt_time(elapsed)}")
        print(f"      Device   : {'GPU' if gpu else 'CPU'}")
        print()
        print("  Possible reasons:")
        print("    • Hashcat returned an error — check the output above")
        print("    • PDF uses an unsupported encryption algorithm")
        print("    • Password format differs from [A-Z]{4}+DDMM")
        print("═"*60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
