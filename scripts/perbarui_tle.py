"""
perbarui_tle.py - Mengunduh TLE terbaru dari CelesTrak dan menyimpannya ke data/tle_cadangan.txt.

Dijalankan setiap hari oleh GitHub Actions (.github/workflows/perbarui-tle.yml), sehingga aplikasi
selalu punya snapshot yang paling lama berumur sehari, meskipun server tempatnya berjalan tidak bisa
menjangkau CelesTrak. Bisa juga dijalankan manual:

    python scripts/perbarui_tle.py
"""

from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

URL = "https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle"
TUJUAN = Path(__file__).resolve().parent.parent / "data" / "tle_cadangan.txt"
MINIMAL_SATELIT = 5000   # jaga-jaga: jangan menimpa cadangan dengan respons yang terpotong


def main() -> int:
    for percobaan in range(1, 4):
        try:
            r = requests.get(URL, timeout=90)
            r.raise_for_status()
            teks = r.text.replace("\r\n", "\n")
            jumlah = teks.count("\n1 ") + teks.startswith("1 ")
            if jumlah < MINIMAL_SATELIT:
                raise ValueError(f"hanya {jumlah} satelit, kemungkinan respons tidak lengkap")
            waktu = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
            kepala = f"# CelesTrak GROUP=active, diunduh {waktu}. Cadangan bila server tidak terjangkau.\n"
            TUJUAN.write_text(kepala + teks.strip() + "\n", encoding="utf-8")
            print(f"{jumlah} satelit disimpan ke {TUJUAN}")
            return 0
        except (requests.RequestException, ValueError) as e:
            print(f"percobaan {percobaan} gagal: {e}")
            time.sleep(20 * percobaan)
    return 1


if __name__ == "__main__":
    sys.exit(main())
