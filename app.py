"""
app.py - Who Watches Indonesia
================================
Jalankan dengan:   streamlit run app.py

Alur besar file ini (baca dari atas ke bawah):
  1. Import library + konfigurasi halaman
  2. Muat data: TLE live dari CelesTrak (cadangan di data/) + katalog GCAT (src/muat_data.py)
  3. Sidebar: kelompok satelit yang ditampilkan, jendela analisis, learning mode
  4. Hitung posisi sekarang (src/orbit.py) dan lintasan 24 jam di atas wilayah (src/wilayah.py)
  5. Tampilkan: angka ringkasan -> tab live map / who's watching / satelit Indonesia / track / data / cara kerja

Setiap bagian diberi komentar "APA" dan "MENGAPA". Penjelasan istilah ada di docs/BELAJAR.md.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src import klasifikasi, muat_data, orbit, wilayah
from src.klasifikasi import KELOMPOK, WARNA_KELOMPOK

# ----------------------------------------------------------------------------
# 0. KONFIGURASI HALAMAN
# ----------------------------------------------------------------------------
st.set_page_config(page_title="Who Watches Indonesia", page_icon="🛰️", layout="wide")

WIB = timezone(timedelta(hours=7))
TEMPLATE = "plotly_dark"
DISCLAIMER = (
    "ℹ️ Seluruh data berasal dari **sumber publik**: elemen orbit (TLE) dari CelesTrak dan katalog GCAT "
    "untuk negara, operator, dan misi setiap satelit. Label \"militer\" atau \"pengintai\" mengikuti klasifikasi "
    "GCAT, bukan penilaian sendiri. Proyek ini bersifat edukatif dan portofolio pribadi, bukan dokumen resmi."
)
LANGKAH_MENIT = 1.0


def rapikan(fig: go.Figure, tinggi: int = 420) -> go.Figure:
    """Gaya seragam untuk semua grafik Plotly: latar gelap, grid tipis, legenda di atas."""
    fig.update_layout(
        template=TEMPLATE,
        height=tinggi,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=20, t=95, b=10),
        title=dict(y=0.99, yanchor="top", x=0, xanchor="left", font=dict(size=15)),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0, title=None),
        font=dict(family="system-ui, -apple-system, Segoe UI, sans-serif"),
    )
    fig.update_xaxes(showgrid=False, zeroline=False)
    fig.update_yaxes(gridcolor="#2a3242", zeroline=False)
    return fig


def wib(waktu) -> str:
    """Format waktu ke 'HH:MM WIB' (atau 'dd/mm HH:MM WIB' bila hari berbeda dari sekarang)."""
    if waktu is None or pd.isna(waktu):
        return "-"
    t = pd.Timestamp(waktu)
    t = t.tz_localize("UTC") if t.tzinfo is None else t
    t = t.tz_convert(WIB)
    return t.strftime("%H:%M WIB") if t.date() == datetime.now(WIB).date() else t.strftime("%d/%m %H:%M WIB")


# ----------------------------------------------------------------------------
# 1. MUAT DATA (di-cache 3 jam: TLE diperbarui CelesTrak beberapa kali sehari, lebih sering tidak perlu)
# ----------------------------------------------------------------------------
@st.cache_data(ttl=3 * 3600, show_spinner="Mengambil TLE dari CelesTrak...")
def muat_tabel_satelit():
    df, tle = muat_data.muat_semua()
    return df, tle.sumber, tle.diambil_pada, tle.pesan


@st.cache_data(ttl=3600, show_spinner="Menghitung lintasan 24 jam untuk ribuan satelit...")
def analisis_lintasan(df_subset: pd.DataFrame, mulai_iso: str, jam: int):
    """
    APA: propagasi semua satelit di df_subset setiap 1 menit selama `jam` jam, lalu hitung kapan
    titik sub-satelitnya berada di dalam poligon Indonesia.
    MENGAPA di-cache: ~1.600 satelit x 1.440 menit = 2,3 juta posisi; cukup sekali per jam.
    """
    mulai = datetime.fromisoformat(mulai_iso)
    waktu = orbit.rentang_waktu(mulai, jam, LANGKAH_MENIT)
    hasil = orbit.propagasi(df_subset, waktu)
    mask = wilayah.di_atas_indonesia(hasil["lat"], hasil["lon"])
    ringkas = orbit.hitung_lintasan(mask, waktu, LANGKAH_MENIT)
    ringkas.index = df_subset.index
    return ringkas, mask, waktu


df_semua, sumber_tle, waktu_tle, pesan_tle = muat_tabel_satelit()
sekarang = datetime.now(timezone.utc).replace(microsecond=0)
mulai_analisis = sekarang.replace(minute=sekarang.minute // 10 * 10, second=0)  # dibulatkan ke 10 menit agar cache terpakai

# ----------------------------------------------------------------------------
# 2. SIDEBAR
# ----------------------------------------------------------------------------
with st.sidebar:
    st.title("🛰️ Who Watches Indonesia")
    st.caption("Satelit Indonesia vs satelit asing di atas Nusantara, dihitung dari orbit publik.")

    st.subheader("Map layers")
    tampil_kelompok = [k for k in KELOMPOK if st.checkbox(k, value=(k != "Satelit asing lainnya" and k != "Belum terkatalog"))]
    area = st.radio("Area", ["Hanya di atas Indonesia", "Kawasan sekitar (85-150° BT)"], index=0)

    st.subheader("Analysis window")
    jam_analisis = st.select_slider("Jendela analisis (jam)", options=[6, 12, 24, 48], value=24)
    sertakan_militer_lain = st.checkbox(
        "Hitung juga satelit militer non-pengintai", value=False,
        help="Komunikasi dan navigasi militer (GPS, Beidou, WGS, dsb.) ikut dihitung di papan skor.",
    )
    st.caption("Lintasan dihitung setiap 1 menit dari waktu sekarang, dibulatkan ke 10 menit.")

    mode_belajar = st.toggle("🎓 Learning mode", value=False, help="Tampilkan rumus dan potongan kode di setiap bagian.")
    auto_refresh = st.toggle("🔄 Auto-refresh live map (30 s)", value=False)

    st.subheader("Data")
    st.caption(f"TLE: **{sumber_tle}**, {wib(waktu_tle)}  \nKatalog GCAT: dibangun {muat_data.tanggal_katalog()}")
    if pesan_tle:
        st.warning(pesan_tle, icon="⚠️")
    if st.button("Refresh TLE", width="stretch"):
        muat_tabel_satelit.clear()
        analisis_lintasan.clear()
        st.rerun()
    st.caption("Data publik. Lihat tab *Data & Sources*.")

# ----------------------------------------------------------------------------
# 3. HITUNG: posisi sekarang + lintasan 24 jam untuk satelit yang relevan
# ----------------------------------------------------------------------------
# APA: himpunan "pemantau" = semua yang bukan "Satelit asing lainnya" (komunikasi, navigasi, dsb.).
# MENGAPA: Starlink dan kawan-kawan berjumlah belasan ribu dan tidak mengamati permukaan Bumi;
# menghitung lintasannya hanya membuang waktu.
df_pemantau = df_semua[df_semua["kelompok"].isin(["Indonesia", "Militer asing", "Pengintai sipil & komersial asing"])]
ringkas, mask_lintasan, waktu_lintasan = analisis_lintasan(df_pemantau, mulai_analisis.isoformat(), jam_analisis)
df_lintasan = df_pemantau.join(ringkas)
df_lintasan["stasioner"] = (df_lintasan["jenis_orbit"] == "GEO") & (df_lintasan["jumlah_lintasan"] >= 1)
df_lewat = df_lintasan[(df_lintasan["jumlah_lintasan"] > 0) & ~df_lintasan["stasioner"]]
df_stasioner = df_lintasan[df_lintasan["stasioner"]]
# APA: papan skor hanya menghitung satelit yang "melihat atau mendengar" (pengintai), kecuali diminta lain.
# MENGAPA: GPS militer yang lewat tidak sedang mengamati siapa pun.
if not sertakan_militer_lain:
    df_lewat = df_lewat[df_lewat["pengintai"] | (df_lewat["kelompok"] == "Indonesia")]

pos_semua = orbit.posisi_saat(df_semua, sekarang)
pos_semua["di_atas_id"] = wilayah.di_atas_indonesia(pos_semua["lat"], pos_semua["lon"])
pos_semua["di_kawasan"] = wilayah.di_kawasan(pos_semua["lat"], pos_semua["lon"])
pos_di_atas = pos_semua[pos_semua["di_atas_id"]]

# ----------------------------------------------------------------------------
# 4. JUDUL + ANGKA RINGKASAN
# ----------------------------------------------------------------------------
st.title("🛰️ Who Watches Indonesia")
st.markdown(
    "**Look up. Someone is already looking down.** Peta live satelit di atas Indonesia: mana yang milik Indonesia, "
    "mana yang milik negara lain, dan negara mana yang satelit militer serta satelit pencitraannya paling sering "
    "melintas di atas wilayah kita."
)

n_asing_pemantau_now = int((pos_di_atas["kelompok"].isin(["Militer asing", "Pengintai sipil & komersial asing"])).sum())
negara_teratas = (
    df_lewat[df_lewat["kelompok"] != "Indonesia"].groupby("negara")["jumlah_lintasan"].sum().sort_values(ascending=False)
)
WARNA_OPERATOR = {"Militer": "#ffb000", "Komersial": "#4dd0e1", "Pemerintah sipil": "#9ecae1", "Akademik & amatir": "#a1d99b", "Tidak diketahui": "#5a6170"}
URUTAN_OPERATOR = list(WARNA_OPERATOR)
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Satelit aktif dipantau", f"{len(df_semua):,}".replace(",", "."), help="Semua objek di grup 'active' CelesTrak")
k2.metric("Di atas Indonesia sekarang", f"{len(pos_di_atas)}", help="Titik sub-satelit berada di dalam poligon Indonesia saat ini")
k3.metric("…yang militer / pengintai asing", f"{n_asing_pemantau_now}")
k4.metric("Satelit Indonesia aktif", f"{int((df_semua['kelompok'] == 'Indonesia').sum())}")
k5.metric(
    f"Paling sering melintas ({jam_analisis} jam)",
    f"{negara_teratas.index[0] if len(negara_teratas) else '-'}",
    help="Negara dengan jumlah lintasan satelit pengintai (pencitraan, radar, SIGINT, peringatan dini) terbanyak di jendela analisis",
)
st.caption(f"Posisi dihitung untuk {wib(sekarang)} ({sekarang:%H:%M} UTC). " + DISCLAIMER)

# ----------------------------------------------------------------------------
# 5. TAB
# ----------------------------------------------------------------------------
tab_peta, tab_siapa, tab_indo, tab_track, tab_data, tab_cara = st.tabs(
    ["🛰️ Live map", "👁️ Who's watching", "🇮🇩 Satelit Indonesia", "📡 Track a satellite", "📋 Data & Sources", "🧭 How it works"]
)


# ---------------------------------------------------------------- 5a. LIVE MAP
def gambar_peta(df_titik: pd.DataFrame, judul: str, jejak_df: pd.DataFrame | None = None, tinggi: int = 560,
                zoom: float | None = None) -> go.Figure:
    """Peta gelap dengan titik satelit (warna = kelompok) dan garis poligon Indonesia."""
    fig = px.scatter_map(
        df_titik,
        lat="lat", lon="lon",
        color="kelompok",
        color_discrete_map=WARNA_KELOMPOK,
        category_orders={"kelompok": KELOMPOK},
        hover_name="nama",
        hover_data={
            "lat": ":.2f", "lon": ":.2f", "kelompok": False,
            "negara": True, "operator": True, "misi": True, "alt_km": ":,.0f", "jenis_orbit": True,
        },
        labels={"negara": "Negara", "operator": "Operator", "misi": "Misi", "alt_km": "Ketinggian (km)", "jenis_orbit": "Orbit"},
        zoom=zoom if zoom is not None else (3.6 if area.startswith("Hanya") else 3.0),
        center={"lat": -2.5, "lon": 118.0},
        map_style="carto-darkmatter",
    )
    fig.update_traces(marker=dict(size=10, opacity=0.9))
    lon_p, lat_p = wilayah.poligon_lon_lat()
    fig.add_trace(go.Scattermap(lon=lon_p, lat=lat_p, mode="lines", line=dict(color="#e8e8e8", width=1.2), opacity=0.7,
                                name="Batas wilayah (sketsa)", hoverinfo="skip"))
    if jejak_df is not None and len(jejak_df):
        fig.add_trace(go.Scattermap(lon=jejak_df["lon"], lat=jejak_df["lat"], mode="lines",
                                    line=dict(color="#ff3b3b", width=2.5), name="Jejak darat", hoverinfo="skip"))
    fig.update_layout(height=tinggi, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="rgba(0,0,0,0)",
                      legend=dict(orientation="h", y=0.01, x=0.01, title=None, bgcolor="rgba(11,15,23,0.75)"))
    return fig


with tab_peta:
    @st.fragment(run_every="30s" if auto_refresh else None)
    def bagian_live_map():
        waktu_kini = datetime.now(timezone.utc).replace(microsecond=0)
        pos = orbit.posisi_saat(df_semua[df_semua["kelompok"].isin(tampil_kelompok)], waktu_kini)
        pos["di_atas_id"] = wilayah.di_atas_indonesia(pos["lat"], pos["lon"])
        pos["di_kawasan"] = wilayah.di_kawasan(pos["lat"], pos["lon"])
        df_titik = pos[pos["di_atas_id"]] if area.startswith("Hanya") else pos[pos["di_kawasan"]]

        c1, c2 = st.columns([3, 1])
        c1.subheader("Siapa yang sedang di atas kita?")
        c2.caption(f"🕒 {wib(waktu_kini)} · {len(df_titik)} satelit tampil")
        st.plotly_chart(gambar_peta(df_titik, "live"), width="stretch", key="peta_live")

        if len(df_titik) == 0:
            st.info("Tidak ada satelit dari kelompok yang dipilih di area ini saat ini. Coba aktifkan kelompok lain di sidebar.")
            return

        kiri, kanan = st.columns([1, 1])
        hitung_negara = (
            df_titik.groupby(["negara", "kelompok"]).size().reset_index(name="jumlah")
            .sort_values("jumlah", ascending=False)
        )
        urutan = hitung_negara.groupby("negara")["jumlah"].sum().sort_values(ascending=False).head(12).index.tolist()
        fig = px.bar(
            hitung_negara[hitung_negara["negara"].isin(urutan)], x="jumlah", y="negara", color="kelompok", orientation="h",
            color_discrete_map=WARNA_KELOMPOK, category_orders={"negara": urutan, "kelompok": KELOMPOK},
            title="Per negara, saat ini", labels={"jumlah": "Jumlah satelit", "negara": ""},
        )
        kiri.plotly_chart(rapikan(fig, 380), width="stretch", key="bar_negara_live")

        tabel = df_titik.sort_values(["kelompok", "negara", "nama"])[
            ["bendera", "nama", "negara", "operator", "misi", "jenis_orbit", "alt_km", "lat", "lon"]
        ].rename(columns={"bendera": "", "nama": "Satelit", "negara": "Negara", "operator": "Operator", "misi": "Misi",
                          "jenis_orbit": "Orbit", "alt_km": "Tinggi (km)", "lat": "Lat", "lon": "Lon"})
        kanan.markdown("**Daftar satelit yang tampil**")
        kanan.dataframe(tabel, hide_index=True, height=340,
                        column_config={"Tinggi (km)": st.column_config.NumberColumn(format="%.0f"),
                                       "Lat": st.column_config.NumberColumn(format="%.2f"),
                                       "Lon": st.column_config.NumberColumn(format="%.2f")})

    bagian_live_map()

    st.info(
        "💡 **Cara membaca peta.** Titik adalah *titik sub-satelit*: lokasi tepat di bawah satelit. Satelit orbit rendah "
        "(LEO) bergerak ±7,5 km/detik sehingga titiknya berpindah setiap kali halaman dimuat ulang; satelit GEO diam "
        "di atas khatulistiwa pada bujur tetap, itulah sebabnya satelit komunikasi Indonesia berjajar di garis khatulistiwa. "
        "Satelit pencitraan sebenarnya bisa memotret hingga ratusan km di samping jalurnya, jadi \"di atas Indonesia\" "
        "di sini adalah definisi yang ketat."
    )
    if mode_belajar:
        with st.expander("🎓 Dari TLE ke titik di peta"):
            st.markdown(
                """
