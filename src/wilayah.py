"""
wilayah.py - Batas wilayah Indonesia versi sederhana dan uji "titik di dalam poligon".

Satelit dianggap "melintas di atas Indonesia" bila titik sub-satelitnya (proyeksi tegak lurus ke
permukaan Bumi) berada di dalam poligon di bawah. Poligon ini adalah sketsa kasar yang mengikuti
batas daratan dan laut Indonesia (termasuk Laut Natuna, Laut Jawa, Laut Banda, Laut Arafura),
bukan batas resmi. Simpangannya bisa 50-100 km dari batas sebenarnya, dan Timor-Leste ikut
terlingkupi karena berada di tengah poligon. Untuk analisis "siapa yang melintas" tingkat
ketelitian ini sudah cukup; untuk keperluan hukum tentu tidak.
"""

from __future__ import annotations

import numpy as np

# Pasangan (lon, lat), searah jarum jam mulai dari ujung barat laut (Sabang).
POLIGON_INDONESIA: list[tuple[float, float]] = [
    (94.5, 6.5), (98.0, 5.5), (100.5, 3.0), (103.0, 1.6), (104.3, 1.1),      # Selat Malaka hingga Selat Singapura
    (105.5, 2.0), (107.0, 4.5), (108.5, 6.5), (110.0, 5.5), (109.6, 2.1),    # Laut Natuna, kembali ke Tanjung Datu
    (110.5, 1.0), (112.0, 1.3), (113.5, 1.4), (114.8, 1.5), (115.3, 3.0),    # perbatasan darat Kalimantan-Sarawak
    (115.9, 4.3), (117.9, 4.2), (118.5, 3.8), (119.5, 4.5), (121.5, 4.5),    # perbatasan Sabah, Laut Sulawesi
    (124.5, 4.8), (126.5, 6.0), (127.5, 5.5), (129.0, 3.5), (131.0, 2.0),    # Miangas, Laut Maluku, Samudra Pasifik
    (134.0, 1.0), (137.5, -0.5), (141.0, -2.0), (141.0, -9.3),              # utara Papua, perbatasan PNG (141 BT)
    (139.0, -10.0), (136.0, -10.5), (132.0, -10.5), (128.0, -11.0),         # Laut Arafura
    (125.0, -11.5), (121.0, -11.5), (117.0, -10.5), (113.0, -10.0),         # selatan Timor, Sumba, Jawa
    (109.0, -9.5), (106.0, -8.5), (103.0, -7.0), (100.0, -4.5),             # Samudra Hindia selatan Jawa-Sumatra
    (97.0, -1.0), (95.0, 2.0),                                              # barat Sumatra, kembali ke Sabang
]

# Kotak pembatas (bounding box): saringan cepat sebelum uji poligon yang lebih mahal.
LON_MIN, LON_MAX = 94.5, 141.0
LAT_MIN, LAT_MAX = -11.5, 6.5

# Kawasan sekitar yang lebih luas, dipakai untuk peta "sekitar Indonesia".
KAWASAN = {"lon_min": 85.0, "lon_max": 150.0, "lat_min": -20.0, "lat_max": 15.0}


def di_dalam_poligon(lat, lon, poligon: list[tuple[float, float]] = POLIGON_INDONESIA) -> np.ndarray:
    """
    Uji titik-di-dalam-poligon dengan metode ray casting, tervektorisasi untuk array numpy.

    Ide: tarik garis khayal dari titik ke arah timur tak hingga, hitung berapa kali garis itu memotong
    sisi poligon. Ganjil = di dalam, genap = di luar. Bekerja untuk poligon cekung sekalipun.

    >>> bool(di_dalam_poligon(np.array([-6.2]), np.array([106.8]))[0])   # Jakarta
    True
    >>> bool(di_dalam_poligon(np.array([1.35]), np.array([103.8]))[0])   # Singapura
    False
    """
    lat = np.asarray(lat, dtype=float)
    lon = np.asarray(lon, dtype=float)
    di_dalam = np.zeros(lat.shape, dtype=bool)
    n = len(poligon)
    for i in range(n):
        x1, y1 = poligon[i]
        x2, y2 = poligon[(i + 1) % n]
        # sisi memotong garis horizontal y=lat ?
        melintang = (y1 > lat) != (y2 > lat)
        # titik potong sisi dengan garis horizontal itu berada di sebelah timur titik ?
        with np.errstate(divide="ignore", invalid="ignore"):
            x_potong = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
        di_dalam ^= melintang & (lon < x_potong)
    return di_dalam


def di_atas_indonesia(lat, lon) -> np.ndarray:
    """True bila titik (lat, lon) berada di dalam poligon Indonesia. Kotak pembatas dipakai sebagai saringan awal."""
    lat = np.asarray(lat, dtype=float)
    lon = np.asarray(lon, dtype=float)
    kotak = (lat >= LAT_MIN) & (lat <= LAT_MAX) & (lon >= LON_MIN) & (lon <= LON_MAX)
    hasil = np.zeros(lat.shape, dtype=bool)
    if kotak.any():
        hasil[kotak] = di_dalam_poligon(lat[kotak], lon[kotak])
    return hasil


def di_kawasan(lat, lon) -> np.ndarray:
    """True bila titik berada di kawasan sekitar Indonesia (kotak yang lebih luas untuk peta)."""
    lat = np.asarray(lat, dtype=float)
    lon = np.asarray(lon, dtype=float)
    return (lat >= KAWASAN["lat_min"]) & (lat <= KAWASAN["lat_max"]) & (lon >= KAWASAN["lon_min"]) & (lon <= KAWASAN["lon_max"])


def poligon_lon_lat() -> tuple[list[float], list[float]]:
    """Poligon tertutup sebagai dua list (lon, lat) untuk digambar di peta."""
    titik = POLIGON_INDONESIA + [POLIGON_INDONESIA[0]]
    return [p[0] for p in titik], [p[1] for p in titik]
