from . import db
from datetime import date


class Karyawan(db.Model):
    __tablename__ = 'karyawan'

    id = db.Column(db.Integer, primary_key=True)
    nama = db.Column(db.String(150), nullable=False)
    jenis_kelamin = db.Column(db.String(20), nullable=False)
    nup = db.Column(db.String(50), unique=True, nullable=False)
    tempat_lahir = db.Column(db.String(150), nullable=False)
    tanggal_lahir = db.Column(db.Date, nullable=False)
    nik = db.Column(db.String(50), unique=True, nullable=False)
    alamat = db.Column(db.String(255), nullable=True)
    no_hp = db.Column(db.String(20), nullable=True)
    jabatan = db.Column(db.String(100), nullable=True)
    unit_kerja = db.Column(db.String(100), nullable=True)
    email = db.Column(db.String(120), unique=True, nullable=True)
    tanggal_mulai = db.Column(db.Date, nullable=False)
    tanggal_akhir_kontrak = db.Column(db.Date, nullable=True)
    gaji_honorarium = db.Column(db.Integer, nullable=True)
    tunjangan_tetap = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(50), default='Aktif', nullable=False)
    tindak_lanjut_kontrak = db.Column(
        db.String(100),
        nullable=False,
        default='Tidak perlu',
        server_default='Tidak perlu'
    )

    dokumen = db.relationship('Dokumen', backref='karyawan', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Karyawan {self.nama}>'

    @property
    def sisa_kontrak(self):
        if self.tanggal_akhir_kontrak:
            today = date.today()
            delta = self.tanggal_akhir_kontrak - today
            if delta.days < 0:
                return 0
            return delta.days
        return None

