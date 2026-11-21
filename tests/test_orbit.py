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


def test_rentang_waktu_tanpa_zona_dianggap_utc():
    t = orbit.rentang_waktu(datetime(2026, 11, 13, 0, 0), jam=0.5, langkah_menit=10)
    assert list(t) == [pd.Timestamp("2026-11-13 00:00"), pd.Timestamp("2026-11-13 00:10"), pd.Timestamp("2026-11-13 00:20")]


@pytest.mark.parametrize("mm", [float("nan"), 0.0, -1.0, None])
def test_jenis_orbit_dan_periode_untuk_mean_motion_tidak_valid(mm):
    assert orbit.jenis_orbit(mm, 51.6) == "Tidak diketahui"
    assert np.isnan(orbit.periode_menit(mm))


def test_periode_menit_iss_sekitar_93_menit():
    assert orbit.periode_menit(15.4915) == pytest.approx(92.95, abs=0.05)


def _perbarui_checksum(baris: str) -> str:
    total = sum(int(c) if c.isdigit() else 1 if c == "-" else 0 for c in baris[:68])
    return baris[:68] + str(total % 10)


def test_parse_tle_nomor_norad_alpha5():
    l1 = _perbarui_checksum(TLE_CONTOH.splitlines()[1].replace("25544", "T0002", 1))
    l2 = _perbarui_checksum(TLE_CONTOH.splitlines()[2].replace("25544", "T0002", 1))
    df = orbit.parse_tle("UJI ALPHA5\n" + l1 + "\n" + l2)
    assert len(df) == 1
    assert df.loc[0, "norad"] == 270002
    assert orbit._norad("A0001") == 100001
    assert orbit._norad("J0000") == 180000
    assert orbit._norad("Z9999") == 339999


def test_parse_tle_buang_awalan_0_format_3le():
    teks = TLE_CONTOH.replace("ISS (ZARYA)", "0 ISS (ZARYA)").replace("TELKOM 3S", "0 TELKOM 3S")
    df = orbit.parse_tle(teks)
    assert list(df["nama"]) == ["ISS (ZARYA)", "TELKOM 3S"]


def test_parse_tle_lewati_pasangan_norad_tidak_cocok():
    b = TLE_CONTOH.splitlines()
    # baris 1 ISS dipasangkan dengan baris 2 TELKOM 3S: bukan satu satelit
    teks = "\n".join(["CAMPUR", b[1], b[5], b[3], b[4], b[5]])
    df = orbit.parse_tle(teks)
    assert list(df["norad"]) == [41944]


def test_rentang_waktu_langkah_pecahan_dan_sangat_kecil():
    mulai = datetime(2026, 1, 1)
    # 1/3 menit = 20 detik, bukan 19 karena terpotong int().
    w = orbit.rentang_waktu(mulai, 0.1, 1 / 3)
    assert (w[1] - w[0]).total_seconds() == 20
    # Langkah di bawah 1 detik dibulatkan jadi 1 detik, tidak error.
    assert (orbit.rentang_waktu(mulai, 0.001, 0.005)[1] - mulai).total_seconds() == 1
    with pytest.raises(ValueError):
        orbit.rentang_waktu(mulai, 1, 0)


def test_parse_tle_lewati_baris_dengan_checksum_salah():
    baris = TLE_CONTOH.splitlines()
    # Satu digit inklinasi tertukar (51.6332 -> 59.6332), checksum jadi tidak cocok.
    rusak = baris[2].replace("51.6332", "59.6332", 1)
    df = orbit.parse_tle("\n".join([baris[0], baris[1], rusak]))
    assert df.empty
    assert orbit._checksum_ok(baris[1]) and orbit._checksum_ok(baris[2])
    assert orbit._checksum_ok(baris[1][:68])  # tanpa kolom checksum tetap diterima


def test_jenis_orbit_dan_periode_aman_untuk_pd_na_dan_teks():
    assert orbit.jenis_orbit(pd.NA, 50.0) == "Tidak diketahui"
    assert orbit.jenis_orbit("15.5", "53") == "LEO"
    assert orbit.jenis_orbit("abc", 0) == "Tidak diketahui"
    assert np.isnan(orbit.periode_menit(pd.NA))
    assert orbit.periode_menit("2") == 720.0


def test_parse_tle_duplikat_norad_ambil_epoch_terbaru():
    baris = TLE_CONTOH.splitlines()
    l1_baru = _perbarui_checksum(baris[1].replace("26306.43427755", "26307.43427755", 1))
    teks = TLE_CONTOH + "\n".join(["ISS BARU", l1_baru, baris[2]])
    df = orbit.parse_tle(teks)
    assert sorted(df["norad"]) == [25544, 41944]
    iss = df[df["norad"] == 25544].iloc[0]
    assert iss["nama"] == "ISS BARU"
    assert iss["epoch"].day == 3


@pytest.mark.parametrize("z", [7000.0, -7000.0])
def test_ketinggian_tepat_di_atas_kutub(z):
    # Jari-jari kutub WGS84 = 6356,752 km, jadi ketinggian = |z| - 6356,752.
    lat, _lon, alt = orbit.teme_ke_geodetik(np.array([[0.0, 0.0, z]]), np.array([2460000.5]))
    assert abs(lat[0]) == pytest.approx(90.0)
    assert alt[0] == pytest.approx(7000.0 - 6356.752, abs=0.01)


def test_ketinggian_di_ekuator_tidak_berubah():
    _lat, _lon, alt = orbit.teme_ke_geodetik(np.array([[7000.0, 0.0, 0.0]]), np.array([2460000.5]))
    assert alt[0] == pytest.approx(7000.0 - 6378.137, abs=1e-6)


def test_lintasan_panjang_waktu_tidak_cocok_ditolak():
    waktu = pd.date_range("2026-01-01", periods=2, freq="min")
    with pytest.raises(ValueError, match="panjang waktu"):
        orbit.hitung_lintasan(np.array([[True, True, False]]), waktu, 1)
    with pytest.raises(ValueError, match="panjang waktu"):
        orbit.daftar_lintasan(np.array([False, True, True]), waktu, 1)