Setiap satelit diwakili dua baris teks bernama **TLE** (Two-Line Element set), misalnya:

```
TELKOM 3S
1 41944U 17007A   26306.52345678  .00000123  00000+0  00000+0 0  9991
2 41944   0.0211 265.1234 0002345 123.4567 236.5432  1.00271234 35567
```

Baris 2 menyimpan bentuk orbit: inklinasi (`0.0211°`, hampir sejajar khatulistiwa), eksentrisitas, dan
*mean motion* (`1.0027` putaran per hari = geostasioner). Model **SGP4** mengubah angka-angka itu menjadi
posisi x, y, z pada waktu mana pun. Posisinya dinyatakan dalam kerangka yang tidak ikut berputar dengan Bumi,
sehingga perlu diputar sebesar sudut **GMST** (sudut rotasi Bumi saat itu) sebelum diubah ke lintang dan bujur.

```python
e, r, v = SatrecArray(satrecs).sgp4(jd, fr)       # (n_satelit, n_waktu, 3) km, kerangka TEME
lat, lon, alt = orbit.teme_ke_geodetik(r, jd+fr)  # putar dengan GMST, lalu WGS84
di_atas = wilayah.di_atas_indonesia(lat, lon)     # ray casting ke poligon
```
Kode lengkapnya ada di `src/orbit.py` dan `src/wilayah.py`, keduanya diuji di `tests/`.
"""
            )

# ---------------------------------------------------------------- 5b. WHO'S WATCHING
with tab_siapa:
    st.subheader(f"Negara mana yang paling sering melintas di atas Indonesia? ({jam_analisis} jam ke depan)")
    st.caption(
        "Yang dihitung: satelit **pengintai** (pencitraan optik, radar, intai sinyal, peringatan dini), militer maupun sipil/komersial"
        + (", ditambah satelit militer lain (komunikasi, navigasi)" if sertakan_militer_lain else "")
        + ". Satu lintasan = satu kali titik sub-satelit masuk poligon Indonesia. Satelit GEO yang diam di atas wilayah dihitung terpisah."
    )
    if len(df_lewat) == 0:
        st.warning("Tidak ada lintasan yang terhitung. Coba perlebar jendela analisis.")
    else:
        asing = df_lewat[df_lewat["kelompok"] != "Indonesia"]
        per_negara = asing.groupby(["negara", "operator"])["jumlah_lintasan"].sum().reset_index()
        urutan = per_negara.groupby("negara")["jumlah_lintasan"].sum().sort_values(ascending=False).head(15).index.tolist()
        fig = px.bar(
            per_negara[per_negara["negara"].isin(urutan)], x="jumlah_lintasan", y="negara", color="operator", orientation="h",
            color_discrete_map=WARNA_OPERATOR, category_orders={"negara": urutan, "operator": URUTAN_OPERATOR},
            title=f"Jumlah lintasan di atas Indonesia, {jam_analisis} jam", labels={"jumlah_lintasan": "Lintasan", "negara": ""},
            text="jumlah_lintasan",
        )
        fig.update_traces(textposition="inside")
        c1, c2 = st.columns([3, 2])
        c1.plotly_chart(rapikan(fig, 480), width="stretch")

        per_misi = asing.groupby(["misi", "operator"])["jumlah_lintasan"].sum().reset_index()
        fig2 = px.bar(
            per_misi, x="jumlah_lintasan", y="misi", color="operator", orientation="h",
            title="Per jenis misi dan operator", color_discrete_map=WARNA_OPERATOR, category_orders={"operator": URUTAN_OPERATOR},
            labels={"jumlah_lintasan": "Lintasan", "misi": "", "operator": "Operator"},
        )
        c2.plotly_chart(rapikan(fig2, 480), width="stretch")

        # Jumlah satelit unik vs lintasan: supaya adil, tampilkan keduanya
        ringkas_negara = (
            asing.groupby("negara")
            .agg(satelit=("norad", "nunique"), lintasan=("jumlah_lintasan", "sum"), menit=("menit_di_atas", "sum"),
                 militer=("operator", lambda s: int((s == "Militer").sum())))
            .sort_values("lintasan", ascending=False)
        )
        ringkas_negara["menit_per_jam"] = ringkas_negara["menit"] / jam_analisis
        st.markdown("**Papan skor**")
        st.dataframe(
            ringkas_negara.reset_index()[["negara", "satelit", "militer", "lintasan", "menit", "menit_per_jam"]].rename(columns={
                "negara": "Negara", "satelit": "Satelit yang melintas", "militer": "…di antaranya militer",
                "lintasan": "Lintasan", "menit": "Total menit-satelit di atas wilayah", "menit_per_jam": "Menit-satelit per jam",
            }),
            hide_index=True, width="stretch",
            column_config={"Menit-satelit per jam": st.column_config.NumberColumn(format="%.1f", help="Rata-rata jumlah menit satelit negara itu berada di atas wilayah, per jam"),
                           "Total menit-satelit di atas wilayah": st.column_config.NumberColumn(format="%.0f")},
        )

        # Jam sibuk: kapan lintasan dimulai (WIB), untuk 8 negara teratas
        st.markdown("**Jam berapa mereka lewat?** (jam mulai lintasan, WIB)")
        idx_asing = df_pemantau.index.get_indexer(asing.index)
        m = mask_lintasan[idx_asing]
        tepi = m & ~np.concatenate([np.zeros((m.shape[0], 1), bool), m[:, :-1]], axis=1)
        jam_wib = ((waktu_lintasan.hour + 7) % 24).to_numpy()
        baris_heat = []
        for negara in urutan[:8]:
            sel = (asing["negara"] == negara).to_numpy()
            hit = tepi[sel].sum(axis=0)
            per_jam = np.bincount(jam_wib, weights=hit, minlength=24)
            baris_heat.append(per_jam)
        heat = np.array(baris_heat)
        fig3 = go.Figure(go.Heatmap(z=heat, x=[f"{h:02d}" for h in range(24)], y=urutan[:8], colorscale="YlOrRd",
                                    hovertemplate="%{y} · %{x}:00 WIB · %{z} lintasan<extra></extra>"))
        fig3.update_layout(title="Lintasan per jam (WIB)", xaxis_title="Jam mulai lintasan", yaxis_autorange="reversed")
        st.plotly_chart(rapikan(fig3, 360), width="stretch")

        st.info(
            "💡 **Pola yang terlihat.** Satelit pencitraan hampir selalu memakai orbit *sun-synchronous*: mereka melintasi "
            "setiap tempat pada jam matahari yang sama (umumnya pukul 10-11 pagi dan 22-23 malam waktu setempat) supaya "
            "pencahayaan fotonya konsisten. Itulah sebabnya kolom pagi dan malam pada heatmap lebih gelap. Satelit intai "
            "sinyal tidak butuh cahaya, jadi lintasannya lebih merata."
        )

        if len(df_stasioner):
            st.markdown("**Diam permanen di atas wilayah (GEO)**")
            st.caption("Satelit geostasioner yang titik sub-satelitnya berada di dalam poligon Indonesia. Mereka tidak \"melintas\", mereka menetap.")
            st.dataframe(
                df_stasioner.sort_values(["kelompok", "negara"])[["bendera", "nama", "negara", "operator", "misi", "program"]]
                .rename(columns={"bendera": "", "nama": "Satelit", "negara": "Negara", "operator": "Operator", "misi": "Misi", "program": "Program"}),
                hide_index=True, width="stretch",
            )

        st.markdown("**Rincian per satelit**")
        pilih_negara = st.multiselect("Filter negara", urutan, default=urutan[:5], key="filter_negara_rinci")
        rinci = asing[asing["negara"].isin(pilih_negara)].sort_values("jumlah_lintasan", ascending=False)
        st.dataframe(
            rinci.assign(berikutnya=rinci["lintasan_pertama"].map(wib))[
                ["bendera", "nama", "negara", "operator", "misi", "program", "jumlah_lintasan", "menit_di_atas", "berikutnya"]
            ].rename(columns={"bendera": "", "nama": "Satelit", "negara": "Negara", "operator": "Operator", "misi": "Misi",
                              "program": "Program", "jumlah_lintasan": "Lintasan", "menit_di_atas": "Menit", "berikutnya": "Lintasan berikutnya"}),
            hide_index=True, width="stretch", height=420,
        )

    if mode_belajar:
        with st.expander("🎓 Bagaimana lintasan dihitung"):
            st.markdown(
                """
