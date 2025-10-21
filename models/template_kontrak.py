from . import db

class TemplateKontrak(db.Model):
    __tablename__ = 'template_kontrak'

    id = db.Column(db.Integer, primary_key=True)
    nama_template = db.Column(db.String(150), nullable=False)
    file_path = db.Column(db.String(255), nullable=False)

    def __repr__(self):
        return f'<TemplateKontrak {self.nama_template}>'

