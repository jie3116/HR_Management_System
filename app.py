import os
from datetime import date, timedelta, datetime
from functools import wraps
from werkzeug.utils import secure_filename
from flask import (Flask, render_template, request, redirect, url_for, flash,
                   session, send_from_directory)
from flask_migrate import Migrate
from docxtpl import DocxTemplate
from dotenv import load_dotenv
import locale
from sqlalchemy import or_, distinct
import openpyxl

load_dotenv()

# Impor Konfigurasi dan Model
from config import Config
from models import db
from models.karyawan import Karyawan
from models.dokumen import Dokumen
from models.template_kontrak import TemplateKontrak
from models.user import User

# Atur locale ke Bahasa Indonesia untuk format tanggal
try:
    locale.setlocale(locale.LC_TIME, 'id_ID.UTF-8')
except locale.Error:
    try:
        locale.setlocale(locale.LC_TIME, 'Indonesian_indonesia.1252')
    except locale.Error:
        pass  # Gunakan default jika locale Indonesia tidak tersedia

# --- Inisialisasi Aplikasi ---
app = Flask(__name__)
app.config.from_object(Config)

# --- Inisialisasi Ekstensi ---
db.init_app(app)
migrate = Migrate(app, db)

# Membuat folder upload jika belum ada
os.makedirs(app.config['UPLOAD_FOLDER_DOC'], exist_ok=True)
os.makedirs(app.config['UPLOAD_FOLDER_KONTRAK'], exist_ok=True)
os.makedirs(app.config['UPLOAD_FOLDER_TEMPLATE'], exist_ok=True)

# --- Daftar Status  ---
STATUS_TINDAK_LANJUT_OPTIONS = [
    'Tidak perlu',
    'Belum ditindaklanjuti',
    'Telah dikonfirmasi ke cabang/unit kerja',
    'Dalam proses perpanjangan kontrak',
    'Tidak diperpanjang'
]


# --- Fungsi Otomatis Baru ---
def check_and_update_statuses():
    """
    Memeriksa dan memperbarui status karyawan secara otomatis.
    """
    today = date.today()
    ninety_days_later = today + timedelta(days=90)

    try:
        # 1. Nonaktifkan karyawan yang kontraknya habis dan tidak diperpanjang
        karyawan_to_terminate = Karyawan.query.filter(
            Karyawan.tindak_lanjut_kontrak == 'Tidak diperpanjang',
            Karyawan.tanggal_akhir_kontrak < today,
            Karyawan.status == 'Aktif'
        ).all()
        for karyawan in karyawan_to_terminate:
            karyawan.status = 'Nonaktif'

        # 2. Ubah status tindak lanjut untuk kontrak yang akan habis
        karyawan_to_follow_up = Karyawan.query.filter(
            Karyawan.tanggal_akhir_kontrak.isnot(None),
            Karyawan.tanggal_akhir_kontrak <= ninety_days_later,
            Karyawan.tindak_lanjut_kontrak == 'Tidak perlu'
        ).all()
        for karyawan in karyawan_to_follow_up:
            karyawan.tindak_lanjut_kontrak = 'Belum ditindaklanjuti'

        db.session.commit()
    except Exception as e:
        db.session.rollback()
        # Di lingkungan produksi, sebaiknya gunakan logger
        print(f"Error saat update status otomatis: {e}")


# --- Helper Functions & Decorators ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Silakan login untuk mengakses halaman ini.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)

    return decorated_function


def allowed_file(filename, extensions):
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in extensions


def format_rupiah(value):
    if value is None:
        return "0"
    # Format tanpa desimal
    return "{:,.0f}".format(value).replace(',', '.')


def format_tanggal(value):
    if value is None:
        return "-"
    # Format: 19 Oktober 2025
    return value.strftime("%d %B %Y")


def get_basename(path):
    """Mengambil nama file dari path lengkap."""
    return os.path.basename(path)


# Daftarkan filter ke Jinja2
app.jinja_env.filters['rupiah'] = format_rupiah
app.jinja_env.filters['tanggal'] = format_tanggal
app.jinja_env.filters['basename'] = get_basename


# --- Rute Autentikasi ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    # Jika sudah login, arahkan ke dashboard
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session['user_id'] = user.id
            session['username'] = user.username
            flash('Login berhasil!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Username atau password salah.', 'danger')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('Anda telah logout.', 'success')
    return redirect(url_for('login'))


# --- Rute Utama ---
@app.route('/')
@login_required
def index():
    return redirect(url_for('dashboard'))


