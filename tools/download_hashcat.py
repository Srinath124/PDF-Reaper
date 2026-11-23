import re
import sys
import os
import urllib.request
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parent.parent
OUTDIR = ROOT / "hashcat_download"
EXTRACT_DIR = ROOT / "hashcat"
INDEX_URL = "https://hashcat.net/files/"

print('Fetching index...')
html = urllib.request.urlopen(INDEX_URL, timeout=30).read().decode('utf-8', errors='ignore')
# find first zip or 7z
m = re.search(r'href\s*=\s*"(?P<u>/files/hashcat-[^"\s]+\.(zip|7z))"', html)
if not m:
    print('No release link found on index page')
    sys.exit(2)

href = m.group('u')
url = 'https://hashcat.net' + href
print('Found:', url)
OUTDIR.mkdir(parents=True, exist_ok=True)
EXTRACT_DIR.mkdir(parents=True, exist_ok=True)
filename = url.split('/')[-1]
dest = OUTDIR / filename

print('Downloading to', dest)
try:
    urllib.request.urlretrieve(url, dest)
except Exception as e:
    print('Download failed:', e)
    sys.exit(3)

if filename.lower().endswith('.zip'):
    print('Extracting zip...')
    try:
        with ZipFile(dest, 'r') as z:
            for member in z.namelist():
                target = (EXTRACT_DIR / member).resolve()
                if not str(target).startswith(str(EXTRACT_DIR.resolve())):
                    raise ValueError(f"Unsafe archive member: {member}")
            z.extractall(EXTRACT_DIR)
        print('Extraction complete to', EXTRACT_DIR)
        # Try to find hashcat.exe or hashcat binary
        exe = None
        for p in EXTRACT_DIR.rglob('hashcat*.exe'):
            exe = p
            break
        if not exe:
            for p in EXTRACT_DIR.rglob('hashcat'):  # unix binary
                if p.is_file() and os.access(str(p), os.X_OK):
                    exe = p
                    break
        if exe:
            print('Found binary at', exe)
            print('EXPORT_PATH=' + str(exe))
            sys.exit(0)
        else:
            print('Could not find hashcat executable inside archive')
            sys.exit(4)
    except Exception as e:
        print('Extraction error:', e)
        sys.exit(5)
else:
    print('Downloaded archive is not a zip. Please extract .7z manually if needed:', dest)
    sys.exit(6)
