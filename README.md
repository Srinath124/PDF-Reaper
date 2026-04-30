# 🔐 PDF-Reaper (GPU-Accelerated PDF Password Recovery)

A high-performance, cross-platform PDF password cracking tool built in Python. This tool is designed to recover lost passwords for protected PDF documents using GPU acceleration via **Hashcat**. 

## 🎯 Target Password Pattern
This tool specifically targets an **8-character password pattern**:
- **First 4 characters**: Uppercase alphabetical letters (`[A-Z]{4}`)
- **Last 4 characters**: A valid date and month (`DDMM`)
- **Example**: `TGLA1209`

### 🏢 Real-World Use Cases
This specific `[A-Z]{4} + DDMM` pattern is very commonly used for automated document protection by institutions:
- **Bank e-Statements** (e.g., ICICI, HDFC, and other regional banks often use first 4 letters of name + DDMM of birth)
- **Salary Slips / Payslips** from corporate payroll systems
- **Official Government Documents** (Variations of e-Aadhar or PAN documents)
- **Insurance Policy Documents**

## 🏗️ Architecture & How It Works

The script operates through a robust automated pipeline:
1. **GPU Detection**: Scans for an available NVIDIA GPU via `nvidia-smi` to utilize CUDA acceleration. Falls back to multi-threaded CPU if no GPU is found.
2. **Hashcat Verification**: Ensures `hashcat` is installed and accessible.
3. **Hash Extraction**: Automatically downloads `pdf2john.py` (if not cached) to extract the `$pdf$...` hash from your protected PDF.
4. **Hash Mode Detection**: Parses the PDF encryption version (RC4-40, RC4-128, AES-256) to determine the exact Hashcat mode (10400, 10500, 10600, or 10700).
5. **Wordlist Generation**: Generates `dates.txt` containing all 366 possible `DDMM` combinations (including leap years).
6. **Hybrid Attack Execution**: Launches Hashcat using **Attack Mode 7**. It applies a mask (`?u?u?u?u`) to the left of the `DDMM` wordlist. The GPU blasts through `26^4 × 366 ≈ 167.2 million` combinations.
7. **Unlock & Save**: Uses `pikepdf` to decrypt the PDF with the cracked password and saves an unlocked copy in the `unlocked/` directory.

## ⚡ Performance
- **Keyspace**: ~167 million combinations
- **GPU (e.g., RTX 3050)**: ~20+ Million H/s ➔ **Cracks in under 10 seconds**
- **CPU Fallback**: ~500k H/s ➔ Cracks in ~5-6 minutes

---

## 📁 Folder Structure

```text
protected file encrypter/
├── crack_pdf.py         ← Main execution script
├── drop_file_here/      ← 👉 Place your protected PDF here (auto-detected)
├── unlocked/            ← Unlocked PDF appears here after success
└── hashcat.pot          ← (Auto-generated) Cracked hashes cache
```

*(Note: Older scripts like `bruteforce.py` and `gpu_cpu_pipeline.py` are obsolete and should be deleted).*

---

## 🚀 Requirements & Installation

1. **Python 3.8+**
2. **Hashcat**: Must be installed and added to your system PATH.
   - *Windows*: `choco install hashcat` or download from [hashcat.net](https://hashcat.net/hashcat/)
   - *Linux*: `sudo apt install hashcat`
   - *macOS*: `brew install hashcat`
3. **Python Packages**:
   ```bash
   pip install pikepdf
   ```

## 🛠️ Usage

1. **Place your protected `.pdf` file** inside the `drop_file_here/` folder.
2. Open a terminal in this directory.
3. Run the script:
   ```bash
   python crack_pdf.py
   ```
4. **Custom Hashcat Path** (If not in PATH):
   ```bash
   python crack_pdf.py --hashcat "C:\path\to\hashcat.exe"
   ```
5. The script will output the recovered password and save the decrypted file to `unlocked/`.