@app.route('/dashboard')
@login_required
def dashboard():
    # Jalankan pemeriksaan status otomatis
    check_and_update_statuses()

    # Ambil parameter filter dari URL
    search_query = request.args.get('search', '').strip()
    selected_unit_kerja = request.args.get('unit_kerja', '').strip()
    gaji_min_str = request.args.get('gaji_min', '').strip()
    gaji_max_str = request.args.get('gaji_max', '').strip()

    # Konversi gaji ke integer (tangani jika kosong atau tidak valid)
    try:
        gaji_min = int(gaji_min_str) if gaji_min_str else None
    except ValueError:
        gaji_min = None
        flash('Gaji minimum tidak valid.', 'warning')
    try:
        gaji_max = int(gaji_max_str) if gaji_max_str else None
    except ValueError:
        gaji_max = None
        flash('Gaji maksimum tidak valid.', 'warning')

    total_karyawan = Karyawan.query.count()

    today = date.today()
    ninety_days_later = today + timedelta(days=90)

    # Ambil daftar karyawan yang kontraknya akan habis
    kontrak_akan_habis = Karyawan.query.filter(
        Karyawan.tanggal_akhir_kontrak.isnot(None),
        Karyawan.tanggal_akhir_kontrak <= ninety_days_later,
        Karyawan.tanggal_akhir_kontrak >= today,
        Karyawan.status == 'Aktif'  # Hanya tampilkan yang masih aktif
    ).order_by(Karyawan.tanggal_akhir_kontrak).all()

    # Ambil daftar unik unit kerja untuk dropdown filter
    unit_kerja_options = [uk[0] for uk in db.session.query(distinct(Karyawan.unit_kerja)).filter(
        Karyawan.unit_kerja.isnot(None)).order_by(Karyawan.unit_kerja).all()]

    # Query dasar untuk karyawan aktif
    query = Karyawan.query.filter_by(status='Aktif')

    # Terapkan filter pencarian teks
    if search_query:
        search_term = f"%{search_query}%"
        query = query.filter(
            or_(
                Karyawan.nama.ilike(search_term),
                Karyawan.nup.ilike(search_term),
                Karyawan.jabatan.ilike(search_term)
            )
        )

    # Terapkan filter unit kerja
    if selected_unit_kerja:
        query = query.filter(Karyawan.unit_kerja == selected_unit_kerja)

    # Terapkan filter gaji minimum
    if gaji_min is not None:
        query = query.filter(Karyawan.gaji_honorarium >= gaji_min)

    # Terapkan filter gaji maksimum
    if gaji_max is not None:
        query = query.filter(Karyawan.gaji_honorarium <= gaji_max)

    # Eksekusi query untuk mendapatkan daftar karyawan aktif yang terfilter
    semua_karyawan_aktif = query.order_by(Karyawan.nama).all()

    return render_template('dashboard.html',
                           total_karyawan=total_karyawan,
                           kontrak_akan_habis=kontrak_akan_habis,
                           semua_karyawan_aktif=semua_karyawan_aktif,
                           # Kirim nilai filter kembali ke template
                           search_query=search_query,
                           selected_unit_kerja=selected_unit_kerja,
                           gaji_min=gaji_min_str,  # Kirim string asli untuk input
                           gaji_max=gaji_max_str,  # Kirim string asli untuk input
                           # Kirim data untuk dropdown
                           unit_kerja_options=unit_kerja_options,
                           status_options=STATUS_TINDAK_LANJUT_OPTIONS)


# --- Rute Karyawan ---
@app.route('/karyawan')
@login_required
def karyawan():
    semua_karyawan = Karyawan.query.order_by(Karyawan.nama).all()
    # Ambil daftar unik unit kerja untuk dropdown di form tambah
    unit_kerja_options = [uk[0] for uk in db.session.query(distinct(Karyawan.unit_kerja)).filter(
        Karyawan.unit_kerja.isnot(None)).order_by(Karyawan.unit_kerja).all()]
    return render_template('karyawan.html',
                           semua_karyawan=semua_karyawan,
                           unit_kerja_options=unit_kerja_options)


