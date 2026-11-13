"""Tes pembangun katalog GCAT (scripts/bangun_katalog.py) dengan potongan TSV tiruan, tanpa internet."""

import importlib.util
from pathlib import Path

import pandas as pd

PATH = Path(__file__).resolve().parents[1] / "scripts" / "bangun_katalog.py"
spec = importlib.util.spec_from_file_location("bangun_katalog", PATH)
bk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bk)

SATCAT = (
    "#JCAT\tSatcat\tType\tName\tState\tOwner\tLDate\tOpOrbit\tMass\n"
    "# Updated 2026 Nov 2\n"
    "S00002\t2\tP\t1-y ISZ \tSU\tOKB1\t1957 Oct  4 1928:34\tLLEO/I\t84\n"
    "S00001\t1\tR2\tR-7 stage\tSU\tOKB1\t1957 Oct  4\tLLEO/I\t7790\n"
    "S41591\t41591\tP\tTelkom 3S\tID\tTELKOM\t2017 Feb 14\tGEO\t3550\n"
    "A00001\t\tP\tTanpa NORAD\tUS\tNASA\t2020 Jan  1\tLEO\t-\n"
)
PSATCAT = (
    "#JCAT\tClass\tCategory\tProgram\n"
    "# Updated 2026 Nov 2\n"
    "S00002\tC\tTECH\tSputnik\n"
    "S41591\tC\tCOM\t\n"
)


def test_baca_tsv_lewati_baris_tanggal_dan_rapikan_kolom():
    df = bk._baca_tsv(SATCAT.encode())
    assert list(df.columns)[:3] == ["JCAT", "Satcat", "Type"]
    assert len(df) == 4
    assert df.loc[0, "Name"] == "1-y ISZ"          # spasi di ujung dibuang
    assert df.loc[3, "Satcat"] == ""                # sel kosong tetap teks kosong, bukan NaN


def test_gabungkan_hanya_payload_bernomor_norad():
    kat = bk.gabungkan(bk._baca_tsv(SATCAT.encode()), bk._baca_tsv(PSATCAT.encode()))
    assert list(kat.columns) == bk.KOLOM_KELUARAN
    assert kat["norad"].tolist() == [2, 41591]      # roket dan payload tanpa NORAD dibuang
    sputnik, telkom = kat.iloc[0], kat.iloc[1]
    assert sputnik["tanggal_luncur"] == "1957-10-04" and sputnik["massa_kg"] == 84
    assert telkom["negara_kode"] == "ID" and telkom["kategori_gcat"] == "COM"
    assert telkom["program"] == ""                  # program kosong dari GCAT dibiarkan kosong
