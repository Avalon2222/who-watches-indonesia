"""
orbit.py - Dari TLE ke posisi di atas peta.

Rantai perhitungannya:
  TLE (dua baris teks)  --sgp4-->  posisi x,y,z di kerangka TEME (km)
                        --GMST-->  putar ke kerangka Bumi (ECEF)
                        --WGS84--> lintang, bujur, ketinggian

Semua fungsi menerima array numpy supaya ribuan satelit dan ribuan waktu bisa dihitung sekaligus
(perpustakaan sgp4 melakukannya dalam C). Tidak ada Streamlit di sini.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
from sgp4.api import Satrec, SatrecArray, jday

R_BUMI_KM = 6378.137          # jari-jari ekuator WGS84
F_PEPAT = 1 / 298.257223563   # kepepatan Bumi (flattening)
E2 = F_PEPAT * (2 - F_PEPAT)  # eksentrisitas kuadrat
UKURAN_POTONGAN = 400         # satelit per batch saat propagasi panjang, demi hemat memori


# ----------------------------------------------------------------------------
# 1. Membaca TLE
# ----------------------------------------------------------------------------
def parse_tle(teks: str) -> pd.DataFrame:
    """
    Ubah teks TLE tiga baris (nama, baris 1, baris 2) menjadi DataFrame.

    Kolom: norad, nama, line1, line2, epoch (UTC), inklinasi_deg, mean_motion (putaran/hari).
    Baris yang rusak dilewati. Duplikat nomor NORAD diambil yang pertama.
    """
    baris = [b.rstrip() for b in teks.splitlines() if b.strip()]
    rekaman = []
    i = 0
    while i < len(baris) - 1:
        if baris[i].startswith("1 ") and baris[i + 1].startswith("2 "):
            nama = baris[i - 1].strip() if i > 0 and not baris[i - 1][:2] in ("1 ", "2 ") else ""
            l1, l2 = baris[i], baris[i + 1]
            try:
                norad = int(l1[2:7])
                epoch = _epoch_tle(l1)
                inklinasi = float(l2[8:16])
                mean_motion = float(l2[52:63])
            except ValueError:
                i += 2
                continue
            rekaman.append((norad, nama, l1, l2, epoch, inklinasi, mean_motion))
            i += 2
        else:
            i += 1
    df = pd.DataFrame(rekaman, columns=["norad", "nama", "line1", "line2", "epoch", "inklinasi_deg", "mean_motion"])
    return df.drop_duplicates("norad").reset_index(drop=True)


def _epoch_tle(line1: str) -> datetime:
    """Epoch TLE ditulis sebagai YYDDD.FFFFFFFF (tahun 2 digit + hari dalam tahun + pecahan hari)."""
    tahun2 = int(line1[18:20])
    hari = float(line1[20:32])
    tahun = 2000 + tahun2 if tahun2 < 57 else 1900 + tahun2
    return datetime(tahun, 1, 1, tzinfo=timezone.utc) + timedelta(days=hari - 1)


def jenis_orbit(mean_motion: float, inklinasi_deg: float) -> str:
    """
    Tebak jenis orbit dari jumlah putaran per hari.
      ~1 putaran/hari dan inklinasi kecil  -> GEO (geostasioner, diam di atas satu titik)
      ~1 putaran/hari, inklinasi besar      -> GSO miring
      < 1,5 putaran/hari                    -> HEO / MEO tinggi
      1,5 - 5 putaran/hari                  -> MEO (misalnya GPS: 2 putaran/hari)
      > 5 putaran/hari                      -> LEO (orbit rendah, 90-120 menit per putaran)
    """
    if 0.9 <= mean_motion <= 1.1:
        return "GEO" if inklinasi_deg < 10 else "GSO miring"
    if mean_motion < 1.5:
        return "HEO/MEO tinggi"
    if mean_motion < 5:
        return "MEO"
    return "LEO"


def periode_menit(mean_motion: float) -> float:
    """Lama satu putaran orbit dalam menit (1440 menit per hari dibagi jumlah putaran per hari)."""
    return 1440.0 / mean_motion


# ----------------------------------------------------------------------------
# 2. Waktu: datetime -> Julian Date, dan GMST
# ----------------------------------------------------------------------------
def ke_jd(waktu: datetime) -> tuple[float, float]:
    """datetime (UTC) -> (jd, fr) seperti yang diminta sgp4. jd = bagian bulat, fr = pecahan hari."""
    w = pd.Timestamp(waktu)
    w = w.tz_localize(timezone.utc) if w.tzinfo is None else w.tz_convert(timezone.utc)   # naive dianggap UTC
    return jday(w.year, w.month, w.day, w.hour, w.minute, w.second + w.microsecond / 1e6)


def gmst_rad(jd_ut1: np.ndarray) -> np.ndarray:
    """
    Greenwich Mean Sidereal Time (rad) dari Julian Date, rumus IAU 1982 (Vallado, Astrodynamics).
    Nilai ini menyatakan sudut putaran Bumi relatif terhadap bintang; dipakai untuk memutar koordinat
    TEME (tidak ikut berputar) menjadi koordinat yang menempel pada Bumi.
    """
    t = (jd_ut1 - 2451545.0) / 36525.0
    detik = 67310.54841 + (876600.0 * 3600 + 8640184.812866) * t + 0.093104 * t**2 - 6.2e-6 * t**3
    return np.mod(np.deg2rad(detik / 240.0), 2 * np.pi)  # 240 detik waktu = 1 derajat sudut


# ----------------------------------------------------------------------------
# 3. TEME -> lintang, bujur, ketinggian
# ----------------------------------------------------------------------------
def teme_ke_geodetik(r_teme: np.ndarray, jd: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    r_teme: array (..., 3) posisi km di kerangka TEME; jd: Julian Date penuh dengan bentuk (...).
    Mengembalikan lat (deg), lon (deg, -180..180), alt (km) dengan bentuk (...).

    Langkah: putar TEME ke ECEF dengan sudut GMST (polar motion diabaikan, galat < 1 km),
    lalu konversi ECEF ke lintang geodetik WGS84 secara iteratif.
    """
    theta = gmst_rad(jd)
    x, y, z = r_teme[..., 0], r_teme[..., 1], r_teme[..., 2]
    cos_t, sin_t = np.cos(theta), np.sin(theta)
    x_e = cos_t * x + sin_t * y
    y_e = -sin_t * x + cos_t * y
    z_e = z

    lon = np.degrees(np.arctan2(y_e, x_e))
    p = np.hypot(x_e, y_e)
    lat = np.arctan2(z_e, p * (1 - E2))
    for _ in range(4):  # iterasi Bowring sederhana, konvergen dalam 2-3 langkah
        n = R_BUMI_KM / np.sqrt(1 - E2 * np.sin(lat) ** 2)
        alt = p / np.cos(lat) - n
        lat = np.arctan2(z_e, p * (1 - E2 * n / (n + alt)))
    n = R_BUMI_KM / np.sqrt(1 - E2 * np.sin(lat) ** 2)
    alt = p / np.cos(lat) - n
    return np.degrees(lat), lon, alt