1. Ambil semua satelit berkelompok *Indonesia*, *Militer asing*, dan *Pengintai sipil & komersial asing* (sekitar 1.600).
2. Buat deret waktu setiap 1 menit sepanjang jendela analisis: 24 jam = 1.440 titik waktu.
3. Propagasi semuanya sekaligus dengan `SatrecArray.sgp4` → matriks posisi berukuran (1.600 × 1.440 × 3).
4. Uji setiap posisi terhadap poligon Indonesia → matriks boolean `mask` (1.600 × 1.440).
5. Hitung *tepi naik* (False → True) per baris: itu jumlah lintasan. Jumlah True × 1 menit = total menit di atas wilayah.

```python
sebelumnya = np.concatenate([np.zeros((n, 1), bool), mask[:, :-1]], axis=1)
jumlah_lintasan = (mask & ~sebelumnya).sum(axis=1)
```
Dengan langkah 1 menit, lintasan LEO yang hanya menyentuh ujung poligon kurang dari 1 menit bisa terlewat.
Itu kompromi yang disengaja supaya seluruh perhitungan selesai dalam 2-3 detik.
"""
            )

# ---------------------------------------------------------------- 5c. SATELIT INDONESIA
with tab_indo:
    st.subheader("Satelit Indonesia yang masih aktif")
    df_id = df_semua[df_semua["kelompok"] == "Indonesia"].merge(
        muat_data.muat_catatan_indonesia(), on="norad", how="left", suffixes=("", "_catatan")
    )
    pos_id = pos_semua[pos_semua["kelompok"] == "Indonesia"][["norad", "lat", "lon", "alt_km"]]
    df_id = df_id.merge(pos_id, on="norad", how="left")

    c1, c2, c3 = st.columns(3)
    c1.metric("Satelit aktif (ada TLE)", len(df_id))
    c2.metric("Komunikasi (GEO)", int((df_id["misi"] == "Komunikasi").sum()))
    c3.metric("Observasi Bumi (LEO)", int(df_id["pengintai"].sum()))

    st.plotly_chart(gambar_peta(df_id.assign(kelompok="Indonesia").dropna(subset=["lat"]), "indonesia", tinggi=380, zoom=3.0),
                    width="stretch", key="peta_indonesia")
    st.caption("Tujuh satelit komunikasi berjajar di khatulistiwa (GEO, ±35.800 km); dua satelit LAPAN melesat di orbit rendah dan hanya sesekali berada di atas Indonesia.")

    tabel_id = df_id[["bendera", "nama_catatan", "operator_catatan", "fungsi", "orbit", "diluncurkan", "catatan", "sumber", "url_sumber"]].rename(columns={
        "bendera": "", "nama_catatan": "Satelit", "operator_catatan": "Operator", "fungsi": "Fungsi", "orbit": "Orbit",
        "diluncurkan": "Diluncurkan", "catatan": "Catatan", "sumber": "Sumber", "url_sumber": "URL",
    })
    tabel_id["Satelit"] = tabel_id["Satelit"].fillna(df_id["nama"])
    st.dataframe(tabel_id, hide_index=True, width="stretch", column_config={"URL": st.column_config.LinkColumn()})

    st.markdown("**Indonesia dibandingkan tetangga** (satelit aktif dengan TLE publik, per kelompok)")
    tetangga = ["ID", "MY", "SG", "T", "VN", "PH", "AU", "IN", "KR", "J", "CN"]
    df_tetangga = df_semua[df_semua["negara_kode"].isin(tetangga)].copy()
    df_tetangga["kelompok_banding"] = np.select(
        [df_tetangga["operator"] == "Militer", df_tetangga["pengintai"]],
        ["Militer", "Pengintai sipil & komersial"], "Lainnya (komunikasi, navigasi, dsb.)",
    )
    banding = df_tetangga.groupby(["negara", "kelompok_banding"]).size().reset_index(name="jumlah")
    urutan_b = banding.groupby("negara")["jumlah"].sum().sort_values(ascending=False).index.tolist()
    fig = px.bar(
        banding, x="jumlah", y="negara", color="kelompok_banding", orientation="h", log_x=True, barmode="group",
        category_orders={"negara": urutan_b, "kelompok_banding": ["Militer", "Pengintai sipil & komersial", "Lainnya (komunikasi, navigasi, dsb.)"]},
        color_discrete_map={"Militer": "#ffb000", "Pengintai sipil & komersial": "#4dd0e1", "Lainnya (komunikasi, navigasi, dsb.)": "#55607a"},
        title="Jumlah satelit aktif per negara (skala log)", labels={"jumlah": "Satelit aktif", "negara": "", "kelompok_banding": ""},
        text="jumlah",
    )
    fig.update_traces(textposition="outside")
    st.plotly_chart(rapikan(fig, 560), width="stretch")
    st.info(
        "💡 **Yang menonjol.** Semua satelit Indonesia yang aktif adalah satelit komunikasi komersial di GEO, ditambah dua satelit "
        "observasi LAPAN. Menurut katalog GCAT tidak ada satu pun satelit Indonesia yang dioperasikan militer, sementara "
        "China, Amerika Serikat, dan Rusia masing-masing mengoperasikan ratusan. Pengamatan dari orbit di atas Indonesia hampir "
        "seluruhnya dilakukan oleh satelit negara lain, sipil maupun militer."
    )
    if mode_belajar:
        with st.expander("🎓 Mengapa satelit GEO terlihat diam"):
            st.markdown(
                """