@app.route('/karyawan/tambah', methods=['POST'])
@login_required
def tambah_karyawan():
    try:
        # Validasi input tanggal
        tanggal_lahir_str = request.form.get('tanggal_lahir')
        tanggal_mulai_str = request.form.get('tanggal_mulai')
        tanggal_akhir_str = request.form.get('tanggal_akhir_kontrak')

        tanggal_lahir = datetime.strptime(tanggal_lahir_str, '%Y-%m-%d').date() if tanggal_lahir_str else None
        tanggal_mulai = datetime.strptime(tanggal_mulai_str, '%Y-%m-%d').date() if tanggal_mulai_str else None
        tanggal_akhir_kontrak = datetime.strptime(tanggal_akhir_str, '%Y-%m-%d').date() if tanggal_akhir_str else None

        if not tanggal_lahir or not tanggal_mulai:
            flash('Tanggal Lahir dan Tanggal Mulai wajib diisi.', 'danger')
            return redirect(url_for('karyawan'))

        new_karyawan = Karyawan(
            nama=request.form['nama'],
            jenis_kelamin=request.form['jenis_kelamin'],
            nup=request.form['nup'],
            tempat_lahir=request.form['tempat_lahir'],
            tanggal_lahir=tanggal_lahir,
            nik=request.form['nik'],
            alamat=request.form.get('alamat'),
            no_hp=request.form.get('no_hp'),
            jabatan=request.form.get('jabatan'),
            unit_kerja=request.form.get('unit_kerja'),
            email=request.form.get('email'),
            tanggal_mulai=tanggal_mulai,
            tanggal_akhir_kontrak=tanggal_akhir_kontrak,
            gaji_honorarium=int(request.form.get('gaji_honorarium')) if request.form.get('gaji_honorarium') else None,
            # Izinkan NULL jika kosong
            tunjangan_tetap=int(request.form.get('tunjangan_tetap')) if request.form.get('tunjangan_tetap') else None,
            # Izinkan NULL jika kosong
            status=request.form.get('status', 'Aktif')
            # tindak_lanjut_kontrak diisi default oleh model
        )
        db.session.add(new_karyawan)
        db.session.commit()
        flash('Karyawan baru berhasil ditambahkan.', 'success')
    except ValueError:
        db.session.rollback()
        flash('Format tanggal tidak valid. Gunakan format YYYY-MM-DD.', 'danger')
    except Exception as e:
        db.session.rollback()
        # Periksa apakah error karena duplikasi NUP/NIK
        error_str = str(e).lower()
        if 'unique constraint' in error_str and 'nup' in error_str:
            flash(f'Gagal menambahkan karyawan. NUP {request.form["nup"]} sudah digunakan.', 'danger')
        elif 'unique constraint' in error_str and 'nik' in error_str:
            flash(f'Gagal menambahkan karyawan. NIK {request.form["nik"]} sudah digunakan.', 'danger')
        else:
            flash(f'Gagal menambahkan karyawan. Error: {str(e)}', 'danger')
    return redirect(url_for('karyawan'))


