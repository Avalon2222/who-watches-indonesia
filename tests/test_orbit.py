"""Uji pembacaan TLE, propagasi, dan penghitungan lintasan dengan TLE contoh (tanpa internet)."""

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from src import orbit

# TLE nyata (CelesTrak, epoch 2 Nov 2026). Dipakai hanya sebagai contoh bentuk data.
TLE_CONTOH = """ISS (ZARYA)
1 25544U 98067A   26306.43427755  .00005374  00000+0  10508-3 0  9999
2 25544  51.6332 335.9757 0007139 339.3739  20.6961 15.49150046593183
TELKOM 3S
1 41944U 17007A   26306.50444602 -.00000370  00000+0  00000+0 0  9998
2 41944   0.0054 199.7592 0002611  36.4271 105.2252  1.00270770 35524
"""


def test_parse_tle_membaca_nama_dan_elemen():
    df = orbit.parse_tle(TLE_CONTOH)
    assert len(df) == 2
    assert df.loc[0, "norad"] == 25544 and df.loc[0, "nama"] == "ISS (ZARYA)"
    assert df.loc[1, "norad"] == 41944
    assert abs(df.loc[1, "mean_motion"] - 1.0027) < 0.001
    assert df.loc[0, "epoch"].year == 2026 and df.loc[0, "epoch"].month == 11


def test_parse_tle_tahan_baris_rusak():
    teks = "SAMPAH\nbaris tidak jelas\n" + TLE_CONTOH
    assert len(orbit.parse_tle(teks)) == 2


def test_jenis_orbit():
    assert orbit.jenis_orbit(1.0027, 0.02) == "GEO"
    assert orbit.jenis_orbit(1.0027, 45.0) == "GSO miring"
    assert orbit.jenis_orbit(2.0057, 55.0) == "MEO"       # GPS
    assert orbit.jenis_orbit(15.5, 97.0) == "LEO"
    assert abs(orbit.periode_menit(15.0) - 96.0) < 1e-9


def test_gmst_dekat_nilai_referensi():
    # Vallado contoh 3-5: 1992 Aug 20 12:14:00 UTC -> GMST 152.578 787 ° (JD 2448855.009722)
    g = np.degrees(orbit.gmst_rad(np.array([2448855.009722])))[0]
    assert abs(g - 152.5787) < 0.01


def test_geo_diam_di_bujur_tetap():
    df = orbit.parse_tle(TLE_CONTOH)
    geo = df[df["norad"] == 41944]
    t0 = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
    pos = orbit.propagasi(geo, [t0, t0 + timedelta(hours=6), t0 + timedelta(hours=12)])
    lon = pos["lon"][0]
    assert np.all(np.abs(lon - 118.0) < 0.5)                 # slot Telkom 3S: 118° BT
    assert np.all(np.abs(pos["lat"][0]) < 0.5)
    assert np.all(np.abs(pos["alt_km"][0] - 35786) < 150)


def test_leo_bergerak_dan_ketinggian_masuk_akal():
    df = orbit.parse_tle(TLE_CONTOH)
    iss = df[df["norad"] == 25544]
    t0 = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
    pos = orbit.propagasi(iss, [t0, t0 + timedelta(minutes=10)])
    assert 350 < pos["alt_km"][0, 0] < 500
    assert abs(pos["lat"][0, 0] - pos["lat"][0, 1]) + abs(pos["lon"][0, 0] - pos["lon"][0, 1]) > 5
    assert np.abs(pos["lat"][0]).max() <= 51.7                 # tidak melebihi inklinasi


def test_hitung_lintasan_menghitung_deret_true():
    waktu = pd.date_range("2026-11-02", periods=10, freq="1min")
    mask = np.array([
        [0, 1, 1, 0, 0, 1, 0, 0, 1, 1],   # 3 lintasan, 5 menit
        [1, 1, 0, 0, 0, 0, 0, 0, 0, 0],   # 1 lintasan (sudah di atas sejak awal), 2 menit
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],   # tidak pernah
    ], dtype=bool)
    r = orbit.hitung_lintasan(mask, waktu, 1.0)
    assert r["jumlah_lintasan"].tolist() == [3, 1, 0]
    assert r["menit_di_atas"].tolist() == [5.0, 2.0, 0.0]
    assert r.loc[0, "lintasan_pertama"] == waktu[1]
    assert r.loc[0, "lintasan_terakhir"] == waktu[9]
    assert pd.isna(r.loc[2, "lintasan_pertama"])


def test_daftar_lintasan_memberi_mulai_selesai_durasi():
    waktu = pd.date_range("2026-11-02", periods=10, freq="1min")
    mask = np.array([0, 1, 1, 0, 0, 1, 0, 0, 1, 1], dtype=bool)
    d = orbit.daftar_lintasan(mask, waktu, 1.0)
    assert len(d) == 3
    assert d["durasi_menit"].tolist() == [2.0, 1.0, 2.0]
    assert d.loc[2, "selesai"] == waktu[9]


def test_hitung_lintasan_menolak_bentuk_salah():
    with pytest.raises(ValueError):
        orbit.hitung_lintasan(np.zeros(5, bool), pd.date_range("2026-11-02", periods=5, freq="1min"), 1.0)


