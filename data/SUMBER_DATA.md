# Sumber data

Semua data dalam proyek ini publik. Tidak ada yang berasal dari akun berbayar atau sumber tertutup.

## 1. Elemen orbit (TLE) — CelesTrak

- **Apa:** Two-Line Element set untuk semua objek berstatus aktif, grup `active` (±16.000 objek pada November 2026, termasuk ±10.000 Starlink).
- **URL:** `https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle`
- **Asal:** CelesTrak menyalin data pelacakan 18th Space Defense Squadron (US Space Force) yang dipublikasikan lewat Space-Track, lalu menyajikannya tanpa login.
- **Pembaruan:** beberapa kali sehari. Aplikasi men-cache 3 jam; tombol *Refresh TLE* memaksa unduh ulang.
- **Cadangan:** `tle_cadangan.txt` adalah salinan yang diunduh pada tanggal yang tertulis di baris pertamanya. Dipakai bila server tidak terjangkau. Posisi dari TLE yang berumur lebih dari beberapa hari bisa meleset beberapa kilometer, dan satelit yang baru diluncurkan tidak akan muncul.
- **Lisensi:** bebas dipakai dengan menyebut CelesTrak sebagai sumber. CelesTrak meminta agar pengguna tidak mengunduh berulang-ulang lebih sering dari 2 jam; caching di aplikasi mengikuti permintaan itu.
- **Yang tidak ada di sini:** satelit militer yang tidak dipublikasikan orbitnya (sebagian satelit NRO Amerika, dan lain-lain). Mereka memang ada, hanya tidak terlihat.

## 2. Katalog satelit — GCAT (General Catalog of Artificial Space Objects)

- **Apa:** katalog karya Jonathan McDowell (Harvard-Smithsonian Center for Astrophysics) yang mencatat setiap objek buatan yang pernah mengorbit: nama, nomor NORAD, negara (`State`), pemilik (`Owner`), kelas operator (`Class`), kategori misi (`Category`), orbit, tanggal luncur, massa.
- **URL:** `https://planet4589.org/space/gcat/tsv/cat/satcat.tsv` (objek fisik) dan `.../cat/psatcat.tsv` (payload beserta kelas dan kategori). Dokumentasi: https://planet4589.org/space/gcat/web/cat/index.html
- **Kolom yang dipakai:**
  - `Class`: `A` amatir/akademik, `B` bisnis/komersial, `C` pemerintah sipil, `D` militer. Kombinasi seperti `BD` berarti dioperasikan bersama; aplikasi memperlakukan semua yang mengandung `D` sebagai militer.
  - `Category`: `COM` komunikasi, `IMG` pencitraan, `IMG-R` pencitraan radar, `SIG` intai sinyal, `EW` peringatan dini, `NAV` navigasi, `MET` cuaca, `SCI` sains, `TECH` uji teknologi, dan lain-lain. Tanda `?` berarti belum pasti, `*` berarti ada catatan; aplikasi mengambil kode dasarnya saja.
- **Pembaruan:** `scripts/bangun_katalog.py` mengunduh kedua tabel dan menyimpan versi ringkas ke `katalog_satelit.csv` (semua payload bernomor NORAD, ±27.000 baris, 1,9 MB). Tanggal pembuatan ada di baris pertama file. Jalankan ulang sebulan sekali agar satelit baru ikut dikenali.
- **Lisensi:** Creative Commons Attribution 4.0 (CC BY 4.0).
- **Keterbatasan:** klasifikasi militer/sipil adalah keputusan GCAT berdasarkan sumber terbuka. Satelit *dual-use* (misalnya Gaofen China atau KOMPSAT Korea) tercatat sipil meskipun citranya dipakai militer. Satelit yang baru diluncurkan bisa belum masuk katalog; aplikasi menebak keluarga yang mudah dikenali (Starlink, OneWeb, Yaogan, Jilin, dan sebagainya) dari pola nama dan memberi label "Belum terkatalog" untuk sisanya.

## 3. Kode negara — `kode_negara.csv`

- Pemetaan kode negara GCAT (sebagian tidak sama dengan ISO: `D` Jerman, `F` Prancis, `J` Jepang, `I` Italia, `UK` Inggris, `I-ESA` ESA) ke nama Indonesia dan bendera. Dibuat sendiri berdasarkan dokumentasi GCAT.
- `SU` (Uni Soviet) dipertahankan untuk objek lama; satelit Rusia setelah 1991 berkode `RU`.

## 4. Catatan satelit Indonesia — `satelit_indonesia.csv`

- Keterangan tambahan (operator, fungsi, slot orbit, tanggal luncur, catatan) untuk sembilan satelit Indonesia yang memiliki TLE aktif. Setiap baris memiliki kolom `sumber` dan `url_sumber` (Wikipedia bahasa Indonesia/Inggris).
- GCAT juga mencatat beberapa satelit kecil Indonesia lain yang belum mendapat nomor NORAD atau sudah tidak dilacak; mereka tidak muncul di aplikasi karena tidak ada TLE.

## 5. Batas wilayah — `src/wilayah.py`

- Poligon 46 titik yang digambar sendiri mengikuti batas darat dan laut Indonesia secara kasar (Selat Malaka, Laut Natuna, perbatasan Kalimantan, Laut Sulawesi, Pasifik utara Papua, batas 141° BT, Laut Arafura, Samudra Hindia). Simpangan 50-100 km dari batas sebenarnya; Timor-Leste ikut terlingkupi.
- Bukan batas resmi dan tidak mencerminkan klaim hukum apa pun. Pengganti yang lebih baik: GeoJSON batas ZEE dari Marine Regions (marineregions.org), yang tidak dibundel karena ukurannya.

## Catatan etika

Melacak satelit dari TLE publik adalah kegiatan yang legal dan umum (komunitas amatir, astronom, peneliti). Aplikasi ini
tidak mengungkap apa pun yang belum dipublikasikan dan tidak memuat data dari sumber tertutup. Melintasnya satelit di
atas suatu negara juga bukan pelanggaran: Outer Space Treaty 1967 menyatakan ruang angkasa bebas digunakan semua negara.