# --- Rute untuk Unggah Massal ---
@app.route('/karyawan/upload_excel', methods=['POST'])
@login_required
def upload_excel():
    if 'file' not in request.files:
        flash('Tidak ada file yang dipilih.', 'danger')
        return redirect(url_for('karyawan'))

    file = request.files['file']

    if file.filename == '':
        flash('Tidak ada file yang dipilih.', 'danger')
        return redirect(url_for('karyawan'))

    if file and allowed_file(file.filename, {'xlsx'}):
        try:
            workbook = openpyxl.load_workbook(file, data_only=True)  # data_only=True untuk membaca nilai, bukan formula
            sheet = workbook.active
            berhasil_ditambah = 0
            gagal_karena_duplikat = 0
            gagal_karena_data = 0

            # Validasi Header
            header = [cell.value for cell in sheet[1]]
            expected_header = ['nama', 'jenis_kelamin', 'nup', 'tempat_lahir', 'tanggal_lahir', 'nik', 'alamat',
                               'no_hp', 'jabatan', 'unit_kerja', 'email', 'tanggal_mulai', 'tanggal_akhir_kontrak',
                               'gaji_honorarium', 'tunjangan_tetap', 'status']
            if header != expected_header:
                flash(
                    f"Header file Excel tidak sesuai. Harap gunakan template yang disediakan. Header yang diharapkan: {', '.join(expected_header)}",
                    'danger')
                return redirect(url_for('karyawan'))

            # Proses baris data
            for index, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
                # Periksa apakah baris kosong (semua sel None)
                if all(cell is None for cell in row):
                    continue  # Lewati baris kosong

                # Ambil data dari baris, tangani nilai None
                nama, jk, nup, tmpt_lhr, tgl_lhr_raw, nik, almt, nohp, jbtn, unit, eml, tgl_mli_raw, tgl_akhr_raw, gaji_raw, tunj_raw, stat = row

                # --- Validasi Data Penting ---
                if not nama or not nup or not tgl_lhr_raw or not nik or not tgl_mli_raw:
                    flash(
                        f"Baris {index}: Data tidak lengkap (Nama, NUP, Tgl Lahir, NIK, Tgl Mulai wajib diisi). Data dilewati.",
                        'warning')
                    gagal_karena_data += 1
                    continue

                # Konversi NUP dan NIK ke string untuk konsistensi
                nup = str(nup)
                nik = str(nik)

                # Cek Duplikasi NUP/NIK
                if Karyawan.query.filter(or_(Karyawan.nup == nup, Karyawan.nik == nik)).first():
                    flash(f"Baris {index}: Karyawan dengan NUP {nup} atau NIK {nik} sudah ada. Data dilewati.",
                          'warning')
                    gagal_karena_duplikat += 1
                    continue

                # --- Konversi dan Validasi Tipe Data ---
                try:
                    # Tangani tanggal dari Excel (bisa jadi datetime atau string)
                    tgl_lhr = tgl_lhr_raw.date() if isinstance(tgl_lhr_raw, datetime) else datetime.strptime(
                        str(tgl_lhr_raw).split()[0], '%Y-%m-%d').date() if tgl_lhr_raw else None
                    tgl_mli = tgl_mli_raw.date() if isinstance(tgl_mli_raw, datetime) else datetime.strptime(
                        str(tgl_mli_raw).split()[0], '%Y-%m-%d').date() if tgl_mli_raw else None
                    tgl_akhr = tgl_akhr_raw.date() if isinstance(tgl_akhr_raw, datetime) else datetime.strptime(
                        str(tgl_akhr_raw).split()[0], '%Y-%m-%d').date() if tgl_akhr_raw else None

                    gaji = int(gaji_raw) if gaji_raw is not None else None
                    tunj = int(tunj_raw) if tunj_raw is not None else None

                    # Ulangi validasi penting setelah konversi
                    if not tgl_lhr or not tgl_mli:
                        flash(f"Baris {index}: Tgl Lahir atau Tgl Mulai tidak valid setelah konversi. Data dilewati.",
                              'warning')
                        gagal_karena_data += 1
                        continue

                except (ValueError, TypeError) as ve:
                    flash(f"Baris {index}: Format data salah (tanggal/angka). Error: {ve}. Data dilewati.", 'warning')
                    gagal_karena_data += 1
                    continue

                # Buat objek Karyawan baru
                new_karyawan = Karyawan(
                    nama=nama,
                    jenis_kelamin=jk,
                    nup=nup,
                    tempat_lahir=tmpt_lhr,
                    tanggal_lahir=tgl_lhr,
                    nik=nik,
                    alamat=almt,
                    no_hp=str(nohp) if nohp else None,
                    jabatan=jbtn,
                    unit_kerja=unit,
                    email=eml,
                    tanggal_mulai=tgl_mli,
                    tanggal_akhir_kontrak=tgl_akhr,
                    gaji_honorarium=gaji,
                    tunjangan_tetap=tunj,
                    status=stat or 'Aktif'  # Default 'Aktif' jika kosong
                )
                db.session.add(new_karyawan)
                berhasil_ditambah += 1  # Tambah hitungan berhasil HANYA jika validasi lolos

            # Commit setelah loop selesai
            db.session.commit()
            flash(
                f'Proses unggah selesai. {berhasil_ditambah} karyawan berhasil ditambahkan. {gagal_karena_duplikat} data duplikat dilewati. {gagal_karena_data} data tidak lengkap/valid dilewati.',
                'success')

        except Exception as e:
            db.session.rollback()
            flash(f'Terjadi kesalahan saat memproses file Excel. Pastikan format file dan data sudah benar. Error: {e}',
                  'danger')
    else:
        flash('Format file tidak diizinkan. Harap unggah file .xlsx.', 'warning')

    return redirect(url_for('karyawan'))


@app.route('/karyawan/download_template')
@login_required
def download_template_excel():
    # Pastikan file template ada di static/
    template_path = os.path.join(app.static_folder, 'template_karyawan.xlsx')
    if not os.path.exists(template_path):
        flash('File template tidak ditemukan di server.', 'danger')
        return redirect(url_for('karyawan'))
    return send_from_directory('static', 'template_karyawan.xlsx', as_attachment=True)


