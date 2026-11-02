"""Uji penerjemahan kode GCAT ke label aplikasi, dan penggabungan dengan katalog di repo."""

import pandas as pd

from src import klasifikasi, muat_data, orbit


def test_label_operator_dan_misi():
    assert klasifikasi.label_operator("D") == "Militer"
    assert klasifikasi.label_operator("BD") == "Militer"
    assert klasifikasi.label_operator("B") == "Komersial"
    assert klasifikasi.label_operator("-") == "Tidak diketahui"
    assert klasifikasi.label_misi("IMG-R?") == "Pencitraan radar (SAR)"
    assert klasifikasi.label_misi("COM/MET-RO") == "Komunikasi"
    assert klasifikasi.label_misi("SIG*") == "Intai sinyal (SIGINT)"
    assert klasifikasi.label_misi("XYZ") == "Lainnya / tidak diketahui"


def test_tentukan_kelompok():
    assert klasifikasi.tentukan_kelompok("ID", "Komersial", "Komunikasi") == "Indonesia"
    assert klasifikasi.tentukan_kelompok("CN", "Militer", "Komunikasi") == "Militer asing"
    assert klasifikasi.tentukan_kelompok("US", "Komersial", "Pencitraan optik") == "Pengintai sipil & komersial asing"
    assert klasifikasi.tentukan_kelompok("US", "Komersial", "Komunikasi") == "Satelit asing lainnya"
    assert klasifikasi.tentukan_kelompok("-", "Tidak diketahui", "Lainnya / tidak diketahui", terkatalog=False) == "Belum terkatalog"


def test_tebak_dari_nama():
    assert klasifikasi.tebak_dari_nama("STARLINK-35000") == ("US", "B", "COM")
    assert klasifikasi.tebak_dari_nama("YAOGAN-45 03") == ("CN", "D", "IMG")
    assert klasifikasi.tebak_dari_nama("OBJEK ANEH 123") is None


def test_klasifikasikan_mengisi_kolom():
    df = pd.DataFrame({
        "nama": ["TELKOM 3S", "YAOGAN-30 01", "STARLINK-99999", "MISTERI"],
        "negara_kode": ["ID", "CN", "-", "-"],
        "kelas": ["B", "D", "-", "-"],
        "kategori_gcat": ["COM", "SIG", "-", "-"],
        "terkatalog": [True, True, False, False],
    })
    hasil = klasifikasi.klasifikasikan(df)
    assert hasil["kelompok"].tolist() == ["Indonesia", "Militer asing", "Satelit asing lainnya", "Belum terkatalog"]
    assert hasil["pengintai"].tolist() == [False, True, False, False]
    assert hasil.loc[2, "negara_kode"] == "US"


def test_katalog_dan_cadangan_di_repo_bisa_digabung():
    katalog = muat_data.muat_katalog()
    assert len(katalog) > 20000 and katalog["norad"].is_unique
    negara = muat_data.muat_kode_negara()
    assert set(katalog["negara_kode"].unique()) - set(negara["kode_gcat"]) - {"-"} == set(), "ada kode negara GCAT yang belum dipetakan"

    df_tle = orbit.parse_tle(muat_data.baca_tle_cadangan())
    df = muat_data.gabungkan(df_tle, katalog, negara)
    assert len(df) > 10000
    assert (df["kelompok"] == "Indonesia").sum() >= 5
    assert df["terkatalog"].mean() > 0.95
    assert {"TELKOM 3S", "LAPAN-A3"} <= set(df.loc[df["kelompok"] == "Indonesia", "nama"])
    catatan = muat_data.muat_catatan_indonesia()
    assert set(catatan["norad"]) <= set(df["norad"])
