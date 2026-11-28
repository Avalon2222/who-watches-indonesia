"""
muat_data.py - Mengambil TLE (live dari CelesTrak, atau cadangan di data/), membaca katalog GCAT,
lalu menggabungkan keduanya menjadi satu DataFrame satelit yang siap dihitung.
Tidak ada Streamlit di sini; caching dilakukan di app.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from src import klasifikasi, orbit

FOLDER_DATA = Path(__file__).resolve().parent.parent / "data"
URL_TLE_AKTIF = "https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle"
URL_TLE_SNAPSHOT = "https://raw.githubusercontent.com/Avalon2222/who-watches-indonesia/main/data/tle_cadangan.txt"
FILE_TLE_CADANGAN = FOLDER_DATA / "tle_cadangan.txt"
FILE_KATALOG = FOLDER_DATA / "katalog_satelit.csv"
FILE_NEGARA = FOLDER_DATA / "kode_negara.csv"
FILE_CATATAN_ID = FOLDER_DATA / "satelit_indonesia.csv"


@dataclass
class HasilTLE:
    teks: str
    sumber: str            # "CelesTrak (live)" atau "cadangan di repo"
    diambil_pada: datetime  # UTC
    pesan: str = ""


def _kolom_teks(kolom: pd.Series) -> bool:
    """True untuk kolom teks. Di pandas 3 teks dibaca sebagai dtype `str`, bukan `object` lagi."""
    return kolom.dtype == object or isinstance(kolom.dtype, pd.StringDtype)


def ambil_tle(timeout: int = 12) -> HasilTLE:
    """
    Ambil TLE semua satelit aktif, dari sumber paling segar ke paling aman:

      1. CelesTrak langsung (live, beberapa jam sekali diperbarui).
      2. Snapshot harian di GitHub repo ini (diperbarui GitHub Actions setiap hari,
         lihat .github/workflows/perbarui-tle.yml). Berguna bila server tempat aplikasi
         berjalan tidak bisa menjangkau CelesTrak.
      3. File data/tle_cadangan.txt yang ikut ter-deploy bersama aplikasi.

    Batas waktu sengaja pendek supaya halaman tidak lama menunggu sumber yang macet.
    """
    galat = ""
    try:
        r = requests.get(URL_TLE_AKTIF, timeout=timeout)
        r.raise_for_status()
        if r.text.count("\n1 ") > 100:
            return HasilTLE(r.text, "CelesTrak (live)", datetime.now(timezone.utc))
        galat = "respons CelesTrak tidak berisi TLE"
    except requests.RequestException as e:
        galat = type(e).__name__

    try:
        r = requests.get(URL_TLE_SNAPSHOT, timeout=timeout)
        r.raise_for_status()
        if r.text.count("\n1 ") > 100:
            return HasilTLE(r.text, "snapshot harian", tanggal_dari_header(r.text),
                            f"CelesTrak tidak terjangkau dari server ({galat}); memakai snapshot harian.")
    except requests.RequestException:
        pass

    return HasilTLE(baca_tle_cadangan(), "cadangan di repo", tanggal_tle_cadangan(),
                    f"CelesTrak tidak terjangkau dari server ({galat}); memakai cadangan di repo.")


def baca_tle_cadangan() -> str:
    return FILE_TLE_CADANGAN.read_text(encoding="utf-8")


def tanggal_dari_header(teks: str) -> datetime:
    """Tanggal snapshot ditulis di baris pertama: '# CelesTrak GROUP=active, diunduh 2026-11-02T17:14Z. ...'."""
    baris1 = teks.split("\n", 1)[0]
    # Pemisah tanggal dan jam bisa "T" (ISO) atau spasi.
    m = re.search(r"(\d{4}-\d{2}-\d{2})(?:[T ](\d{2}:\d{2}))?", baris1)
    if not m:
        return datetime(2000, 1, 1, tzinfo=timezone.utc)
    jam = m.group(2) or "00:00"
    # Header yang rusak (bulan 13, jam 25) jangan sampai membuat aplikasi gagal dimuat:
    # coba tanggal + jam, lalu tanggal saja, lalu tanggal cadangan.
    for teks, pola in ((f"{m.group(1)} {jam}", "%Y-%m-%d %H:%M"), (m.group(1), "%Y-%m-%d")):
        try:
            return datetime.strptime(teks, pola).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return datetime(2000, 1, 1, tzinfo=timezone.utc)


def _baris_pertama(path: Path) -> str:
    with path.open(encoding="utf-8") as f:
        return f.readline()


def tanggal_tle_cadangan() -> datetime:
    return tanggal_dari_header(_baris_pertama(FILE_TLE_CADANGAN))


def muat_katalog() -> pd.DataFrame:
    df = pd.read_csv(FILE_KATALOG, comment="#", dtype={"negara_kode": str, "kelas": str, "kategori_gcat": str})
    for kolom in ["nama_gcat", "negara_kode", "pemilik", "kelas", "kategori_gcat", "program", "orbit_gcat", "tanggal_luncur"]:
        df[kolom] = df[kolom].fillna("-").astype(str)
    return df


def tanggal_katalog() -> str:
    m = re.search(r"Dibangun (\d{4}-\d{2}-\d{2})", _baris_pertama(FILE_KATALOG))
    return m.group(1) if m else "?"


def muat_kode_negara() -> pd.DataFrame:
    return pd.read_csv(FILE_NEGARA, dtype=str).fillna("")


def muat_catatan_indonesia() -> pd.DataFrame:
    df = pd.read_csv(FILE_CATATAN_ID, dtype={"norad": "Int64"})
    for kolom in df.columns:
        if _kolom_teks(df[kolom]):
            df[kolom] = df[kolom].fillna("")
    return df


def gabungkan(df_tle: pd.DataFrame, katalog: pd.DataFrame, negara: pd.DataFrame) -> pd.DataFrame:
    """
    TLE + katalog + nama negara -> satu tabel satelit dengan kolom:
    norad, nama, line1, line2, epoch, inklinasi_deg, mean_motion, jenis_orbit, periode_menit,
    negara_kode, negara, bendera, pemilik, kelas, kategori_gcat, program, tanggal_luncur, terkatalog,
    operator, misi, pengintai, kelompok.
    """
    # Katalog dengan nomor NORAD ganda akan menggandakan satelit saat merge; pakai baris terakhir.
    katalog = katalog.drop_duplicates("norad", keep="last")
    # Nomor NORAD katalog yang terbaca sebagai teks atau pecahan ("25544", 25544.0) tidak akan bertemu
    # dengan nomor bulat dari TLE; samakan dulu, dan baris tanpa nomor yang sah dibuang.
    katalog = katalog.assign(norad=pd.to_numeric(katalog["norad"], errors="coerce")).dropna(subset=["norad"])
    katalog["norad"] = katalog["norad"].astype("int64")
    df = df_tle.merge(katalog, on="norad", how="left")
    df["terkatalog"] = df["negara_kode"].notna()
    df["sumber_klasifikasi"] = df["terkatalog"].map({True: "GCAT", False: "-"})
    for kolom in ["nama_gcat", "negara_kode", "pemilik", "kelas", "kategori_gcat", "program", "orbit_gcat", "tanggal_luncur"]:
        df[kolom] = df[kolom].fillna("-").astype(str)
    # Kode negara " id" atau "us" dari input manual tetap dicocokkan ke tabel negara (yang huruf besar),
    # sama seperti tentukan_kelompok yang sudah toleran terhadap huruf dan spasi.
    df["negara_kode"] = df["negara_kode"].str.strip().str.upper().replace("", "-")
    df = klasifikasi.klasifikasikan(df)

    # Kunci tabel negara dirapikan dengan cara yang sama seperti negara_kode di atas; " id" atau
    # "us" hasil suntingan manual di kode_negara.csv dulu membuat negaranya tampil sebagai kode saja.
    kode = negara["kode_gcat"].astype(str).str.strip().str.upper()
    # Nama atau bendera yang kosong di kode_negara.csv (sel kosong jadi "") jangan ikut dipetakan;
    # dulu negaranya tampil sebagai teks kosong, padahal kodenya masih bisa ditampilkan.
    nama_negara = negara["negara"].astype(str).str.strip()
    bendera = negara["bendera"].astype(str).str.strip()
    peta_nama = {k: v for k, v in zip(kode, nama_negara) if v}
    peta_bendera = {k: v for k, v in zip(kode, bendera) if v}
    df["negara"] = df["negara_kode"].map(peta_nama).fillna(df["negara_kode"].where(df["negara_kode"] != "-", "Belum terkatalog"))
    df["bendera"] = df["negara_kode"].map(peta_bendera).fillna("🛰️")
    df["jenis_orbit"] = [orbit.jenis_orbit(mm, inc) for mm, inc in zip(df["mean_motion"], df["inklinasi_deg"])]
    df["periode_menit"] = df["mean_motion"].map(orbit.periode_menit)
    return df


def muat_semua(tle: HasilTLE | None = None) -> tuple[pd.DataFrame, HasilTLE]:
    """Jalan pintas: ambil TLE (live/cadangan), baca katalog, gabungkan."""
    tle = tle or ambil_tle()
    df = gabungkan(orbit.parse_tle(tle.teks), muat_katalog(), muat_kode_negara())
    return df, tle