@app.route('/karyawan/detail/<int:id>')
@login_required
def detail_karyawan(id):
    karyawan = Karyawan.query.get_or_404(id)
    templates = TemplateKontrak.query.all()
    # Ambil daftar unik unit kerja untuk dropdown edit
    unit_kerja_options = [uk[0] for uk in db.session.query(distinct(Karyawan.unit_kerja)).filter(
        Karyawan.unit_kerja.isnot(None)).order_by(Karyawan.unit_kerja).all()]
    return render_template('detail_karyawan.html',
                           karyawan=karyawan,
                           templates=templates,
                           status_options=STATUS_TINDAK_LANJUT_OPTIONS,
                           unit_kerja_options=unit_kerja_options)


@app.route('/karyawan/edit/<int:id>', methods=['POST'])
@login_required
def edit_karyawan(id):
    karyawan_to_edit = Karyawan.query.get_or_404(id)
    try:
        # Validasi input tanggal
        tanggal_lahir_str = request.form.get('tanggal_lahir')
        tanggal_mulai_str = request.form.get('tanggal_mulai')
        tanggal_akhir_str = request.form.get('tanggal_akhir_kontrak')

        tanggal_lahir = datetime.strptime(tanggal_lahir_str, '%Y-%m-%d').date() if tanggal_lahir_str else None
        tanggal_mulai = datetime.strptime(tanggal_mulai_str, '%Y-%m-%d').date() if tanggal_mulai_str else None
        tanggal_akhir_kontrak = datetime.strptime(tanggal_akhir_str, '%Y-%m-%d').date() if tanggal_akhir_str else None

        if not tanggal_lahir or not tanggal_mulai:
            flash('Tanggal Lahir dan Tanggal Mulai wajib diisi.', 'danger')
            return redirect(url_for('detail_karyawan', id=id))

        karyawan_to_edit.nama = request.form['nama']
        karyawan_to_edit.jenis_kelamin = request.form['jenis_kelamin']
        karyawan_to_edit.nup = request.form['nup']
        karyawan_to_edit.tempat_lahir = request.form['tempat_lahir']
        karyawan_to_edit.tanggal_lahir = tanggal_lahir
        karyawan_to_edit.nik = request.form['nik']
        karyawan_to_edit.alamat = request.form.get('alamat')
        karyawan_to_edit.no_hp = request.form.get('no_hp')
        karyawan_to_edit.jabatan = request.form.get('jabatan')
        karyawan_to_edit.unit_kerja = request.form.get('unit_kerja')
        karyawan_to_edit.email = request.form.get('email')
        karyawan_to_edit.tanggal_mulai = tanggal_mulai
        karyawan_to_edit.tanggal_akhir_kontrak = tanggal_akhir_kontrak
        karyawan_to_edit.gaji_honorarium = int(request.form.get('gaji_honorarium')) if request.form.get(
            'gaji_honorarium') else None
        karyawan_to_edit.tunjangan_tetap = int(request.form.get('tunjangan_tetap')) if request.form.get(
            'tunjangan_tetap') else None
        karyawan_to_edit.status = request.form['status']
        karyawan_to_edit.tindak_lanjut_kontrak = request.form['tindak_lanjut_kontrak']

        db.session.commit()
        flash('Data karyawan berhasil diperbarui.', 'success')
    except ValueError:
        db.session.rollback()
        flash('Format tanggal tidak valid. Gunakan format YYYY-MM-DD.', 'danger')
    except Exception as e:
        db.session.rollback()
        error_str = str(e).lower()
        if 'unique constraint' in error_str and 'nup' in error_str:
            flash(f'Gagal memperbarui data. NUP {request.form["nup"]} sudah digunakan oleh karyawan lain.', 'danger')
        elif 'unique constraint' in error_str and 'nik' in error_str:
            flash(f'Gagal memperbarui data. NIK {request.form["nik"]} sudah digunakan oleh karyawan lain.', 'danger')
        else:
            flash(f'Gagal memperbarui data. Error: {str(e)}', 'danger')
    return redirect(url_for('detail_karyawan', id=id))


