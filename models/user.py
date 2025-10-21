from werkzeug.security import generate_password_hash, check_password_hash
from . import db # Menggunakan . untuk import relatif dari paket yang sama

class User(db.Model):
    __tablename__ = 'user' # Sebaiknya nama tabel lowercase

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True, nullable=False)
    password_hash = db.Column(db.String(256))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'