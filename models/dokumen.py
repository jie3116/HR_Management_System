from datetime import datetime
from . import db

class Dokumen(db.Model):
    __tablename__ = 'dokumen'

    id = db.Column(db.Integer, primary_key=True)
    karyawan_id = db.Column(db.Integer, db.ForeignKey('karyawan.id'), nullable=False)
    jenis = db.Column(db.String(50), nullable=False) # CV, KTP, Kontrak, SK
    file_path = db.Column(db.String(255), nullable=False)
    nomor_surat = db.Column(db.String(100), nullable=True) # Khusus untuk Kontrak/SK
    tanggal_upload = db.Column(db.Date, default=datetime.utcnow)

    def __repr__(self):
        return f'<Dokumen {self.jenis} - {self.karyawan.nama}>'

