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
from sqlalchemy import or_
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

# Daftar Status PKWT
STATUS_TINDAK_LANJUT_OPTIONS = [
    'Tidak perlu',
    'Belum ditindaklanjuti',
    'Telah dikonfirmasi ke cabang/unit kerja',
    'Dalam proses perpanjangan kontrak',
    'Tidak diperpanjang'
]


# Fungsi Pengecekan Status PKWT
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
        print(f"Error saat update status otomatis: {e}")


# Helper Functions & Decorators
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
    return "{:,.0f}".format(value).replace(',', '.')


def format_tanggal(value):
    if value is None:
        return "-"
    return value.strftime("%d %B %Y")


def get_basename(path):
    return os.path.basename(path)


app.jinja_env.filters['rupiah'] = format_rupiah
app.jinja_env.filters['tanggal'] = format_tanggal
app.jinja_env.filters['basename'] = get_basename


# Rute Autentikasi
@app.route('/login', methods=['GET', 'POST'])
def login():
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


# Rute Utama
@app.route('/')
@login_required
def index():
    return redirect(url_for('dashboard'))


@app.route('/dashboard')
@login_required
def dashboard():
    check_and_update_statuses()
    search_query = request.args.get('search', '')
    total_karyawan = Karyawan.query.count()
    today = date.today()
    ninety_days_later = today + timedelta(days=90)
    kontrak_akan_habis = Karyawan.query.filter(
        Karyawan.tanggal_akhir_kontrak.isnot(None),
        Karyawan.tanggal_akhir_kontrak <= ninety_days_later,
        Karyawan.tanggal_akhir_kontrak >= today,
        Karyawan.status == 'Aktif'
    ).order_by(Karyawan.tanggal_akhir_kontrak).all()
    query = Karyawan.query.filter_by(status='Aktif')
    if search_query:
        search_term = f"%{search_query}%"
        query = query.filter(
            or_(
                Karyawan.nama.ilike(search_term),
                Karyawan.nup.ilike(search_term),
                Karyawan.jabatan.ilike(search_term)
            )
        )
    semua_karyawan_aktif = query.order_by(Karyawan.nama).all()
    return render_template('dashboard.html',
                           total_karyawan=total_karyawan,
                           kontrak_akan_habis=kontrak_akan_habis,
                           semua_karyawan_aktif=semua_karyawan_aktif,
                           search_query=search_query,
                           status_options=STATUS_TINDAK_LANJUT_OPTIONS)


# Rute Karyawan
@app.route('/karyawan')
@login_required
def karyawan():
    semua_karyawan = Karyawan.query.order_by(Karyawan.nama).all()
    return render_template('karyawan.html', semua_karyawan=semua_karyawan)


@app.route('/karyawan/tambah', methods=['POST'])
@login_required
def tambah_karyawan():
    try:
        new_karyawan = Karyawan(
            nama=request.form['nama'],
            jenis_kelamin=request.form['jenis_kelamin'],
            nup=request.form['nup'],
            tempat_lahir=request.form['tempat_lahir'],
            tanggal_lahir=datetime.strptime(request.form['tanggal_lahir'], '%Y-%m-%d').date(),
            nik=request.form['nik'],
            alamat=request.form.get('alamat'),
            no_hp=request.form.get('no_hp'),
            jabatan=request.form.get('jabatan'),
            unit_kerja=request.form.get('unit_kerja'),
            email=request.form.get('email'),
            tanggal_mulai=datetime.strptime(request.form['tanggal_mulai'], '%Y-%m-%d').date(),
            tanggal_akhir_kontrak=datetime.strptime(request.form.get('tanggal_akhir_kontrak'),
                                                    '%Y-%m-%d').date() if request.form.get(
                'tanggal_akhir_kontrak') else None,
            gaji_honorarium=int(request.form.get('gaji_honorarium')) if request.form.get('gaji_honorarium') else 0,
            tunjangan_tetap=int(request.form.get('tunjangan_tetap')) if request.form.get('tunjangan_tetap') else 0,
            status=request.form['status']
        )
        db.session.add(new_karyawan)
        db.session.commit()
        flash('Karyawan baru berhasil ditambahkan.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Gagal menambahkan karyawan. Error: {str(e)}', 'danger')
    return redirect(url_for('karyawan'))