Periode orbit mengikuti hukum Kepler ketiga: makin tinggi orbit, makin lambat putarannya. Pada ketinggian
**35.786 km** satu putaran persis 23 jam 56 menit, sama dengan rotasi Bumi, sehingga satelit tampak diam di
satu bujur. Dari TLE, ciri GEO adalah *mean motion* ≈ 1,0027 putaran/hari dan inklinasi mendekati 0°.

```python
def jenis_orbit(mean_motion, inklinasi_deg):
    if 0.9 <= mean_motion <= 1.1:
        return "GEO" if inklinasi_deg < 10 else "GSO miring"
    ...
```
Satelit LEO LAPAN-A3 di 500 km menempuh satu putaran dalam ±95 menit (≈15 putaran per hari).
"""
            )

# ---------------------------------------------------------------- 5d. TRACK A SATELLITE
with tab_track:
    st.subheader("Lacak satu satelit")
    kandidat = df_pemantau.sort_values(["kelompok", "negara", "nama"])
    label = kandidat["bendera"] + " " + kandidat["nama"] + " · " + kandidat["negara"] + " · " + kandidat["misi"]
    default_idx = int(np.argmax((kandidat["nama"] == "LAPAN-A3").to_numpy())) if (kandidat["nama"] == "LAPAN-A3").any() else 0
    pilihan = st.selectbox("Pilih satelit (ketik untuk mencari)", options=list(range(len(kandidat))), index=default_idx,
                           format_func=lambda i: label.iloc[i])
    sat = kandidat.iloc[pilihan]
    menit_jejak = st.slider("Panjang jejak darat ke depan (menit)", 30, 360, 100, step=10)

    jejak_df = orbit.potong_di_garis_tanggal(orbit.jejak(sat["line1"], sat["line2"], sekarang, menit_jejak, 30))
    pos_sat = pos_semua[pos_semua["norad"] == sat["norad"]]
    titik = pos_sat.assign(kelompok=sat["kelompok"]) if len(pos_sat) else pd.DataFrame(columns=pos_semua.columns)
    c1, c2 = st.columns([3, 1])
    with c1:
        st.plotly_chart(gambar_peta(titik, "track", jejak_df=jejak_df, tinggi=480, zoom=1.3), width="stretch", key="peta_track")
    with c2:
        st.markdown(f"### {sat['bendera']} {sat['nama']}")
        st.markdown(
            f"**Negara:** {sat['negara']}  \n**Operator:** {sat['operator']} ({sat['pemilik']})  \n**Misi:** {sat['misi']}  \n"
            f"**Program:** {sat['program']}  \n**Diluncurkan:** {sat['tanggal_luncur']}  \n**NORAD:** {sat['norad']}  \n"
            f"**Orbit:** {sat['jenis_orbit']}, inklinasi {sat['inklinasi_deg']:.1f}°, periode {sat['periode_menit']:.0f} menit  \n"
            f"**Epoch TLE:** {wib(sat['epoch'])}"
        )
        if len(pos_sat):
            st.markdown(f"**Sekarang:** lat {pos_sat['lat'].iloc[0]:.2f}, lon {pos_sat['lon'].iloc[0]:.2f}, tinggi {pos_sat['alt_km'].iloc[0]:,.0f} km")

    idx_sat = df_pemantau.index.get_loc(sat.name)
    jadwal = orbit.daftar_lintasan(mask_lintasan[idx_sat], waktu_lintasan, LANGKAH_MENIT)
    st.markdown(f"**Jadwal lintasan di atas Indonesia, {jam_analisis} jam ke depan** ({len(jadwal)} lintasan)")
    if len(jadwal):
        st.dataframe(
            jadwal.assign(Mulai=jadwal["mulai"].map(wib), Selesai=jadwal["selesai"].map(wib))[["Mulai", "Selesai", "durasi_menit"]]
            .rename(columns={"durasi_menit": "Durasi (menit)"}),
            hide_index=True, width="stretch",
        )
    else:
        st.caption("Tidak melintasi poligon Indonesia dalam jendela ini.")
    if mode_belajar:
        with st.expander("🎓 Mengapa jejak darat berbentuk gelombang"):
            st.markdown(
                """
