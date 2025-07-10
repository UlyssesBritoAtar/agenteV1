from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate  # ✅ IMPORTANTE
import os

from sqlalchemy import create_engine, text
from werkzeug.security import generate_password_hash

from app_disparo_cliente import disparo_bp
from chat_bot_v3 import chat_bot_v3_bp
from models import db, User
from auth_routes import auth_bp
from admin_routes import admin_bp
from cliente_routes import cliente_bp
import secrets

# Configurações
DB_NAME = "chatbot1"

DATA_BASE_URL =os.getenv("DATABASE_URL")

# Cria banco se não existir
engine = create_engine(DATA_BASE_URL)
with engine.connect() as conn:
    conn.execute(text(f"CREATE DATABASE IF NOT EXISTS {DB_NAME} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))

# Inicializa Flask
app = Flask(__name__)
app.secret_key = secrets.token_hex(16)  # Gera uma chave secreta aleatória de 32 caracteres

app.config["SQLALCHEMY_DATABASE_URI"] = DATA_BASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Inicializa DB e Migrate
db.init_app(app)
migrate = Migrate(app, db)  # ✅ ATIVA FLASK-MIGRATE

# Inicializa LoginManager
login_manager = LoginManager(app)
login_manager.login_view = 'auth.login'

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# Registra rotas
app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(cliente_bp)
app.register_blueprint(chat_bot_v3_bp)
app.register_blueprint(disparo_bp)

# Inicialização
if __name__ == "__main__":
    with app.app_context():
        db.create_all()

        # Criação do admin automático se não existir
        if not User.query.filter_by(username="admin").first():
            admin_user = User(
                username="admin",
                password=generate_password_hash("admin123"),
                role="admin"
            )
            db.session.add(admin_user)
            db.session.commit()
            print("✅ Usuário admin criado com sucesso.")
        else:
            print("✔ Usuário admin já existe.")

    app.run(debug=True, port=5000)
