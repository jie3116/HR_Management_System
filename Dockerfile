# --- Tahap 1: Gunakan image Python sebagai dasar ---
# Menggunakan versi 'slim' agar ukurannya lebih kecil
FROM python:3.11-slim

# --- Tahap 2: Atur lingkungan di dalam kontainer ---
# Tetapkan direktori kerja di dalam kontainer
WORKDIR /app

# Atur agar output Python tidak di-buffer, sehingga log muncul langsung
ENV PYTHONUNBUFFERED 1

# --- Tahap 3: Instal dependensi ---
# Salin file requirements.txt terlebih dahulu
COPY requirements.txt .

# Jalankan pip install. Menambahkan gunicorn untuk server produksi.
RUN pip install --no-cache-dir -r requirements.txt

# --- Tahap 4: Salin kode aplikasi ---
# Salin semua file dari folder proyek saat ini ke dalam direktori /app di kontainer
COPY . .

# --- Tahap 5: Jalankan aplikasi ---
# Beri tahu Docker bahwa aplikasi akan berjalan di port 5000
EXPOSE 5000

# Perintah untuk menjalankan aplikasi menggunakan Gunicorn (server WSGI produksi)
# Ini akan menjalankan migrasi database secara otomatis saat kontainer dimulai
CMD ["bash", "-c", "flask db upgrade && gunicorn --bind 0.0.0.0:5000 'app:app'"]