Orbit satelit adalah lingkaran miring di ruang angkasa, tetapi Bumi berputar di bawahnya. Proyeksi lingkaran
miring ke peta datar menghasilkan kurva sinus dengan amplitudo = inklinasi (satelit berinklinasi 97° mencapai
lintang ±83°). Karena Bumi berputar ke timur sebesar ±22,5° setiap 90 menit, setiap putaran berikutnya
bergeser ke barat. Inilah alasan satelit LEO hanya "mampir" di atas Indonesia beberapa kali sehari.
"""
            )

# ---------------------------------------------------------------- 5e. DATA & SOURCES
with tab_data:
    st.subheader("Data & sumber")
    st.markdown(
        f"""
| Data | Sumber | Diperbarui | Lisensi |
|---|---|---|---|
| Elemen orbit (TLE) {f"{len(df_semua):,}".replace(",", ".")} satelit aktif | [CelesTrak](https://celestrak.org/NORAD/elements/) grup *active* | {sumber_tle}, {wib(waktu_tle)}; cadangan di `data/tle_cadangan.txt` | bebas dipakai dengan atribusi |
| Negara, operator, misi per satelit | [GCAT](https://planet4589.org/space/gcat/) (Jonathan McDowell), tabel *satcat* + *psatcat* | katalog dibangun {muat_data.tanggal_katalog()} (`scripts/bangun_katalog.py`) | CC BY 4.0 |
| Catatan satelit Indonesia | Wikipedia, per baris ada tautan | `data/satelit_indonesia.csv` | CC BY-SA |
| Batas wilayah | sketsa poligon sendiri di `src/wilayah.py` | - | - |
"""
    )
    st.markdown("**Arti kelompok**")
    st.markdown(
        """
| Kelompok | Definisi (dari kode GCAT) |
|---|---|
| 🇮🇩 Indonesia | Negara pemilik = Indonesia, apa pun misinya |
| Militer asing | Kelas operator **D** (defense) menurut GCAT, apa pun misinya: pencitraan, SIGINT, komunikasi militer, navigasi militer |
| Pengintai sipil & komersial asing | Kelas A/B/C dengan misi IMG (pencitraan optik), IMG-R (radar), SIG (intai sinyal), atau EW (peringatan dini) |
| Satelit asing lainnya | Sisanya: komunikasi (termasuk Starlink, OneWeb), navigasi, cuaca, sains, uji teknologi |
| Belum terkatalog | Ada di TLE CelesTrak tetapi belum ada di katalog GCAT (biasanya baru diluncurkan); sebagian ditebak dari pola nama |
"""
    )
    st.markdown("**Keterbatasan yang perlu diketahui**")
    st.markdown(
        """
- **"Di atas Indonesia" = titik sub-satelit di dalam poligon sketsa.** Satelit pencitraan bisa melihat ratusan km ke samping,
  jadi jumlah lintasan di sini adalah batas bawah dari "berapa kali Indonesia bisa dipotret".
- **Poligon adalah perkiraan** (simpangan 50-100 km), Timor-Leste ikut terlingkupi, dan bukan batas resmi.
- **TLE punya umur.** Akurasi posisi SGP4 menurun beberapa km per hari setelah epoch; TLE diperbarui CelesTrak harian.
- **Satelit militer yang paling rahasia tidak punya TLE publik** (misalnya sebagian satelit NRO Amerika). Yang terlihat di sini
  hanya yang dilacak dan dipublikasikan.
- **Klasifikasi mengikuti GCAT.** Satelit dual-use (misalnya Gaofen, KOMPSAT) bisa masuk kelas sipil meskipun citranya dipakai militer.
- Melintas di atas suatu negara **bukan pelanggaran**: ruang angkasa tidak tunduk pada kedaulatan wilayah (Outer Space Treaty 1967).
"""
    )
    st.markdown("**Unduh data yang sedang dipakai**")
    kolom_unduh = ["norad", "nama", "negara", "operator", "misi", "kelompok", "program", "tanggal_luncur", "jenis_orbit", "inklinasi_deg", "periode_menit", "epoch"]
    c1, c2 = st.columns(2)
    c1.download_button("⬇️ Semua satelit aktif + klasifikasi (CSV)", df_semua[kolom_unduh].to_csv(index=False).encode(),
                       "satelit_aktif_klasifikasi.csv", "text/csv", width="stretch")
    c2.download_button(f"⬇️ Hasil lintasan {jam_analisis} jam (CSV)",
                       df_lintasan[kolom_unduh + ["jumlah_lintasan", "menit_di_atas", "lintasan_pertama"]].to_csv(index=False).encode(),
                       "lintasan_di_atas_indonesia.csv", "text/csv", width="stretch")
    st.markdown("**Tabel lengkap satelit aktif**")
    st.dataframe(df_semua[kolom_unduh].sort_values(["kelompok", "negara", "nama"]), hide_index=True, height=400, width="stretch")

# ---------------------------------------------------------------- 5f. HOW IT WORKS
with tab_cara:
    st.subheader("Alur data → orbit → peta")
    st.graphviz_chart(
        """
digraph G {
  rankdir=LR; bgcolor="transparent";
  node [shape=box, style="rounded,filled", fillcolor="#161c28", fontcolor="#e8e8e8", color="#55607a", fontname="sans-serif", fontsize=11];
  edge [color="#8899aa", fontcolor="#aab4c4"];
  tle  [label="CelesTrak\\nTLE semua satelit aktif\\n(live, cadangan di data/)"];
  gcat [label="GCAT\\nnegara · operator · misi\\n(data/katalog_satelit.csv)"];
  muat [label="src/muat_data.py\\ngabung TLE + katalog"];
  klas [label="src/klasifikasi.py\\nkode GCAT -> kelompok"];
  orb  [label="src/orbit.py\\nSGP4 -> TEME -> GMST -> lat/lon"];
  wil  [label="src/wilayah.py\\npoligon Indonesia, ray casting"];
  app  [label="app.py\\nsidebar, tab, grafik Plotly"];
  user [label="Browser\\n(Streamlit)", fillcolor="#3a2f10"];
  tle -> muat; gcat -> muat; muat -> klas -> app; muat -> orb -> wil -> app; app -> user; user -> app [label="klik -> rerun", fontsize=9];
}
"""
    )
    st.markdown(
        """
| Langkah | File | Yang terjadi |
|---|---|---|
| 1 | `src/muat_data.py` | Unduh TLE grup *active* dari CelesTrak (±16.000 objek). Gagal? Pakai `data/tle_cadangan.txt`. |
| 2 | `scripts/bangun_katalog.py` | Sekali-sekali: unduh GCAT, saring payload, simpan negara/operator/misi per nomor NORAD. |
| 3 | `src/klasifikasi.py` | Kelas D → Militer; misi IMG/IMG-R/SIG/EW → pengintai; negara ID → Indonesia. |
| 4 | `src/orbit.py` | **SGP4** menghitung posisi; **GMST** memutar ke kerangka Bumi; **WGS84** memberi lintang-bujur-tinggi. |
| 5 | `src/wilayah.py` | Uji titik-di-dalam-poligon (ray casting) untuk jutaan titik sekaligus dengan numpy. |
| 6 | `app.py` | Posisi sekarang untuk peta live; matriks 1.600 × 1.440 menit untuk papan skor dan jadwal lintasan. |

**Konsep yang dipakai**

- **TLE / SGP4**: format standar NORAD untuk orbit dan model propagasinya; akurat ±1 km dekat epoch.
- **Kerangka koordinat**: TEME (tidak berputar bersama Bumi) → ECEF (menempel pada Bumi) lewat sudut GMST.
- **Lintang geodetik WGS84**: Bumi pepat, sehingga konversi dari x,y,z ke lintang butuh iterasi kecil.
- **Titik sub-satelit & jejak darat**: proyeksi satelit ke permukaan dan kurvanya seiring waktu.
- **Orbit sun-synchronous**: inklinasi ±98° yang membuat satelit lewat pada jam matahari yang sama setiap hari.
- **Vektorisasi numpy**: semua satelit × semua waktu dihitung sebagai satu matriks, bukan perulangan Python.
"""
    )
    st.caption(DISCLAIMER)
