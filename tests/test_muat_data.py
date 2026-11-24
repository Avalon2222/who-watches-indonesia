"""
Tes untuk rantai sumber TLE di src/muat_data.py dan helper waktu di src/orbit.py.

Internet dipalsukan pakai monkeypatch, jadi tes ini tetap jalan offline dan
bisa mensimulasikan CelesTrak mati / snapshot GitHub mati.
"""

from datetime import datetime, timedelta, timezone

import pandas as pd
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


def test_tanggal_dari_header_rusak_tidak_crash():
    assert muat_data.tanggal_dari_header("# diunduh 2026-11-02T25:99Z") == datetime(2026, 11, 2, tzinfo=timezone.utc)
    assert muat_data.tanggal_dari_header("# diunduh 2026-13-45") == datetime(2000, 1, 1, tzinfo=timezone.utc)


def test_gabungkan_katalog_norad_ganda_tidak_menggandakan_satelit():
    tle = pd.DataFrame({
        "norad": [25544], "nama": ["ISS (ZARYA)"], "line1": ["1"], "line2": ["2"],
        "epoch": [datetime(2026, 11, 1, tzinfo=timezone.utc)], "inklinasi_deg": [51.6], "mean_motion": [15.5],
    })
    baris = {"nama_gcat": "ISS", "pemilik": "NASA", "kelas": "C", "kategori_gcat": "SS",
             "program": "ISS", "orbit_gcat": "LEO", "tanggal_luncur": "1998"}
    katalog = pd.DataFrame([{"norad": 25544, "negara_kode": "RU", **baris}, {"norad": 25544, "negara_kode": "US", **baris}])
    negara = pd.DataFrame({"kode_gcat": ["US"], "negara": ["Amerika Serikat"], "bendera": ["🇺🇸"]})
    hasil = muat_data.gabungkan(tle, katalog, negara)
    assert len(hasil) == 1
    assert hasil.iloc[0]["negara"] == "Amerika Serikat"


def test_gabungkan_kode_negara_huruf_kecil_tetap_dapat_nama():
    tle = pd.DataFrame({
        "norad": [1, 2], "nama": ["A", "B"], "line1": ["1", "1"], "line2": ["2", "2"],
        "epoch": [datetime(2026, 11, 1, tzinfo=timezone.utc)] * 2, "inklinasi_deg": [51.6, 0.1], "mean_motion": [15.5, 1.0],
    })
    baris = {"nama_gcat": "X", "pemilik": "-", "kelas": "B", "kategori_gcat": "COM",
             "program": "-", "orbit_gcat": "LEO", "tanggal_luncur": "2020"}
    katalog = pd.DataFrame([{"norad": 1, "negara_kode": " us", **baris}, {"norad": 2, "negara_kode": "id ", **baris}])
    negara = pd.DataFrame({"kode_gcat": ["US", "ID"], "negara": ["Amerika Serikat", "Indonesia"], "bendera": ["🇺🇸", "🇮🇩"]})
    hasil = muat_data.gabungkan(tle, katalog, negara)
    assert list(hasil["negara"]) == ["Amerika Serikat", "Indonesia"]
    assert list(hasil["bendera"]) == ["🇺🇸", "🇮🇩"]
    assert hasil.iloc[1]["kelompok"] == "Indonesia"


@pytest.mark.parametrize("langkah", [float("nan"), float("inf")])
def test_rentang_waktu_langkah_nan_atau_tak_hingga_ditolak(langkah):
    with pytest.raises(ValueError, match="langkah_menit"):
        orbit.rentang_waktu(datetime(2026, 1, 1), 1, langkah)


def test_gabungkan_kode_di_tabel_negara_huruf_kecil():
    tle = pd.DataFrame({
        "norad": [1], "nama": ["A"], "line1": ["1"], "line2": ["2"],
        "epoch": [datetime(2026, 11, 1, tzinfo=timezone.utc)], "inklinasi_deg": [0.1], "mean_motion": [1.0],
    })
    katalog = pd.DataFrame([{"norad": 1, "negara_kode": "ID", "nama_gcat": "X", "pemilik": "-", "kelas": "B",
                             "kategori_gcat": "COM", "program": "-", "orbit_gcat": "GEO", "tanggal_luncur": "2020"}])
    negara = pd.DataFrame({"kode_gcat": [" id"], "negara": ["Indonesia"], "bendera": ["🇮🇩"]})
    hasil = muat_data.gabungkan(tle, katalog, negara)
    assert hasil.iloc[0]["negara"] == "Indonesia"
    assert hasil.iloc[0]["bendera"] == "🇮🇩"