def test_potong_di_garis_tanggal_menyisipkan_nan():
    jejak = pd.DataFrame({"waktu": pd.date_range("2026-11-02", periods=4, freq="30s"),
                          "lat": [0.0, 1.0, 2.0, 3.0], "lon": [170.0, 179.0, -179.0, -170.0], "alt_km": [500.0] * 4})
    hasil = orbit.potong_di_garis_tanggal(jejak)
    assert len(hasil) == 5 and hasil["lon"].isna().sum() == 1


def test_teme_ke_geodetik_bolak_balik():
    # Buat titik dari lat/lon/alt yang diketahui, putar ke TEME, lalu pastikan fungsi mengembalikannya lagi.
    lat0, lon0, alt0 = np.radians([-6.2, 45.0, 0.0]), np.radians([106.8, -120.0, 0.0]), np.array([550.0, 20200.0, 35786.0])
    jd = np.array([2461346.5, 2461346.75, 2461347.1])
    n = orbit.R_BUMI_KM / np.sqrt(1 - orbit.E2 * np.sin(lat0) ** 2)
    x_e = (n + alt0) * np.cos(lat0) * np.cos(lon0)
    y_e = (n + alt0) * np.cos(lat0) * np.sin(lon0)
    z_e = (n * (1 - orbit.E2) + alt0) * np.sin(lat0)
    theta = orbit.gmst_rad(jd)
    r_teme = np.stack([np.cos(theta) * x_e - np.sin(theta) * y_e,
                       np.sin(theta) * x_e + np.cos(theta) * y_e, z_e], axis=-1)
    lat, lon, alt = orbit.teme_ke_geodetik(r_teme, jd)
    assert lat == pytest.approx(np.degrees(lat0), abs=1e-6)
    assert lon == pytest.approx(np.degrees(lon0), abs=1e-6)
    assert alt == pytest.approx(alt0, abs=1e-3)


def test_posisi_saat_buang_satelit_gagal():
    df = orbit.parse_tle(TLE_CONTOH)
    # TLE rusak (eksentrisitas > 1) tidak bisa dipropagasi dan harus dibuang dari hasil.
    rusak = df.iloc[[0]].copy()
    rusak["line2"] = rusak["line2"].str.slice(0, 26) + "9999999" + rusak["line2"].str.slice(33)
    gabung = pd.concat([df, rusak], ignore_index=True)
    t0 = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
    pos = orbit.posisi_saat(gabung, t0)
    assert len(pos) == 2
    assert {"lat", "lon", "alt_km"} <= set(pos.columns)
    assert pos.index.tolist() == [0, 1]
    assert len(gabung) == 3 and "lat" not in gabung   # input tidak diubah


def test_jejak_satu_orbit_iss():
    df = orbit.parse_tle(TLE_CONTOH)
    iss = df[df["norad"] == 25544].iloc[0]
    t0 = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
    j = orbit.jejak(iss["line1"], iss["line2"], t0, menit=10, langkah_detik=60)
    assert len(j) == 11 and j["waktu"].iloc[-1] == t0 + timedelta(minutes=10)
    assert j[["lat", "lon", "alt_km"]].notna().all().all()


def test_potong_di_garis_tanggal_jaga_tipe_dan_posisi():
    jejak = pd.DataFrame({"waktu": pd.date_range("2026-11-02", periods=6, freq="30s"),
                          "lat": [0.0, 1.0, 2.0, 3.0, 4.0, 5.0],
                          "lon": [178.0, -178.0, -170.0, 170.0, 179.0, -179.0], "alt_km": [500.0] * 6})
    hasil = orbit.potong_di_garis_tanggal(jejak)
    assert len(hasil) == 9  # tiga lompatan: dua lewat garis tanggal, satu kembali
    assert hasil["lon"].isna().sum() == 3
    assert list(hasil.index[hasil["lon"].isna()]) == [1, 4, 7]
    assert str(hasil["waktu"].dtype).startswith("datetime64")
    assert hasil["lat"].dtype == float
    assert hasil["waktu"].is_monotonic_increasing


def test_potong_di_garis_tanggal_tanpa_lompatan():
    jejak = pd.DataFrame({"waktu": pd.date_range("2026-11-02", periods=3, freq="30s"),
                          "lat": [0.0, 1.0, 2.0], "lon": [100.0, 101.0, 102.0], "alt_km": [500.0] * 3})
    assert orbit.potong_di_garis_tanggal(jejak) is jejak


def test_parse_tle_lewati_angka_rusak():
    rusak = TLE_CONTOH.splitlines()
    rusak[1] = rusak[1][:2] + "ABCDE" + rusak[1][7:]  # nomor NORAD bukan angka
    df = orbit.parse_tle("\n".join(rusak))
    assert len(df) == 1


def test_hitung_lintasan_tanpa_waktu():
    hasil = orbit.hitung_lintasan(np.zeros((3, 0), bool), pd.DatetimeIndex([]), 1.0)
    assert len(hasil) == 3
    assert (hasil["jumlah_lintasan"] == 0).all()
    assert hasil["lintasan_pertama"].isna().all()


def test_rentang_waktu_utc_tanpa_ujung_akhir():
    from src import orbit as o

    wib = timezone(timedelta(hours=7))
    t = o.rentang_waktu(datetime(2026, 11, 13, 7, 0, tzinfo=wib), jam=1, langkah_menit=15)
    assert len(t) == 4                                       # 00:00, 00:15, 00:30, 00:45 UTC
    assert t[0] == pd.Timestamp("2026-11-13 00:00") and t.tz is None