# Rute untuk Unggah Massal
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
            workbook = openpyxl.load_workbook(file)
            sheet = workbook.active

            # Lewati baris header
            for row in sheet.iter_rows(min_row=2, values_only=True):
                if not all([row[0], row[2], row[4], row[5], row[11]]):
                    flash(f"Baris data tidak lengkap, NUP: {row[2]}. Data dilewati.", 'warning')
                    continue

                if Karyawan.query.filter(or_(Karyawan.nup == str(row[2]), Karyawan.nik == str(row[5]))).first():
                    flash(f"Karyawan dengan NUP {row[2]} atau NIK {row[5]} sudah ada. Data dilewati.", 'warning')
                    continue

                new_karyawan = Karyawan(
                    nama=row[0],
                    jenis_kelamin=row[1],
                    nup=str(row[2]),
                    tempat_lahir=row[3],
                    tanggal_lahir=row[4],
                    nik=str(row[5]),
                    alamat=row[6],
                    no_hp=str(row[7]),
                    jabatan=row[8],
                    unit_kerja=row[9],
                    email=row[10],
                    tanggal_mulai=row[11],
                    tanggal_akhir_kontrak=row[12],
                    gaji_honorarium=int(row[13]) if row[13] else 0,
                    tunjangan_tetap=int(row[14]) if row[14] else 0,
                    status=row[15] or 'Aktif'
                )
                db.session.add(new_karyawan)

            db.session.commit()
            flash('Data karyawan dari file Excel berhasil diunggah.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Terjadi kesalahan saat memproses file Excel. Error: {e}', 'danger')
    else:
        flash('Format file tidak diizinkan. Harap unggah file .xlsx.', 'warning')

    return redirect(url_for('karyawan'))


@app.route('/karyawan/download_template')
@login_required
def download_template_excel():
    return send_from_directory('static', 'template_karyawan.xlsx', as_attachment=True)


@app.route('/karyawan/detail/<int:id>')
@login_required
def detail_karyawan(id):
    karyawan = Karyawan.query.get_or_404(id)
    templates = TemplateKontrak.query.all()
    return render_template('detail_karyawan.html',
                           karyawan=karyawan,
                           templates=templates,
                           status_options=STATUS_TINDAK_LANJUT_OPTIONS)


@app.route('/karyawan/edit/<int:id>', methods=['POST'])
@login_required
def edit_karyawan(id):
    karyawan_to_edit = Karyawan.query.get_or_404(id)
    try:
        karyawan_to_edit.nama = request.form['nama']
        karyawan_to_edit.jenis_kelamin = request.form['jenis_kelamin']
        karyawan_to_edit.nup = request.form['nup']
        karyawan_to_edit.tempat_lahir = request.form['tempat_lahir']
        karyawan_to_edit.tanggal_lahir = datetime.strptime(request.form['tanggal_lahir'], '%Y-%m-%d').date()
        karyawan_to_edit.nik = request.form['nik']
        karyawan_to_edit.alamat = request.form.get('alamat')
        karyawan_to_edit.no_hp = request.form.get('no_hp')
        karyawan_to_edit.jabatan = request.form.get('jabatan')
        karyawan_to_edit.unit_kerja = request.form.get('unit_kerja')
        karyawan_to_edit.email = request.form.get('email')
        karyawan_to_edit.tanggal_mulai = datetime.strptime(request.form['tanggal_mulai'], '%Y-%m-%d').date()
        karyawan_to_edit.tanggal_akhir_kontrak = datetime.strptime(request.form.get('tanggal_akhir_kontrak'),
                                                                   '%Y-%m-%d').date() if request.form.get(
            'tanggal_akhir_kontrak') else None
        karyawan_to_edit.gaji_honorarium = int(request.form.get('gaji_honorarium')) if request.form.get(
            'gaji_honorarium') else 0
        karyawan_to_edit.tunjangan_tetap = int(request.form.get('tunjangan_tetap')) if request.form.get(
            'tunjangan_tetap') else 0
        karyawan_to_edit.status = request.form['status']
        karyawan_to_edit.tindak_lanjut_kontrak = request.form['tindak_lanjut_kontrak']
        db.session.commit()
        flash('Data karyawan berhasil diperbarui.', 'success')
    except Exception as e:
        db.session.rollback()
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
    return redirect(url_for('dashboard'))