@app.route('/karyawan/update_tindak_lanjut/<int:id>', methods=['POST'])
@login_required
def update_tindak_lanjut(id):
    karyawan = Karyawan.query.get_or_404(id)
    new_status = request.form.get('status_tindak_lanjut')
    if new_status in STATUS_TINDAK_LANJUT_OPTIONS:
        try:
            karyawan.tindak_lanjut_kontrak = new_status
            db.session.commit()
            flash(f'Status tindak lanjut untuk {karyawan.nama} berhasil diperbarui.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Gagal memperbarui status. Error: {str(e)}', 'danger')
    else:
        flash(f'Status "{new_status}" tidak valid.', 'danger')
    # Kembali ke dashboard dengan filter yang sama (jika ada)
    return redirect(request.referrer or url_for('dashboard'))


@app.route('/karyawan/hapus/<int:id>', methods=['POST'])
@login_required
def hapus_karyawan(id):
    karyawan_to_delete = Karyawan.query.get_or_404(id)
    try:
        # Hapus file fisik terkait DULU sebelum menghapus record DB
        for doc in karyawan_to_delete.dokumen:
            if doc.file_path and os.path.exists(doc.file_path):
                try:
                    os.remove(doc.file_path)
                except OSError as e:
                    # Log error jika gagal hapus file, tapi lanjutkan proses
                    print(f"Peringatan: Gagal menghapus file {doc.file_path}. Error: {e}")

        db.session.delete(karyawan_to_delete)
        db.session.commit()
        flash('Karyawan dan semua dokumen terkait berhasil dihapus.', 'success')
        # Kembali ke halaman karyawan setelah hapus
        return redirect(url_for('karyawan'))
    except Exception as e:
        db.session.rollback()
        flash(f'Gagal menghapus karyawan. Error: {str(e)}', 'danger')
        # Kembali ke halaman detail jika gagal hapus
        return redirect(url_for('detail_karyawan', id=id))


# --- Rute Dokumen ---
@app.route('/dokumen/upload/<int:karyawan_id>', methods=['POST'])
@login_required
def upload_dokumen(karyawan_id):
    karyawan = Karyawan.query.get_or_404(karyawan_id)
    if 'file' not in request.files:
        flash('Tidak ada file yang dipilih.', 'danger')
        return redirect(url_for('detail_karyawan', id=karyawan_id))

    file = request.files['file']
    jenis_dokumen = request.form.get('jenis_dokumen', 'Lainnya').strip()  # Default 'Lainnya' jika kosong

    if not jenis_dokumen:
        flash('Jenis dokumen wajib diisi.', 'danger')
        return redirect(url_for('detail_karyawan', id=karyawan_id))

    if file.filename == '':
        flash('Tidak ada file yang dipilih.', 'danger')
        return redirect(url_for('detail_karyawan', id=karyawan_id))

    if file and allowed_file(file.filename, app.config['ALLOWED_EXTENSIONS_DOC']):
        # Buat nama file lebih unik dan bersih
        base, ext = os.path.splitext(file.filename)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        filename = secure_filename(f"{karyawan.nup}_{jenis_dokumen}_{timestamp}{ext}")
        file_path = os.path.join(app.config['UPLOAD_FOLDER_DOC'], filename)

        try:
            file.save(file_path)
            new_dokumen = Dokumen(
                karyawan_id=karyawan_id,
                jenis=jenis_dokumen,
                file_path=file_path,
                tanggal_upload=date.today()  # Tambahkan tanggal upload
            )
            db.session.add(new_dokumen)
            db.session.commit()
            flash('Dokumen berhasil diunggah.', 'success')
        except Exception as e:
            db.session.rollback()
            # Hapus file yang mungkin sudah tersimpan jika ada error DB
            if os.path.exists(file_path):
                os.remove(file_path)
            flash(f'Gagal menyimpan dokumen. Error: {str(e)}', 'danger')
    else:
        allowed_ext_str = ", ".join(app.config['ALLOWED_EXTENSIONS_DOC'])
        flash(f'Format file tidak diizinkan. Hanya izinkan: {allowed_ext_str}', 'warning')

    return redirect(url_for('detail_karyawan', id=karyawan_id))


@app.route('/dokumen/download/<int:dokumen_id>')
@login_required
def download_dokumen(dokumen_id):
    dokumen = Dokumen.query.get_or_404(dokumen_id)
    try:
        # Cek apakah path file ada
        if not dokumen.file_path or not os.path.exists(dokumen.file_path):
            raise FileNotFoundError
        directory = os.path.dirname(dokumen.file_path)
        filename = os.path.basename(dokumen.file_path)
        return send_from_directory(directory, filename, as_attachment=True)
    except FileNotFoundError:
        flash('File tidak ditemukan di server.', 'danger')
        return redirect(url_for('detail_karyawan', id=dokumen.karyawan_id))