# ----------------------------------------------------------------------------
# 4. Propagasi banyak satelit x banyak waktu
# ----------------------------------------------------------------------------
def _satrec_array(df: pd.DataFrame) -> SatrecArray:
    return SatrecArray([Satrec.twoline2rv(l1, l2) for l1, l2 in zip(df["line1"], df["line2"])])


def propagasi(df: pd.DataFrame, waktu: list[datetime] | pd.DatetimeIndex) -> dict[str, np.ndarray]:
    """
    Hitung posisi setiap satelit di df pada setiap waktu.

    Mengembalikan dict array berbentuk (n_satelit, n_waktu): lat, lon, alt_km, galat (0 = sukses).
    Satelit yang gagal dipropagasi (TLE kedaluwarsa, orbit meluruh) mendapat NaN.
    """
    jd_list, fr_list = zip(*[ke_jd(w) for w in waktu]) if len(waktu) else ((), ())
    jd = np.array(jd_list, dtype=float)
    fr = np.array(fr_list, dtype=float)
    n, m = len(df), len(jd)
    lat = np.full((n, m), np.nan)
    lon = np.full((n, m), np.nan)
    alt = np.full((n, m), np.nan)
    galat = np.zeros((n, m), dtype=int)

    for awal in range(0, n, UKURAN_POTONGAN):
        potongan = df.iloc[awal : awal + UKURAN_POTONGAN]
        e, r, _v = _satrec_array(potongan).sgp4(jd, fr)   # r: (n_potongan, m, 3) km, kerangka TEME
        la, lo, al = teme_ke_geodetik(r, (jd + fr)[None, :])
        gagal = e != 0
        la[gagal] = lo[gagal] = al[gagal] = np.nan
        lat[awal : awal + len(potongan)] = la
        lon[awal : awal + len(potongan)] = lo
        alt[awal : awal + len(potongan)] = al
        galat[awal : awal + len(potongan)] = e
    return {"lat": lat, "lon": lon, "alt_km": alt, "galat": galat}


def posisi_saat(df: pd.DataFrame, waktu: datetime) -> pd.DataFrame:
    """Posisi semua satelit pada satu waktu: df + kolom lat, lon, alt_km. Baris yang gagal dibuang."""
    hasil = propagasi(df, [waktu])
    keluar = df.copy()
    keluar["lat"] = hasil["lat"][:, 0]
    keluar["lon"] = hasil["lon"][:, 0]
    keluar["alt_km"] = hasil["alt_km"][:, 0]
    return keluar.dropna(subset=["lat", "lon"]).reset_index(drop=True)


