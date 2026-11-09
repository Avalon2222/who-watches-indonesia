"""
Tes untuk rantai sumber TLE di src/muat_data.py dan helper waktu di src/orbit.py.

Internet dipalsukan pakai monkeypatch, jadi tes ini tetap jalan offline dan
bisa mensimulasikan CelesTrak mati / snapshot GitHub mati.
"""

from datetime import datetime, timedelta, timezone

import pytest
import requests

from src import muat_data, orbit

TLE_PALSU = "# CelesTrak GROUP=active, diunduh 2026-11-05T06:30Z.\n" + "SAT\n1 x\n2 x\n" * 101


class _Respons:
    def __init__(self, teks: str, status: int = 200):
        self.text = teks
        self.status = status

    def raise_for_status(self):
        if self.status >= 400:
            raise requests.HTTPError(f"{self.status}")


def _pasang_internet(monkeypatch, celestrak, snapshot):
    """celestrak/snapshot: teks respons, atau kelas exception untuk mensimulasikan gagal."""
    def get_palsu(url, timeout):
        jawab = celestrak if url == muat_data.URL_TLE_AKTIF else snapshot
        if isinstance(jawab, type) and issubclass(jawab, Exception):
            raise jawab("gagal")
        return _Respons(jawab)

    monkeypatch.setattr(muat_data.requests, "get", get_palsu)


def test_ambil_tle_pakai_celestrak_kalau_hidup(monkeypatch):
    _pasang_internet(monkeypatch, TLE_PALSU, requests.ConnectionError)
    hasil = muat_data.ambil_tle()
    assert hasil.sumber == "CelesTrak (live)"
    assert hasil.pesan == ""


def test_ambil_tle_jatuh_ke_snapshot_harian(monkeypatch):
    _pasang_internet(monkeypatch, requests.ConnectTimeout, TLE_PALSU)
    hasil = muat_data.ambil_tle()
    assert hasil.sumber == "snapshot harian"
    assert hasil.diambil_pada == datetime(2026, 11, 5, 6, 30, tzinfo=timezone.utc)
    assert "ConnectTimeout" in hasil.pesan


def test_ambil_tle_respons_aneh_dianggap_gagal(monkeypatch):
    # CelesTrak kadang membalas 200 tapi isinya pesan error, bukan TLE
    _pasang_internet(monkeypatch, "GP data has not updated since your last download", requests.ConnectionError)
    hasil = muat_data.ambil_tle()
    assert hasil.sumber == "cadangan di repo"
    assert "tidak berisi TLE" in hasil.pesan
    assert hasil.teks == muat_data.baca_tle_cadangan()


def test_tanggal_dari_header_tanpa_jam_dan_tanpa_tanggal():
    assert muat_data.tanggal_dari_header("# diunduh 2026-01-02\n") == datetime(2026, 1, 2, tzinfo=timezone.utc)
    assert muat_data.tanggal_dari_header("tanpa tanggal").year == 2000


def test_epoch_tle_tahun_dua_digit():
    # hari ke-1.5 tahun 2026 = 1 Januari jam 12:00 UTC
    baris1 = "1 25544U 98067A   26001.50000000  .00000000  00000-0  00000-0 0  9990"
    assert orbit._epoch_tle(baris1) == datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    # tahun 57-99 berarti abad 1900-an (aturan format TLE)
    baris_lama = baris1.replace("26001", "98001")
    assert orbit._epoch_tle(baris_lama).year == 1998


def test_periode_menit():
    assert orbit.periode_menit(1.0) == pytest.approx(1440)
    assert orbit.periode_menit(15.5) == pytest.approx(92.9, abs=0.1)   # kira-kira ISS


def test_ke_jd_naive_dianggap_utc():
    aware = datetime(2026, 11, 7, 12, tzinfo=timezone.utc)
    wib = aware.astimezone(timezone(timedelta(hours=7)))
    assert orbit.ke_jd(aware.replace(tzinfo=None)) == orbit.ke_jd(aware) == orbit.ke_jd(wib)


def test_rentang_waktu_panjang_dan_langkah():
    mulai = datetime(2026, 11, 7, tzinfo=timezone.utc)
    waktu = orbit.rentang_waktu(mulai, jam=2, langkah_menit=10)
    assert len(waktu) == 12                     # 120 menit / 10, ujung tidak ikut
    assert waktu[1] - waktu[0] == timedelta(minutes=10)
    assert waktu.tz is None                     # sgp4 butuh waktu naive (UTC)


def test_kolom_teks_kenal_dtype_pandas_3():
    import pandas as pd
    assert muat_data._kolom_teks(pd.Series(["a", None], dtype="str"))
    assert muat_data._kolom_teks(pd.Series(["a", None], dtype=object))
    assert not muat_data._kolom_teks(pd.Series([1.0, None]))
    df = muat_data.muat_catatan_indonesia()
    teks = [k for k in df.columns if muat_data._kolom_teks(df[k])]
    assert teks and not df[teks].isna().any().any()


def test_tanggal_tle_cadangan_dari_header_repo():
    t = muat_data.tanggal_tle_cadangan()
    assert t.tzinfo == timezone.utc
    assert t > datetime(2026, 1, 1, tzinfo=timezone.utc)   # bukan nilai jatuh 2000-01-01


def test_tanggal_katalog(monkeypatch, tmp_path):
    assert muat_data.tanggal_katalog() != "?"
    palsu = tmp_path / "katalog.csv"
    palsu.write_text("# Sumber: GCAT. Dibangun 2026-11-02.\nnorad\n", encoding="utf-8")
    monkeypatch.setattr(muat_data, "FILE_KATALOG", palsu)
    assert muat_data.tanggal_katalog() == "2026-11-02"
    palsu.write_text("norad\n", encoding="utf-8")
    assert muat_data.tanggal_katalog() == "?"


def test_muat_semua_pakai_tle_yang_diberikan():
    teks = muat_data.FILE_TLE_CADANGAN.read_text(encoding="utf-8")
    tle = muat_data.HasilTLE(teks=teks, sumber="cadangan di repo", diambil_pada=datetime.now(timezone.utc))
    df, kembali = muat_data.muat_semua(tle)
    assert kembali is tle
    assert len(df) > 1000
    assert {"norad", "line1", "line2"} <= set(df.columns)