# --- Rute Template Kontrak ---
@app.route('/template')
@login_required
def template_kontrak():
    templates = TemplateKontrak.query.all()
    return render_template('template_kontrak.html', templates=templates)


@app.route('/template/upload', methods=['POST'])
@login_required
def upload_template():
    if 'file' not in request.files:
        flash('Tidak ada file yang dipilih.', 'danger')
        return redirect(url_for('template_kontrak'))

    file = request.files['file']
    nama_template = request.form.get('nama_template', '').strip()

    if file.filename == '' or not nama_template:
        flash('Nama template dan file tidak boleh kosong.', 'danger')
        return redirect(url_for('template_kontrak'))

    if file and allowed_file(file.filename, {'docx'}):
        # Buat nama file unik untuk menghindari tumpang tindih
        base, ext = os.path.splitext(file.filename)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        filename = secure_filename(f"{nama_template.replace(' ', '_')}_{timestamp}{ext}")
        file_path = os.path.join(app.config['UPLOAD_FOLDER_TEMPLATE'], filename)

        # Cek jika nama template sudah ada
        if TemplateKontrak.query.filter_by(nama_template=nama_template).first():
            flash(f'Nama template "{nama_template}" sudah digunakan.', 'warning')
            return redirect(url_for('template_kontrak'))

        try:
            file.save(file_path)
            new_template = TemplateKontrak(nama_template=nama_template, file_path=file_path)
            db.session.add(new_template)
            db.session.commit()
            flash('Template berhasil diunggah.', 'success')
        except Exception as e:
            db.session.rollback()
            if os.path.exists(file_path):
                os.remove(file_path)
            flash(f'Gagal menyimpan template. Error: {str(e)}', 'danger')
    else:
        flash('Format file tidak diizinkan. Harap unggah file .docx', 'warning')

    return redirect(url_for('template_kontrak'))


@app.route('/template/hapus/<int:id>', methods=['POST'])
@login_required
def hapus_template(id):
    template_to_delete = TemplateKontrak.query.get_or_404(id)
    try:
        # Hapus file fisik
        if template_to_delete.file_path and os.path.exists(template_to_delete.file_path):
            try:
                os.remove(template_to_delete.file_path)
            except OSError as e:
                print(f"Peringatan: Gagal menghapus file template {template_to_delete.file_path}. Error: {e}")

        db.session.delete(template_to_delete)
        db.session.commit()
        flash('Template berhasil dihapus.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Gagal menghapus template. Error: {str(e)}', 'danger')
    return redirect(url_for('template_kontrak'))


def generate_nomor_kontrak():
    """Menghasilkan nomor kontrak baru yang berurutan per tahun."""
    now = datetime.now()
    year = now.strftime('%y')  # '25' untuk 2025
    first_day_of_year = date(now.year, 1, 1)

    # Mengunci tabel dokumen untuk mencegah race condition (opsional tapi lebih aman)
    # Anda mungkin perlu menyesuaikan ini tergantung pada isolasi transaksi DB Anda
    try:
        last_kontrak_this_year = db.session.query(Dokumen).filter(
            Dokumen.jenis == 'Kontrak',
            Dokumen.tanggal_upload >= first_day_of_year
        ).with_for_update().order_by(Dokumen.id.desc()).first()

        nomor_urut = 1
        if last_kontrak_this_year and last_kontrak_this_year.nomor_surat:
            try:
                # SPK.064/KR/BKI-25 -> 64
                last_num_str = last_kontrak_this_year.nomor_surat.split('.')[1].split('/')[0]
                nomor_urut = int(last_num_str) + 1
            except (IndexError, ValueError):
                nomor_urut = 1  # Fallback jika format lama tidak sesuai

        nomor_urut_str = f"{nomor_urut:03d}"  # 001, 002, ..., 065
        # Sesuaikan 'KR/BKI' dengan kode perusahaan Anda jika perlu
        nomor_surat = f"SPK.{nomor_urut_str}/KR/BKI-{year}"
        return nomor_surat
    except Exception as e:
        print(f"Error saat generate nomor kontrak: {e}")
        # Return nomor sementara jika gagal query
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return f"TEMP.{timestamp}-{year}"


