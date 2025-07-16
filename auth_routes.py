from flask import Blueprint, render_template, request, redirect, url_for
from flask_login import login_user, logout_user, login_required
from models import User
from werkzeug.security import check_password_hash

auth_bp = Blueprint("auth", __name__)

# Redirecionar raiz para login
@auth_bp.route("/")
def home():
    return redirect(url_for("auth.login"))

# Rota de login
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form['username']
        password = request.form['password']

        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            login_user(user)
            # Redireciona baseado no papel do usuário
            if user.role == "admin":
                return redirect(url_for('admin.dashboard'))
            else:
                return redirect(url_for('cliente.dashboard'))
        else:
            return render_template("login.html", error="Credenciais inválidas.")

    return render_template("login.html")

@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))  # usa o nome da rota, não do blueprint

