# 🏋️ Latihan

Diurutkan dari yang mudah ke yang lebih menantang. Setiap latihan dilengkapi petunjuk dan kunci jawaban yang dapat
dibuka. Usahakan mencoba minimal 10 menit sebelum membuka kunci. Setelah setiap latihan, jalankan
`python -m pytest tests/` dan `streamlit run app.py`.

---

### Latihan 1 — Ganti warna kelompok ⭐

Warna "Militer asing" saat ini amber (`#ffb000`). Ubah menjadi merah muda `#ff6ec7` dan pastikan peta,
legenda, dan grafik batang ikut berubah tanpa menyentuh `app.py`.

<details><summary>Petunjuk</summary>
Semua warna kelompok didefinisikan di satu tempat: `WARNA_KELOMPOK` di `src/klasifikasi.py`. `app.py` hanya mengimpornya.
</details>

<details><summary>Kunci</summary>

```python
WARNA_KELOMPOK = {
    "Indonesia": "#ff3b3b",
    "Militer asing": "#ff6ec7",
    ...
}
```
Karena peta memakai `color_discrete_map=WARNA_KELOMPOK`, perubahan satu baris berlaku di semua grafik.
</details>

---

### Latihan 2 — Jendela analisis 72 jam ⭐

Slider jendela analisis hanya menawarkan 6/12/24/48 jam. Tambahkan pilihan 72 jam, lalu perhatikan berapa lama
perhitungan pertama (sebelum di-cache) di laptop kamu.

<details><summary>Petunjuk</summary>
Cari `st.select_slider("Jendela analisis (jam)"` di `app.py`. Fungsi `analisis_lintasan` tidak perlu diubah karena
menerima `jam` sebagai argumen.
</details>

<details><summary>Kunci</summary>

```python
jam_analisis = st.select_slider("Jendela analisis (jam)", options=[6, 12, 24, 48, 72], value=24)
```
Matriks posisinya menjadi 1.600 × 4.320 ≈ 7 juta sel; masih di bawah 10 detik, tetapi ini batas yang masuk akal
untuk layanan gratis.
</details>

---

### Latihan 3 — Satelit mana yang paling lama di atas Indonesia? ⭐⭐

Tanpa Streamlit, di Python, cari 10 satelit LEO (bukan GEO) dengan total menit di atas Indonesia terbanyak dalam
24 jam ke depan, beserta negara dan misinya.

<details><summary>Petunjuk</summary>
Gunakan `muat_data.muat_semua()`, saring `jenis_orbit == "LEO"`, lalu `orbit.rentang_waktu`, `orbit.propagasi`,
`wilayah.di_atas_indonesia`, dan `orbit.hitung_lintasan`. Gabungkan hasilnya dengan `df.join(...)`.
</details>

<details><summary>Kunci</summary>

```python
from datetime import datetime, timezone
from src import muat_data, orbit, wilayah

df, _ = muat_data.muat_semua()
leo = df[df["jenis_orbit"] == "LEO"].reset_index(drop=True)
waktu = orbit.rentang_waktu(datetime.now(timezone.utc), 24, 1)
h = orbit.propagasi(leo, waktu)
mask = wilayah.di_atas_indonesia(h["lat"], h["lon"])
hasil = leo.join(orbit.hitung_lintasan(mask, waktu, 1))
print(hasil.sort_values("menit_di_atas", ascending=False)[["nama", "negara", "misi", "menit_di_atas"]].head(10))
```
Satelit dengan inklinasi rendah (misalnya ISS, 51,6°, atau satelit ekuatorial) cenderung menang karena jalurnya
lebih sering memotong wilayah khatulistiwa.
</details>

---

### Latihan 4 — Uji poligon dengan kota baru ⭐⭐

Tambahkan tes di `tests/test_wilayah.py` yang memastikan **Sabang** (5,89 LU, 95,32 BT) dan **Merauke**
(-8,49 LS, 140,40 BT) di dalam poligon, serta **Dili** (-8,56 LS, 125,57 BT) dan **Bandar Seri Begawan**
(4,94 LU, 114,95 BT) di luar. Salah satu dari empat kota itu akan gagal. Mana, dan mengapa?

<details><summary>Petunjuk</summary>
Baca docstring `src/wilayah.py` tentang Timor-Leste.
</details>

<details><summary>Kunci</summary>

Dili gagal: Timor-Leste berada di tengah poligon sketsa sehingga dianggap "di dalam". Dua jalan keluar:
(1) tandai tes itu dengan `pytest.mark.xfail(reason="Timor-Leste ikut terlingkupi poligon sketsa")`, atau
(2) perbaiki poligon dengan menambahkan lekukan di sekitar 124,0-127,3° BT, -8,1 sampai -9,5° LS, lalu pastikan
Kupang dan Atambua tetap di dalam. Pilihan kedua lebih bermanfaat tetapi butuh beberapa titik tambahan.
</details>