@app.route('/kontrak/generate/<int:karyawan_id>', methods=['POST'])
@login_required
def generate_kontrak(karyawan_id):
    karyawan = Karyawan.query.get_or_404(karyawan_id)
    template_id = request.form.get('template_id')
    if not template_id:
        flash('Silakan pilih template kontrak.', 'danger')
        return redirect(url_for('detail_karyawan', id=karyawan_id))

    template = TemplateKontrak.query.get_or_404(template_id)

    # Pastikan file template ada
    if not template.file_path or not os.path.exists(template.file_path):
        flash(f'File template "{template.nama_template}" tidak ditemukan di server.', 'danger')
        return redirect(url_for('detail_karyawan', id=karyawan_id))

    try:
        doc = DocxTemplate(template.file_path)
    except Exception as e:
        flash(f'Gagal memuat file template. Error: {e}', 'danger')
        return redirect(url_for('detail_karyawan', id=karyawan_id))

    nomor_surat_baru = generate_nomor_kontrak()

    context = {
        'nama': karyawan.nama or '',
        'nup': karyawan.nup or '',
        'nik': karyawan.nik or '',
        'jenis_kelamin': karyawan.jenis_kelamin or '',
        'tempat_lahir': karyawan.tempat_lahir or '',
        'tanggal_lahir': format_tanggal(karyawan.tanggal_lahir),
        'alamat': karyawan.alamat or '',
        'jabatan': karyawan.jabatan or '',
        'unit_kerja': karyawan.unit_kerja or '',
        'no_hp': karyawan.no_hp or '-',
        'gaji': format_rupiah(karyawan.gaji_honorarium),
        'tunjangan': format_rupiah(karyawan.tunjangan_tetap),
        'tanggal_mulai': format_tanggal(karyawan.tanggal_mulai),
        'tanggal_akhir': format_tanggal(karyawan.tanggal_akhir_kontrak),
        'nomor_surat': nomor_surat_baru
    }

    try:
        doc.render(context)
        # Buat nama file output yang bersih
        nama_file_aman = "".join(c if c.isalnum() else "_" for c in karyawan.nama)
        timestamp = date.today().strftime("%Y%m%d")
        output_filename = f"Kontrak_{nama_file_aman}_{timestamp}.docx"
        output_path = os.path.join(app.config['UPLOAD_FOLDER_KONTRAK'], secure_filename(output_filename))

        # Handle jika file dengan nama sama sudah ada (jarang terjadi tapi mungkin)
        counter = 1
        original_output_path = output_path
        while os.path.exists(output_path):
            base, ext = os.path.splitext(original_output_path)
            output_path = f"{base}_{counter}{ext}"
            counter += 1

        doc.save(output_path)

        # Simpan record dokumen ke DB
        new_kontrak = Dokumen(
            karyawan_id=karyawan.id,
            jenis='Kontrak',
            file_path=output_path,
            nomor_surat=nomor_surat_baru,
            tanggal_upload=date.today()
        )
        db.session.add(new_kontrak)
        db.session.commit()

        flash(f'Kontrak untuk {karyawan.nama} berhasil dibuat.', 'success')
    except Exception as e:
        db.session.rollback()
        # Jika gagal simpan/render, hapus file yang mungkin terbuat
        if 'output_path' in locals() and os.path.exists(output_path):
            os.remove(output_path)
        flash(f'Gagal membuat atau menyimpan kontrak. Periksa template dan data karyawan. Error: {str(e)}', 'danger')

    return redirect(url_for('detail_karyawan', id=karyawan_id))


# --- Perintah CLI ---
@app.cli.command("create-admin")
def create_admin():
    """Membuat user admin baru."""
    import getpass
    username = input("Masukkan username admin: ")
    # Validasi username tidak boleh kosong
    if not username:
        print("Error: Username tidak boleh kosong.")
        return

    password = getpass.getpass("Masukkan password: ")
    # Validasi password tidak boleh kosong
    if not password:
        print("Error: Password tidak boleh kosong.")
        return

    # Cek jika username sudah ada
    if User.query.filter_by(username=username).first():
        print(f"Error: User '{username}' sudah ada.")
        return

    try:
        new_admin = User(username=username)
        new_admin.set_password(password)
        db.session.add(new_admin)
        db.session.commit()
        print(f"User admin '{username}' berhasil dibuat.")
    except Exception as e:
        db.session.rollback()
        print(f"Gagal membuat admin. Error: {e}")


# --- Main execution ---
if __name__ == '__main__':
    # Gunakan host='0.0.0.0' jika ingin diakses dari jaringan lokal
    app.run(debug=True, host='0.0.0.0', port=5000)