def jejak(line1: str, line2: str, mulai: datetime, menit: int = 100, langkah_detik: int = 30) -> pd.DataFrame:
    """Jejak darat (ground track) satu satelit: DataFrame waktu, lat, lon, alt_km dari `mulai` selama `menit`."""
    waktu = [mulai + timedelta(seconds=s) for s in range(0, menit * 60 + 1, langkah_detik)]
    df = pd.DataFrame({"line1": [line1], "line2": [line2]})
    h = propagasi(df, waktu)
    return pd.DataFrame({"waktu": waktu, "lat": h["lat"][0], "lon": h["lon"][0], "alt_km": h["alt_km"][0]})


def potong_di_garis_tanggal(df_jejak: pd.DataFrame) -> pd.DataFrame:
    """Sisipkan NaN setiap kali bujur melompat dari +180 ke -180 supaya garis tidak melintang peta."""
    lompat = np.abs(np.diff(df_jejak["lon"].to_numpy())) > 180
    if not lompat.any():
        return df_jejak
    # Baris pemisah disisipkan tepat setelah titik sebelum lompatan (indeks i + 0,5), tanpa iterrows,
    # supaya tipe kolom (datetime, float) tetap utuh.
    d = df_jejak.reset_index(drop=True)
    posisi = np.flatnonzero(lompat)
    sela = d.iloc[posisi].copy()
    for k in sela.columns:
        if k != "waktu":
            sela[k] = np.nan
    sela.index = posisi + 0.5
    return pd.concat([d, sela]).sort_index().reset_index(drop=True)


# ----------------------------------------------------------------------------
# 5. Menghitung lintasan di atas suatu wilayah
# ----------------------------------------------------------------------------
def hitung_lintasan(mask: np.ndarray, waktu: pd.DatetimeIndex, langkah_menit: float) -> pd.DataFrame:
    """
    Dari matriks boolean (n_satelit, n_waktu) "sedang di atas wilayah", hitung per satelit:
      jumlah_lintasan  : berapa kali masuk wilayah (deret True yang bersambung = satu lintasan)
      menit_di_atas    : total menit di atas wilayah
      lintasan_pertama : waktu pertama kali masuk (NaT bila tidak pernah)
      lintasan_terakhir: waktu terakhir kali berada di atas wilayah

    Deret True yang sudah menyala di waktu ke-0 tetap dihitung satu lintasan.
    """
    mask = np.asarray(mask, dtype=bool)
    if mask.ndim != 2:
        raise ValueError("mask harus berbentuk (n_satelit, n_waktu)")
    n, m = mask.shape
    if m == 0:
        return pd.DataFrame({"jumlah_lintasan": np.zeros(n, int), "menit_di_atas": np.zeros(n), "lintasan_pertama": pd.NaT, "lintasan_terakhir": pd.NaT})
    # tepi naik: False -> True. Kolom pertama dianggap didahului False.
    sebelumnya = np.concatenate([np.zeros((n, 1), dtype=bool), mask[:, :-1]], axis=1)
    tepi_naik = mask & ~sebelumnya
    jumlah = tepi_naik.sum(axis=1)
    menit = mask.sum(axis=1) * langkah_menit
    ada = mask.any(axis=1)
    idx_pertama = np.where(ada, mask.argmax(axis=1), 0)
    idx_terakhir = np.where(ada, m - 1 - mask[:, ::-1].argmax(axis=1), 0)
    waktu_arr = np.asarray(waktu)
    return pd.DataFrame({
        "jumlah_lintasan": jumlah.astype(int),
        "menit_di_atas": menit.astype(float),
        "lintasan_pertama": pd.to_datetime(np.where(ada, waktu_arr[idx_pertama], np.datetime64("NaT", "ns"))),
        "lintasan_terakhir": pd.to_datetime(np.where(ada, waktu_arr[idx_terakhir], np.datetime64("NaT", "ns"))),
    })


def daftar_lintasan(mask_1d: np.ndarray, waktu: pd.DatetimeIndex, langkah_menit: float) -> pd.DataFrame:
    """Rincian setiap lintasan satu satelit: mulai, selesai, durasi_menit. Untuk tabel 'jadwal lintasan'."""
    mask_1d = np.asarray(mask_1d, dtype=bool)
    baris = []
    sedang = False
    for i, aktif in enumerate(mask_1d):
        if aktif and not sedang:
            awal = i
            sedang = True
        elif not aktif and sedang:
            baris.append((waktu[awal], waktu[i - 1], (i - awal) * langkah_menit))
            sedang = False
    if sedang:
        baris.append((waktu[awal], waktu[len(mask_1d) - 1], (len(mask_1d) - awal) * langkah_menit))
    return pd.DataFrame(baris, columns=["mulai", "selesai", "durasi_menit"])


def rentang_waktu(mulai: datetime, jam: float, langkah_menit: float) -> pd.DatetimeIndex:
    """Deret waktu dari `mulai` sepanjang `jam` jam dengan langkah `langkah_menit` menit (UTC)."""
    mulai = mulai.astimezone(timezone.utc).replace(tzinfo=None)
    return pd.date_range(mulai, mulai + timedelta(hours=jam), freq=f"{int(langkah_menit * 60)}s", inclusive="left")
