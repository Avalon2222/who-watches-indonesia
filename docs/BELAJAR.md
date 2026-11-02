# 📚 Belajar dari proyek ini

Panduan ini menjelaskan apa yang terjadi di balik aplikasi, dari dua baris teks TLE sampai papan skor negara.
Tidak perlu latar belakang astronomi; cukup Python dasar dan rasa penasaran. Setiap bagian menunjuk ke file
dan fungsi yang bisa langsung dibaca.

---

## 1. Gambaran besar

```
CelesTrak (TLE) ─┐
                 ├─► src/muat_data.py ─► tabel satelit ─► src/orbit.py ─► lat/lon ─► src/wilayah.py ─► di atas Indonesia?
GCAT (katalog) ──┘                           │
                                             └─► src/klasifikasi.py ─► Indonesia / militer / pengintai / lainnya
```

Tiga pertanyaan yang dijawab aplikasi, dan di mana jawabannya dihitung:

| Pertanyaan | Fungsi |
|---|---|
| Di mana setiap satelit **sekarang**? | `orbit.posisi_saat(df, waktu)` |
| Berapa kali satelit X **melintas** dalam 24 jam? | `orbit.propagasi` + `wilayah.di_atas_indonesia` + `orbit.hitung_lintasan` |
| Satelit ini **milik siapa dan untuk apa**? | `muat_data.gabungkan` + `klasifikasi.klasifikasikan` |

---

## 2. TLE: dua baris yang menyimpan satu orbit

Setiap objek yang dilacak di orbit Bumi punya nomor katalog NORAD dan *Two-Line Element set* seperti ini:

```
TELKOM 3S
1 41944U 17007A   26306.50444602 -.00000370  00000+0  00000+0 0  9998
2 41944   0.0054 199.7592 0002611  36.4271 105.2252  1.00270770 35524
```

Yang penting untuk proyek ini:

| Posisi | Isi | Contoh | Arti |
|---|---|---|---|
| baris 1, kolom 3-7 | nomor NORAD | `41944` | identitas unik, kunci untuk digabung dengan katalog |
| baris 1, kolom 19-32 | epoch | `26306.50444602` | tahun 2026, hari ke-306, pukul 12:06 UTC: saat elemen ini diukur |
| baris 2, kolom 9-16 | inklinasi | `0.0054°` | kemiringan orbit terhadap khatulistiwa; 0° = tepat di atas khatulistiwa |
| baris 2, kolom 53-63 | mean motion | `1.00270770` | jumlah putaran per hari; 1,0027 = geostasioner, 15 = orbit rendah |

`orbit.parse_tle` membaca teks itu menjadi DataFrame. Perhatikan cara mengambil kolom berdasarkan posisi
karakter, bukan pemisah: format TLE berasal dari era kartu berlubang.

```python
norad = int(l1[2:7])
inklinasi = float(l2[8:16])
mean_motion = float(l2[52:63])
```

**Epoch** menentukan seberapa dipercaya posisinya. Model SGP4 cukup akurat (sekitar 1 km) beberapa hari
di sekitar epoch, lalu menyimpang karena hambatan atmosfer dan manuver tidak terduga. Itulah sebabnya
aplikasi mengunduh TLE baru setiap kali dibuka dan menyimpan cadangan hanya untuk keadaan darurat.

---

## 3. SGP4: dari elemen ke posisi

SGP4 (Simplified General Perturbations 4) adalah model standar yang mengubah TLE menjadi posisi dan kecepatan
pada waktu mana pun. Memakai perpustakaan `sgp4` cukup satu baris, dan versi *array*-nya menghitung ribuan
satelit × ribuan waktu sekaligus dalam C:

```python
from sgp4.api import Satrec, SatrecArray, jday

sats = SatrecArray([Satrec.twoline2rv(l1, l2) for l1, l2 in zip(df["line1"], df["line2"])])
jd, fr = jday(2026, 11, 2, 12, 0, 0)          # Julian Date: bagian bulat + pecahan hari
e, r, v = sats.sgp4(np.array([jd]), np.array([fr]))
# r.shape == (n_satelit, n_waktu, 3)  -> x, y, z dalam km
# e == 0 berarti sukses; nilai lain berarti orbit sudah meluruh atau TLE rusak
```

