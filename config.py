import os
from dotenv import load_dotenv

# Menentukan direktori dasar proyek
basedir = os.path.abspath(os.path.dirname(__file__))
# Memuat environment variables dari file .env
load_dotenv(os.path.join(basedir, '.env'))


class Config:
    # Mengambil SECRET_KEY dari environment variable, dengan nilai default jika tidak ditemukan
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'kunci-rahasia-default-jika-tidak-ada-env'

    # Mengambil URL database dari environment variable
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
                              'sqlite:///' + os.path.join(basedir, 'hr_app_fallback.db')

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Konfigurasi Folder Upload
    UPLOAD_FOLDER_DOC = os.path.join(basedir, 'uploads/dokumen')
    UPLOAD_FOLDER_KONTRAK = os.path.join(basedir, 'uploads/kontrak')
    UPLOAD_FOLDER_TEMPLATE = os.path.join(basedir, 'uploads/template')

    # Ekstensi file yang diizinkan untuk dokumen umum
    ALLOWED_EXTENSIONS_DOC = {'pdf', 'doc', 'docx', 'jpg', 'jpeg', 'png'}