---

### Latihan 5 — Ekspor jadwal lintasan ke iCalendar ⭐⭐

Di tab *Track a satellite*, tambahkan tombol download yang menghasilkan file `.ics` berisi setiap lintasan
sebagai event, supaya bisa dimasukkan ke Google Calendar.

<details><summary>Petunjuk</summary>
Format iCalendar sederhana: header `BEGIN:VCALENDAR`, lalu tiap event `BEGIN:VEVENT` / `DTSTART:20261103T021400Z` /
`DTEND:...` / `SUMMARY:...` / `END:VEVENT`, ditutup `END:VCALENDAR`. DataFrame `jadwal` sudah punya kolom `mulai`
dan `selesai` (UTC, tanpa tzinfo).
</details>

<details><summary>Kunci</summary>

```python
def ke_ics(jadwal, nama):
    baris = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//who-watches-indonesia//ID"]
    for _, r in jadwal.iterrows():
        baris += ["BEGIN:VEVENT",
                  f"DTSTART:{r['mulai']:%Y%m%dT%H%M%SZ}",
                  f"DTEND:{r['selesai']:%Y%m%dT%H%M%SZ}",
                  f"SUMMARY:{nama} di atas Indonesia",
                  "END:VEVENT"]
    baris.append("END:VCALENDAR")
    return "\r\n".join(baris).encode()

st.download_button("⬇️ Jadwal (.ics)", ke_ics(jadwal, sat["nama"]), f"{sat['norad']}.ics", "text/calendar")
```
</details>

---

### Latihan 6 — Lebar sapuan (swath) ⭐⭐⭐

Definisi "di atas Indonesia" saat ini ketat: titik sub-satelit harus di dalam poligon. Satelit pencitraan dengan
sapuan 300 km sebenarnya sudah "melihat" Indonesia saat jalurnya 150 km di luar batas. Ubah `analisis_lintasan`
supaya menerima parameter `lebar_km` dan menganggap satelit "di atas" bila jaraknya ke poligon ≤ `lebar_km / 2`.

<details><summary>Petunjuk</summary>
Cara paling sederhana tanpa pustaka GIS: perbesar poligon. Hitung pusat poligon, lalu geser setiap titik menjauh
dari pusat sejauh `lebar_km/2` (1° lintang ≈ 111 km, 1° bujur ≈ 111 km × cos(lintang)). Hasilnya tidak persis
*buffer* geometris, tetapi cukup untuk poligon sekasar ini. Versi yang benar memakai `shapely`:
`Polygon(...).buffer(derajat)`.
</details>

<details><summary>Kunci</summary>

```python
def poligon_diperbesar(poligon, lebar_km):
    lon_c = sum(p[0] for p in poligon) / len(poligon)
    lat_c = sum(p[1] for p in poligon) / len(poligon)
    hasil = []
    for lon, lat in poligon:
        d_lat = lat - lat_c
        d_lon = lon - lon_c
        jarak = (d_lat**2 + d_lon**2) ** 0.5 or 1e-9
        skala_deg = (lebar_km / 2) / 111.0
        hasil.append((lon + d_lon / jarak * skala_deg, lat + d_lat / jarak * skala_deg))
    return hasil

mask = wilayah.di_dalam_poligon(h["lat"], h["lon"], poligon_diperbesar(wilayah.POLIGON_INDONESIA, 300))
```
Bandingkan papan skor sebelum dan sesudah: jumlah lintasan naik 30-50%, dan urutan negara biasanya tidak berubah.
</details>

---

### Latihan 7 — Tren mingguan ⭐⭐⭐

Buat skrip `scripts/catat_harian.py` yang setiap kali dijalankan menghitung papan skor 24 jam dan menambahkan satu
baris per negara ke `data/riwayat_papan_skor.csv` (tanggal, negara, satelit, lintasan, menit). Jalankan tujuh hari
berturut-turut (atau lewat GitHub Actions terjadwal), lalu buat tab baru "Trend" yang menggambar garis per negara.

<details><summary>Petunjuk</summary>
Potongan dari Latihan 3 sudah 80% jadi. Untuk GitHub Actions, contoh cron: `0 1 * * *` (pukul 08:00 WIB), dengan
langkah `pip install -r requirements.txt`, `python scripts/catat_harian.py`, lalu `git commit` dan `git push` file CSV.
</details>

<details><summary>Kunci</summary>
Tidak ada satu jawaban benar. Yang perlu diperhatikan: pakai `datetime.now(timezone.utc).date()` sebagai kunci,
lewati bila tanggal itu sudah ada di CSV, dan simpan juga `sumber_tle` supaya baris dari TLE cadangan bisa dibedakan.
Untuk grafiknya, `px.line(riwayat, x="tanggal", y="lintasan", color="negara")` sudah cukup.
</details>