Angka yang keluar dinyatakan dalam kerangka **TEME**: sumbu x menunjuk ke titik Aries (arah tetap di
langit), bukan ikut berputar bersama Bumi. Jadi posisi x, y, z yang sama akan berada di atas kota yang berbeda
tergantung jam berapa Bumi sudah berputar. Lihat `orbit.propagasi`.

Kinerja: 1.600 satelit × 1.440 menit = 2,3 juta posisi selesai dalam ±2 detik. Matriksnya 55 MB, sehingga
`propagasi` memecah satelit per 400 baris supaya memori tetap kecil.

---

## 4. GMST: memutar langit menjadi Bumi

Untuk tahu kota mana yang ada di bawah satelit, kerangka TEME harus diputar sebesar sudut rotasi Bumi saat itu.
Sudut itu disebut **Greenwich Mean Sidereal Time** (GMST), dihitung dari Julian Date dengan rumus IAU 1982:

```python
t = (jd_ut1 - 2451545.0) / 36525.0                       # abad Julian sejak J2000
detik = 67310.54841 + (876600*3600 + 8640184.812866)*t + 0.093104*t**2 - 6.2e-6*t**3
gmst = np.deg2rad(detik / 240.0) % (2*np.pi)              # 240 detik waktu = 1 derajat
```

Lalu:

```python
x_e =  cos(gmst)*x + sin(gmst)*y
y_e = -sin(gmst)*x + cos(gmst)*y
z_e =  z
lon = atan2(y_e, x_e)
```

Fungsi `orbit.gmst_rad` diuji terhadap contoh di buku Vallado (*Fundamentals of Astrodynamics*): pada
20 Agustus 1992 12:14 UTC nilainya harus 152,5787°. Mengabaikan gerak kutub dan nutasi menyebabkan galat
di bawah 1 km, jauh lebih kecil daripada galat TLE itu sendiri.

---

## 5. Lintang geodetik: Bumi tidak bulat sempurna

Dari x, y, z menuju lintang tidak cukup dengan `atan2(z, sqrt(x²+y²))`, karena Bumi pepat (jari-jari kutub
21 km lebih pendek dari ekuator). Lintang yang dipakai peta adalah **lintang geodetik** WGS84, dan konversinya
butuh iterasi kecil:

```python
lat = atan2(z, p*(1-e2))                     # tebakan awal, p = sqrt(x²+y²)
for _ in range(4):
    N = a / sqrt(1 - e2*sin(lat)**2)         # jari-jari kelengkungan
    alt = p/cos(lat) - N
    lat = atan2(z, p*(1 - e2*N/(N+alt)))
```

Empat iterasi sudah konvergen di bawah 1 meter. Lihat `orbit.teme_ke_geodetik`. Hasil fungsi ini dibandingkan
dengan perpustakaan `skyfield` saat pengembangan dan sama sampai tiga angka desimal derajat.

---

## 6. Apakah titik ini di dalam Indonesia? Ray casting

Wilayah Indonesia diwakili poligon 46 titik di `src/wilayah.py`. Untuk setiap posisi satelit kita perlu tahu:
di dalam atau di luar? Algoritma **ray casting**: tarik garis khayal dari titik ke arah timur sampai tak hingga,
hitung berapa sisi poligon yang dipotong. Ganjil = di dalam, genap = di luar.

```python
for setiap sisi (x1,y1)-(x2,y2):
    if (y1 > lat) != (y2 > lat):                       # sisi melintasi garis horizontal titik?
        x_potong = x1 + (lat - y1)*(x2 - x1)/(y2 - y1)
        if lon < x_potong:                             # potongannya di sebelah timur titik?
            di_dalam = not di_dalam
```

Versi di repo tervektorisasi: `lat` dan `lon` boleh array berbentuk apa pun (misalnya 1.600 × 1.440), dan
seluruh perbandingan dilakukan numpy sekaligus. Kotak pembatas (`LAT_MIN`, `LON_MAX`, ...) dipakai sebagai
saringan awal supaya 98% titik yang jelas-jelas jauh tidak perlu diuji terhadap 46 sisi.

Mengapa poligon, bukan kotak? Kotak 95-141° BT × 11° LS-6° LU akan ikut menghitung Malaysia, Singapura,
Filipina selatan, dan Australia utara. Poligon kasar sudah jauh lebih jujur.

---

## 7. Menghitung lintasan dari matriks boolean

Setelah `mask[i, t]` berisi True bila satelit i di atas Indonesia pada menit t, menghitung lintasan tinggal
mencari **tepi naik** (False → True):

