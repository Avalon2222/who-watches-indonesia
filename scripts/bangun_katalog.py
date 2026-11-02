"""
bangun_katalog.py - Membangun data/katalog_satelit.csv dari GCAT (Jonathan McDowell).

GCAT (General Catalog of Artificial Space Objects) adalah katalog publik yang mencatat setiap
objek buatan di orbit: nama, negara, pemilik, kelas operator (sipil / bisnis / militer / amatir),
dan kategori misi (komunikasi, pencitraan, SIGINT, navigasi, dan seterusnya). Skrip ini menggabungkan
dua tabel GCAT, menyaring hanya payload (satelit, bukan roket atau puing), lalu
menyimpannya sebagai CSV ringkas yang dibaca aplikasi.

Jalankan sesekali (misalnya sebulan sekali) agar satelit yang baru diluncurkan ikut dikenali:

    python scripts/bangun_katalog.py                 # unduh dari planet4589.org
    python scripts/bangun_katalog.py --dari folder/  # pakai satcat.tsv + psatcat.tsv yang sudah diunduh

Sumber: https://planet4589.org/space/gcat/ (lisensi CC BY 4.0).
"""

from __future__ import annotations

import argparse
import io
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import requests

URL_SATCAT = "https://planet4589.org/space/gcat/tsv/cat/satcat.tsv"
URL_PSATCAT = "https://planet4589.org/space/gcat/tsv/cat/psatcat.tsv"
FOLDER_DATA = Path(__file__).resolve().parent.parent / "data"
FILE_KELUARAN = FOLDER_DATA / "katalog_satelit.csv"

KOLOM_KELUARAN = [
    "norad", "nama_gcat", "negara_kode", "pemilik", "kelas", "kategori_gcat",
    "program", "orbit_gcat", "tanggal_luncur", "massa_kg",
]


def _baca_tsv(sumber: str | bytes) -> pd.DataFrame:
    """Baca TSV GCAT. Baris kedua berisi tanggal pembaruan, bukan data, sehingga dilewati."""
    buf = io.BytesIO(sumber) if isinstance(sumber, bytes) else sumber
    df = pd.read_csv(buf, sep="\t", dtype=str, keep_default_na=False, skiprows=[1])
    df.columns = [c.lstrip("#") for c in df.columns]
    for kolom in df.columns:
        df[kolom] = df[kolom].str.strip()
    return df


def _unduh(url: str) -> bytes:
    print(f"mengunduh {url} ...")
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    return r.content


def gabungkan(satcat: pd.DataFrame, psatcat: pd.DataFrame) -> pd.DataFrame:
    """Gabungkan satcat (objek fisik) dan psatcat (payload) menjadi satu tabel ringkas."""
    payload = satcat[
        satcat["Type"].str.startswith("P")             # P = payload (satelit), bukan R (roket) atau D (puing)
        & satcat["Satcat"].str.match(r"^\d+$")         # punya nomor NORAD
    ].copy()
    # Semua payload disimpan, termasuk yang sudah jatuh: yang menentukan "aktif" adalah daftar TLE
    # CelesTrak, katalog ini hanya memberi keterangan (negara, operator, misi) untuk setiap nomor NORAD.
    misi = psatcat[["JCAT", "Class", "Category", "Program"]]
    df = payload.merge(misi, on="JCAT", how="left")

    keluar = pd.DataFrame({
        "norad": df["Satcat"].astype(int),
        "nama_gcat": df["Name"],
        "negara_kode": df["State"],
        "pemilik": df["Owner"],
        "kelas": df["Class"].fillna("-").replace("", "-"),
        "kategori_gcat": df["Category"].fillna("-").replace("", "-"),
        "program": df["Program"].fillna("-"),
        "orbit_gcat": df["OpOrbit"],
        "tanggal_luncur": pd.to_datetime(df["LDate"].str.slice(0, 11), format="%Y %b %d", errors="coerce").dt.strftime("%Y-%m-%d"),
        "massa_kg": pd.to_numeric(df["Mass"], errors="coerce"),
    })
    keluar = keluar.sort_values("norad").drop_duplicates("norad")
    return keluar[KOLOM_KELUARAN]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dari", help="folder berisi satcat.tsv dan psatcat.tsv yang sudah diunduh")
    ap.add_argument("--keluaran", default=str(FILE_KELUARAN))
    args = ap.parse_args(argv)

    if args.dari:
        folder = Path(args.dari)
        satcat = _baca_tsv(str(folder / "satcat.tsv"))
        psatcat = _baca_tsv(str(folder / "psatcat.tsv"))
    else:
        satcat = _baca_tsv(_unduh(URL_SATCAT))
        psatcat = _baca_tsv(_unduh(URL_PSATCAT))

    katalog = gabungkan(satcat, psatcat)
    tujuan = Path(args.keluaran)
    tujuan.parent.mkdir(parents=True, exist_ok=True)
    with open(tujuan, "w", encoding="utf-8", newline="") as f:
        f.write(f"# Sumber: GCAT (planet4589.org/space/gcat), CC BY 4.0. Dibangun {date.today():%Y-%m-%d}.\n")
        katalog.to_csv(f, index=False)
    print(f"{len(katalog)} payload disimpan ke {tujuan}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