@app.route('/karyawan/hapus/<int:id>', methods=['POST'])
@login_required
def hapus_karyawan(id):
    karyawan_to_delete = Karyawan.query.get_or_404(id)
    try:
        for doc in karyawan_to_delete.dokumen:
            if os.path.exists(doc.file_path):
                os.remove(doc.file_path)

        db.session.delete(karyawan_to_delete)
        db.session.commit()
        flash('Karyawan dan semua dokumen terkait berhasil dihapus.', 'success')
        return redirect(url_for('karyawan'))
    except Exception as e:
        db.session.rollback()
        flash(f'Gagal menghapus karyawan. Error: {str(e)}', 'danger')
        return redirect(url_for('karyawan'))


# Rute Dokumen
@app.route('/dokumen/upload/<int:karyawan_id>', methods=['POST'])
@login_required
def upload_dokumen(karyawan_id):
    karyawan = Karyawan.query.get_or_404(karyawan_id)
    if 'file' not in request.files:
        flash('Tidak ada file yang dipilih.', 'danger')
        return redirect(url_for('detail_karyawan', id=karyawan_id))

    file = request.files['file']
    jenis_dokumen = request.form['jenis_dokumen']

    if file.filename == '':
        flash('Tidak ada file yang dipilih.', 'danger')
        return redirect(url_for('detail_karyawan', id=karyawan_id))

    if file and allowed_file(file.filename, app.config['ALLOWED_EXTENSIONS_DOC']):
        filename = secure_filename(f"{karyawan.nup}_{jenis_dokumen}_{file.filename}")
        file_path = os.path.join(app.config['UPLOAD_FOLDER_DOC'], filename)

        try:
            file.save(file_path)
            new_dokumen = Dokumen(
                karyawan_id=karyawan_id,
                jenis=jenis_dokumen,
                file_path=file_path
            )
            db.session.add(new_dokumen)
            db.session.commit()
            flash('Dokumen berhasil diunggah.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Gagal menyimpan dokumen. Error: {str(e)}', 'danger')

    return redirect(url_for('detail_karyawan', id=karyawan_id))


@app.route('/dokumen/download/<int:dokumen_id>')
@login_required
def download_dokumen(dokumen_id):
    dokumen = Dokumen.query.get_or_404(dokumen_id)
    try:
        directory = os.path.dirname(dokumen.file_path)
        filename = os.path.basename(dokumen.file_path)
        return send_from_directory(directory, filename, as_attachment=True)
    except FileNotFoundError:
        flash('File tidak ditemukan di server.', 'danger')
        return redirect(url_for('detail_karyawan', id=dokumen.karyawan_id))


# Rute Template Kontrak
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
    nama_template = request.form['nama_template']

    if file.filename == '' or nama_template == '':
        flash('Nama template dan file tidak boleh kosong.', 'danger')
        return redirect(url_for('template_kontrak'))

    if file and allowed_file(file.filename, {'docx'}):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER_TEMPLATE'], filename)

        try:
            file.save(file_path)
            new_template = TemplateKontrak(nama_template=nama_template, file_path=file_path)
            db.session.add(new_template)
            db.session.commit()
            flash('Template berhasil diunggah.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Gagal menyimpan template. Error: {str(e)}', 'danger')
    else:
        flash('Format file tidak diizinkan. Harap unggah file .docx', 'warning')

    return redirect(url_for('template_kontrak'))


