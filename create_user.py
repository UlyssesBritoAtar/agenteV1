from werkzeug.security import generate_password_hash
from models import db, User
from app import app

with app.app_context():
    # Criar usuários usando hash
    admin = User(username="admin", password=generate_password_hash("admin123"), role="admin", cliente_id=None)
    cliente = User(username="may", password=generate_password_hash("123456"), role="cliente", cliente_id=1)

    db.session.add(admin)
    db.session.add(cliente)
    db.session.commit()

    print("Usuários criados com sucesso (usando hash).")
