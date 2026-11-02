"""
klasifikasi.py - Menerjemahkan kode GCAT menjadi label yang dipakai aplikasi.

GCAT memberi dua kode untuk setiap payload:
  Class    : siapa operatornya  -> A amatir/akademik, B bisnis, C pemerintah sipil, D militer
  Category : untuk apa satelitnya -> COM komunikasi, IMG pencitraan, IMG-R pencitraan radar,
             SIG intai sinyal, EW peringatan dini, NAV navigasi, MET cuaca, SCI sains, TECH uji coba, ...

Dari dua kode itu aplikasi membentuk:
  operator  : label operator dalam bahasa Indonesia
  misi      : label misi dalam bahasa Indonesia
  pengintai : True bila misinya "melihat atau mendengar" permukaan Bumi (IMG, IMG-R, SIG, EW)
  kelompok  : 4 kelompok warna di peta -> Indonesia / Militer asing / Pengintai sipil & komersial asing / Satelit asing lainnya
"""

from __future__ import annotations

import re

import pandas as pd

OPERATOR = {
    "A": "Akademik & amatir",
    "B": "Komersial",
    "C": "Pemerintah sipil",
    "D": "Militer",
}

# kode kategori GCAT (bagian sebelum tanda / ? *) -> label misi
MISI = {
    "IMG": "Pencitraan optik",
    "IMG-R": "Pencitraan radar (SAR)",
    "SIG": "Intai sinyal (SIGINT)",
    "EW": "Peringatan dini (early warning)",
    "COM": "Komunikasi",
    "NAV": "Navigasi",
    "MET": "Cuaca",
    "MET-RO": "Cuaca (radio okultasi)",
    "EOSCI": "Observasi Bumi (sains)",
    "SCI": "Sains",
    "AST": "Astronomi",
    "GEOD": "Geodesi",
    "TECH": "Teknologi / uji coba",
    "CAL": "Kalibrasi",
    "SS": "Stasiun antariksa",
    "PLAN": "Antarplanet",
    "BIO": "Biologi",
    "MGRAV": "Mikrogravitasi",
    "WEAPON": "Senjata / uji senjata",
}
MISI_PENGINTAI = {"Pencitraan optik", "Pencitraan radar (SAR)", "Intai sinyal (SIGINT)", "Peringatan dini (early warning)"}

KELOMPOK = ["Indonesia", "Militer asing", "Pengintai sipil & komersial asing", "Satelit asing lainnya", "Belum terkatalog"]
WARNA_KELOMPOK = {
    "Indonesia": "#ff3b3b",
    "Militer asing": "#ffb000",
    "Pengintai sipil & komersial asing": "#4dd0e1",
    "Satelit asing lainnya": "#8a97ab",
    "Belum terkatalog": "#5a6170",
}

# Tebakan dari nama untuk satelit yang belum masuk GCAT (baru diluncurkan). Sengaja singkat dan
# hanya untuk keluarga yang mudah dikenali; selebihnya diberi label "Belum terkatalog".
POLA_NAMA = [
    (r"^STARLINK", "US", "B", "COM"),
    (r"^ONEWEB", "UK", "B", "COM"),
    (r"^KUIPER", "US", "B", "COM"),
    (r"^QIANFAN", "CN", "B", "COM"),
    (r"^HULIANWANG|^GUOWANG", "CN", "C", "COM"),
    (r"^FLOCK|^SKYSAT|^PELICAN", "US", "B", "IMG"),
    (r"^JILIN", "CN", "B", "IMG"),
    (r"^YAOGAN", "CN", "D", "IMG"),
    (r"^ICEYE", "FI", "B", "IMG-R"),
    (r"^UMBRA|^CAPELLA", "US", "B", "IMG-R"),
    (r"^LEMUR", "US", "B", "MET-RO"),
    (r"^COSMOS", "RU", "D", "-"),
    (r"^USA \d", "US", "D", "-"),
]


def kode_dasar(kategori_gcat: str) -> str:
    """'IMG-R?' -> 'IMG-R'; 'COM/MET-RO' -> 'COM'; 'SIG*' -> 'SIG'."""
    k = str(kategori_gcat).strip()
    k = re.split(r"[/?*]", k)[0]
    return k or "-"


def label_operator(kelas: str) -> str:
    k = str(kelas).strip()
    if "D" in k:                # D, BD, CD -> dioperasikan (sebagian) oleh militer
        return OPERATOR["D"]
    return OPERATOR.get(k[:1], "Tidak diketahui")


def label_misi(kategori_gcat: str) -> str:
    return MISI.get(kode_dasar(kategori_gcat), "Lainnya / tidak diketahui")


def tentukan_kelompok(negara_kode: str, operator: str, misi: str, terkatalog: bool = True) -> str:
    if not terkatalog:
        return "Belum terkatalog"
    if negara_kode == "ID":
        return "Indonesia"
    if operator == "Militer":
        return "Militer asing"
    if misi in MISI_PENGINTAI:
        return "Pengintai sipil & komersial asing"
    return "Satelit asing lainnya"


def tebak_dari_nama(nama: str) -> tuple[str, str, str] | None:
    """(negara_kode, kelas, kategori) berdasarkan pola nama, atau None bila tidak dikenali."""
    for pola, negara, kelas, kategori in POLA_NAMA:
        if re.search(pola, nama.upper()):
            return negara, kelas, kategori
    return None


def klasifikasikan(df: pd.DataFrame) -> pd.DataFrame:
    """
    Tambahkan kolom operator, misi, pengintai, kelompok ke DataFrame yang sudah memiliki
    kolom nama, negara_kode, kelas, kategori_gcat, terkatalog.
    """
    df = df.copy()
    # isi yang belum terkatalog dari pola nama (bila dikenali)
    belum = ~df["terkatalog"]
    if belum.any():
        tebakan = df.loc[belum, "nama"].map(tebak_dari_nama)
        dikenali = tebakan.notna()
        idx = tebakan[dikenali].index
        df.loc[idx, "negara_kode"] = [t[0] for t in tebakan[dikenali]]
        df.loc[idx, "kelas"] = [t[1] for t in tebakan[dikenali]]
        df.loc[idx, "kategori_gcat"] = [t[2] for t in tebakan[dikenali]]
        df.loc[idx, "sumber_klasifikasi"] = "pola nama"
        df.loc[idx, "terkatalog"] = True
    df["operator"] = df["kelas"].map(label_operator)
    df["misi"] = df["kategori_gcat"].map(label_misi)
    df["pengintai"] = df["misi"].isin(MISI_PENGINTAI)
    df["kelompok"] = [
        tentukan_kelompok(n, o, m, t)
        for n, o, m, t in zip(df["negara_kode"], df["operator"], df["misi"], df["terkatalog"])
    ]
    return df