```python
sebelumnya = np.concatenate([np.zeros((n, 1), bool), mask[:, :-1]], axis=1)
tepi_naik = mask & ~sebelumnya
jumlah_lintasan = tepi_naik.sum(axis=1)
menit_di_atas = mask.sum(axis=1) * langkah_menit
```

Satu baris numpy menggantikan perulangan Python atas 2,3 juta sel. `orbit.daftar_lintasan` melakukan hal
yang sama untuk satu satelit tetapi mengembalikan jam mulai, jam selesai, dan durasi setiap lintasan,
yang dipakai tab *Track a satellite*.

Satelit GEO adalah kasus khusus: kalau titik sub-satelitnya di dalam poligon, `mask` seluruhnya True dan
"lintasannya" satu kali selama 1.440 menit. Aplikasi memisahkannya ke daftar "diam permanen di atas wilayah".

---

## 8. Katalog GCAT: siapa pemilik satelit ini?

TLE tidak menyimpan negara atau tujuan satelit. Informasi itu diambil dari GCAT, katalog publik karya
Jonathan McDowell. Dua tabelnya digabung oleh `scripts/bangun_katalog.py` lewat kunci JCAT, lalu disimpan
ringkas per nomor NORAD.

Dua kode GCAT yang menjadi tulang punggung klasifikasi:

| Kode | Nilai | Dipakai sebagai |
|---|---|---|
| `Class` | A amatir, B bisnis, C sipil, D militer | kolom **operator** |
| `Category` | COM, IMG, IMG-R, SIG, EW, NAV, MET, SCI, TECH, ... | kolom **misi**; IMG/IMG-R/SIG/EW → **pengintai** |

Dari keduanya `klasifikasi.tentukan_kelompok` membentuk empat kelompok warna peta. Semua aturan ada di satu
file kecil supaya mudah diubah dan diuji (`tests/test_klasifikasi.py`).

Satelit yang baru diluncurkan bisa belum ada di GCAT. `klasifikasi.POLA_NAMA` menebak keluarga yang jelas
(`STARLINK`, `YAOGAN`, `JILIN`, ...) dari nama; sisanya diberi label "Belum terkatalog" alih-alih ditebak.

---

## 9. Streamlit: cache dan fragment

Dua hal yang membuat aplikasi tetap cepat:

- `@st.cache_data(ttl=3*3600)` pada `muat_tabel_satelit`: TLE diunduh sekali, dipakai semua pengunjung
  selama 3 jam.
- `@st.cache_data(ttl=3600)` pada `analisis_lintasan`: matriks 24 jam dihitung sekali per jam. Waktu mulai
  dibulatkan ke 10 menit supaya dua pengunjung dalam rentang itu memakai cache yang sama.
- `@st.fragment(run_every="30s")` pada bagian peta live: hanya potongan itu yang dijalankan ulang setiap
  30 detik, bukan seluruh halaman.

Perhitungan posisi "sekarang" untuk 16.000 satelit hanya 0,2 detik, jadi tidak di-cache.

---

## 10. Membaca hasilnya dengan kritis

- **Lintasan ≠ pemotretan.** Satelit pencitraan bisa memotret ratusan km di samping jalurnya. Angka di
  papan skor adalah batas bawah dari "berapa kali Indonesia bisa dipotret".
- **Jumlah lintasan dipengaruhi jumlah satelit.** Amerika Serikat tinggi karena Planet mengoperasikan
  ratusan satelit kecil komersial, bukan karena ratusan satelit militer. Kolom "…di antaranya militer"
  ada untuk itu.
- **Yang tidak terlihat tetap ada.** Satelit paling rahasia tidak memiliki TLE publik.
- **Klasifikasi adalah penilaian GCAT**, dibuat dari sumber terbuka, dan bisa berubah.

---

## 11. Bacaan lanjutan

- CelesTrak, *NORAD Two-Line Element Set Format*: https://celestrak.org/NORAD/documentation/tle-fmt.php
- Vallado & Crawford, *SGP4 Orbit Determination* (AIAA 2008), rujukan model sgp4.
- Dokumentasi GCAT: https://planet4589.org/space/gcat/web/intro/index.html
- Brandon Rhodes, dokumentasi `sgp4` dan `skyfield`: https://rhodesmill.org/skyfield/
- Jonathan McDowell, *Jonathan's Space Report*, untuk membaca kabar peluncuran yang masuk katalog.
