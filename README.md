# Dasbor HR & Manajemen Dokumen Karyawan

Aplikasi web sederhana berbasis Flask untuk mengelola data karyawan, dokumen personal, kontrak kerja, dan alur kerja perpanjangan kontrak. Proyek ini dibangun untuk memusatkan informasi HR, mengotomatisasi tugas-tugas repetitif, dan memberikan notifikasi proaktif.

## ✨ Fitur Utama

### Manajemen Karyawan (CRUD): 
Tambah, lihat, ubah, dan hapus data karyawan secara lengkap.

### Unggah Massal: 
Tambahkan puluhan atau ratusan data karyawan sekaligus melalui unggahan file Excel.

### Manajemen Dokumen: 
Unggah dan kelola dokumen penting per karyawan (CV, KTP, KK, SK, dll.).

### Generator Kontrak Otomatis:

- Unggah templat kontrak kerja dalam format .docx.

- Hasilkan file kontrak baru secara otomatis, lengkap dengan nomor surat yang berurutan.

### Dasbor Cerdas:

- Tampilkan ringkasan jumlah total karyawan.

- Fitur pencarian karyawan berdasarkan Nama, NUP, atau Jabatan.

### Notifikasi & Tindak Lanjut Kontrak:

- Daftar karyawan yang masa kontraknya akan berakhir dalam 90 hari ke depan.
- Alur kerja status tindak lanjut yang interaktif (Belum ditindaklanjuti, Telah dikonfirmasi, dll.) dengan kode warna untuk prioritas.
- Pembaruan status otomatis untuk menandai karyawan yang perlu ditindaklanjuti.

### Autentikasi Aman: 
Sistem login untuk admin dan perintah CLI khusus untuk membuat pengguna baru secara aman.

### Siap untuk Deployment: 
Sudah dikemas dengan Docker dan Docker Compose untuk instalasi yang mudah dan konsisten di lingkungan mana pun.

## 🛠️ Stack Teknologi

- Backend: Python 3, Flask
- Database: PostgreSQL
- ORM: Flask-SQLAlchemy
- Migrasi Database: Flask-Migrate (Alembic)
- Frontend: HTML, Tailwind CSS
- Pemrosesan Dokumen:
docxtpl untuk generate file .docx.
openpyxl untuk membaca file .xlsx.
- Kontainerisasi: Docker, Docker Compose
- Server Produksi (dalam Docker): Gunicorn

## 🚀 Instalasi & Penggunaan
Ada dua cara untuk menjalankan aplikasi ini: secara lokal dengan lingkungan virtual, atau menggunakan Docker (direkomendasikan).

### Cara Docker (Direkomendasikan)
Metode ini adalah yang paling mudah dan konsisten karena sudah mencakup database dan semua dependensi.
Prasyarat: Pastikan Anda sudah menginstal Docker Desktop di komputer Anda dan aplikasinya sedang berjalan.

- Konfigurasi Lingkungan:
Salin file .env.example dan ganti namanya menjadi .env.
Buka file .env dan isi SECRET_KEY dengan string acak yang panjang dan aman. Anda tidak perlu mengubah pengaturan database karena Docker akan mengelolanya secara otomatis.

- Bangun dan Jalankan Kontainer:
Buka terminal di direktori utama proyek dan jalankan satu perintah:
docker-compose up --build
Perintah ini akan membangun image aplikasi, mengunduh image PostgreSQL, menjalankan keduanya, dan secara otomatis menerapkan migrasi database. Tunggu hingga prosesnya selesai.

- Membuat Admin Pertama (Jika Database Baru):
Buka terminal kedua.
Jalankan perintah berikut untuk masuk ke dalam kontainer aplikasi dan membuat admin:
docker-compose exec web flask create-admin
Ikuti petunjuk untuk memasukkan username dan password.

- Akses Aplikasi: Buka browser Anda dan kunjungi http://127.0.0.1:5000.

### Cara Lokal (dengan Lingkungan Virtual)
- Prasyarat: Pastikan Anda sudah menginstal Python 3 dan PostgreSQL di sistem Anda.
- Buat Database: Buat sebuah database baru di PostgreSQL (misalnya, hr_dashboard).
  
Siapkan Lingkungan Virtual:
1. Buat lingkungan virtual : 
python -m venv venv

2. Aktifkan (Windows) :
.\venv\Scripts\activate, atau (macOS/Linux) : source venv/bin/activate

3. Instal Dependensi:
pip install -r requirements.txt

4. Konfigurasi Lingkungan:

5. Salin file .env.example dan ganti namanya menjadi .env.
Buka file .env dan sesuaikan DATABASE_URL dengan informasi koneksi ke database PostgreSQL Anda. Isi juga SECRET_KEY.

6. Terapkan Migrasi Database:
  - Atur variabel lingkungan (Windows PowerShell)
    $env:FLASK_APP = "app.py" atau (Windows CMD) set FLASK_APP=app.py atau (macOS/Linux) export FLASK_APP=app.py
  - Jalankan migrasi
    flask db upgrade

7. Membuat Admin Pertama:
  - flask create-admin
  kemudian ikuti petunjuk di terminal (masukan user dan password).

  - Jalankan Aplikasi:
  flask run

8. Aplikasi akan berjalan di http://127.0.0.1:5000.

## 📁 Struktur Proyek

hr_dashboard/
├── .env                  # (Dibuat manual) Berisi kunci rahasia dan koneksi DB
├── .env.example          # Contoh untuk file .env
├── .gitignore            # Mengabaikan file yang tidak perlu dilacak
├── Dockerfile            # Resep untuk membangun kontainer aplikasi
├── docker-compose.yml    # Orkestrasi untuk menjalankan aplikasi & DB
├── README.md             # File ini
├── app.py                # Logika utama aplikasi Flask
├── config.py             # Konfigurasi aplikasi
├── requirements.txt      # Daftar pustaka Python yang dibutuhkan
│
├── migrations/           # File migrasi database (dibuat oleh Flask-Migrate)
│   └── ...
│
├── models/               # Definisi tabel database (cetak biru)
│   ├── __init__.py
│   ├── karyawan.py
│   └── ...
│
├── static/               # File statis (template Excel)
│   └── template_karyawan.xlsx
│
├── templates/            # File HTML (tampilan antarmuka)
│   ├── base.html
│   ├── dashboard.html
│   └── ...
│
└── uploads/              # (Dibuat otomatis) Folder untuk menyimpan file unggahan
    ├── dokumen/
    ├── kontrak/
    └── template/