def generate_nomor_kontrak():
    now = datetime.now()
    year = now.strftime('%y')

    first_day_of_year = date(now.year, 1, 1)
    last_kontrak_this_year = db.session.query(Dokumen).filter(
        Dokumen.jenis == 'Kontrak',
        Dokumen.tanggal_upload >= first_day_of_year
    ).order_by(Dokumen.id.desc()).first()

    nomor_urut = 1
    if last_kontrak_this_year and last_kontrak_this_year.nomor_surat:
        try:
            last_num_str = last_kontrak_this_year.nomor_surat.split('.')[1].split('/')[0]
            nomor_urut = int(last_num_str) + 1
        except (IndexError, ValueError):
            nomor_urut = 1

    nomor_urut_str = f"{nomor_urut:03d}"
    nomor_surat = f"SPK.{nomor_urut_str}/KR/BKI-{year}"
    return nomor_surat


@app.route('/kontrak/generate/<int:karyawan_id>', methods=['POST'])
@login_required
def generate_kontrak(karyawan_id):
    karyawan = Karyawan.query.get_or_404(karyawan_id)
    template_id = request.form.get('template_id')
    if not template_id:
        flash('Silakan pilih template kontrak.', 'danger')
        return redirect(url_for('detail_karyawan', id=karyawan_id))

    template = TemplateKontrak.query.get_or_404(template_id)
    doc = DocxTemplate(template.file_path)

    nomor_surat_baru = generate_nomor_kontrak()

    context = {
        'nama': karyawan.nama,
        'nup': karyawan.nup,
        'nik': karyawan.nik,
        'jenis_kelamin': karyawan.jenis_kelamin,
        'tempat_lahir': karyawan.tempat_lahir,
        'tanggal_lahir': format_tanggal(karyawan.tanggal_lahir),
        'alamat': karyawan.alamat,
        'jabatan': karyawan.jabatan,
        'unit_kerja': karyawan.unit_kerja,
        'no_hp': karyawan.no_hp or '-',
        'gaji': format_rupiah(karyawan.gaji_honorarium),
        'tunjangan': format_rupiah(karyawan.tunjangan_tetap),
        'tanggal_mulai': format_tanggal(karyawan.tanggal_mulai),
        'tanggal_akhir': format_tanggal(karyawan.tanggal_akhir_kontrak),
        'nomor_surat': nomor_surat_baru
    }

    doc.render(context)

    try:
        output_filename = f"Kontrak_{karyawan.nama.replace(' ', '_')}_{date.today()}.docx"
        output_path = os.path.join(app.config['UPLOAD_FOLDER_KONTRAK'], secure_filename(output_filename))
        doc.save(output_path)

        new_kontrak = Dokumen(
            karyawan_id=karyawan.id,
            jenis='Kontrak',
            file_path=output_path,
            nomor_surat=nomor_surat_baru
        )
        db.session.add(new_kontrak)
        db.session.commit()

        flash(f'Kontrak untuk {karyawan.nama} berhasil dibuat.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Gagal menyimpan kontrak. Error: {str(e)}', 'danger')

    return redirect(url_for('detail_karyawan', id=karyawan_id))


# Perintah CLI
@app.cli.command("create-admin")
def create_admin():
    """Membuat user admin baru."""
    import getpass
    username = input("Masukkan username admin: ")
    password = getpass.getpass("Masukkan password: ")

    if User.query.filter_by(username=username).first():
        print(f"Error: User '{username}' sudah ada.")
        return

    new_admin = User(username=username)
    new_admin.set_password(password)
    db.session.add(new_admin)
    db.session.commit()
    print(f"User admin '{username}' berhasil dibuat.")


# Main execution
if __name__ == '__main__':
    app.run(debug=True)

