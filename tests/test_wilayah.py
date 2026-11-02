"""Uji poligon Indonesia dan uji titik-di-dalam-poligon."""

import numpy as np

from src import wilayah


def test_kota_besar_di_dalam():
    kota = {"Jakarta": (-6.2, 106.8), "Medan": (3.6, 98.7), "Makassar": (-5.1, 119.4), "Jayapura": (-2.5, 140.7),
            "Natuna": (3.9, 108.2), "Kupang": (-10.2, 123.6), "Pontianak": (0.0, 109.3), "Tarakan": (3.3, 117.6)}
    lat = np.array([v[0] for v in kota.values()])
    lon = np.array([v[1] for v in kota.values()])
    hasil = wilayah.di_atas_indonesia(lat, lon)
    assert hasil.all(), [k for k, h in zip(kota, hasil) if not h]


def test_kota_tetangga_di_luar():
    kota = {"Singapura": (1.35, 103.8), "Kuala Lumpur": (3.1, 101.7), "Manila": (14.6, 121.0), "Darwin": (-12.5, 130.8),
            "Kuching": (1.55, 110.35), "Kota Kinabalu": (5.98, 116.07), "Port Moresby": (-9.4, 147.2), "Bangkok": (13.7, 100.5)}
    lat = np.array([v[0] for v in kota.values()])
    lon = np.array([v[1] for v in kota.values()])
    hasil = wilayah.di_atas_indonesia(lat, lon)
    assert not hasil.any(), [k for k, h in zip(kota, hasil) if h]


def test_bentuk_array_dua_dimensi():
    lat = np.array([[-6.2, 1.35], [40.0, -8.5]])
    lon = np.array([[106.8, 103.8], [-74.0, 115.2]])
    hasil = wilayah.di_atas_indonesia(lat, lon)
    assert hasil.shape == (2, 2)
    assert hasil.tolist() == [[True, False], [False, True]]


def test_poligon_tertutup_dan_wajar():
    lon, lat = wilayah.poligon_lon_lat()
    assert (lon[0], lat[0]) == (lon[-1], lat[-1])
    assert min(lon) >= wilayah.LON_MIN and max(lon) <= wilayah.LON_MAX
    assert min(lat) >= wilayah.LAT_MIN and max(lat) <= wilayah.LAT_MAX


def test_ray_casting_persegi_sederhana():
    persegi = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    assert wilayah.di_dalam_poligon(np.array([5.0]), np.array([5.0]), persegi)[0]
    assert not wilayah.di_dalam_poligon(np.array([5.0]), np.array([15.0]), persegi)[0]
