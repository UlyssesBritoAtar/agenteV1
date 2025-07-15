import random
import string
import os
import json
from flask import Blueprint, request, redirect, url_for, render_template, flash
from models import db, Cliente, Agente, User
from middleware import login_required
from werkzeug.security import generate_password_hash

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

UPLOAD_FOLDER = "uploads/agentes"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def gerar_senha_aleatoria(tamanho=12):
    caracteres = string.ascii_letters + string.digits
    senha = ''.join(random.choice(caracteres) for _ in range(tamanho))
    return senha

def gerar_login(nome_cliente):
    return nome_cliente.lower().replace(" ", ".")

@admin_bp.route("/dashboard")
@login_required(role="admin")
def dashboard():
    clientes = Cliente.query.all()
    return render_template("admin_dashboard.html", clientes=clientes)

@admin_bp.route("/cliente/add", methods=["GET", "POST"])
@login_required(role="admin")
def add_cliente():
    if request.method == "POST":
        nome = request.form['nome']
        telefone = request.form['telefone']

        login = gerar_login(nome)
        senha_plana = gerar_senha_aleatoria()
        senha_hash = generate_password_hash(senha_plana)

        if User.query.filter_by(username=login).first():
            flash("Login já existente, escolha outro nome.", "danger")
            return redirect(url_for('admin.add_cliente'))

        cliente = Cliente(nome=nome, telefone=telefone)
        db.session.add(cliente)
        db.session.commit()

        user = User(username=login, password=senha_hash, role="cliente", cliente_id=cliente.id)
        db.session.add(user)
        db.session.commit()

        flash(f"Cliente criado com sucesso! Login: {login} | Senha: {senha_plana}", "success")
        return redirect(url_for('admin.dashboard'))

    return render_template("admin_add_cliente.html")

@admin_bp.route("/cliente/edit/<int:cliente_id>", methods=["GET", "POST"])
@login_required(role="admin")
def editar_cliente(cliente_id):
    cliente = Cliente.query.get_or_404(cliente_id)
    user = User.query.filter_by(cliente_id=cliente.id).first()

    if request.method == "POST":
        novo_login = request.form['login']
        nova_senha = request.form['senha']

        if not novo_login or not nova_senha:
            flash("Login e senha não podem estar vazios!", "danger")
            return redirect(url_for('admin.editar_cliente', cliente_id=cliente.id))

        user.username = novo_login
        user.password = generate_password_hash(nova_senha)
        db.session.commit()

        flash("Login e senha atualizados com sucesso!", "success")
        return redirect(url_for('admin.dashboard'))

    return render_template("admin_edit_cliente.html", cliente=cliente, login=user.username, senha="")

@admin_bp.route("/agente/add/<int:cliente_id>", methods=["GET", "POST"])
@login_required(role="admin")
def add_agente(cliente_id):
    cliente = Cliente.query.get_or_404(cliente_id)

    if request.method == "POST":
        nome = request.form['nome']
        instance_key = request.form['instance_key']
        api_key = request.form['api_key']
        numero_operador = request.form.get('numero_operador', '').strip()
        instrucoes_texto = request.form['instrucoes_texto']
        params_json_str = request.form['params_json']

        print("DADOS A SALVAR:")
        print("NOME:", nome)
        print("INSTANCE_KEY:", instance_key)
        print("API_KEY:", api_key)
        print("INSTRUÇÕES:", instrucoes_texto)
        print("PARAMS:", params_json_str)

        try:
            json.loads(params_json_str)
        except json.JSONDecodeError:
            flash("Params JSON inválido!", "danger")
            return redirect(url_for('admin.add_agente', cliente_id=cliente.id))

        agente = Agente(
            nome=nome,
            cliente_id=cliente_id,
            arquivo_instrucoes=instrucoes_texto,
            arquivo_params=params_json_str,
            api_key=api_key,
            instance_key=instance_key,
            numero_operador=numero_operador,
            ativo=True
        )

        db.session.add(agente)
        db.session.commit()

        flash("Agente criado com sucesso!", "success")
        return redirect(url_for('admin.dashboard'))

    return render_template("admin_add_agente.html", cliente=cliente)

@admin_bp.route("/agente/reativar_numero/<int:agente_id>", methods=["POST"])
@login_required(role="admin")
def reativar_agente_telefone(agente_id):
    agente = Agente.query.get_or_404(agente_id)
    numero = request.form['telefone'].strip()

    try:
        bloqueios = json.loads(agente.desativados_por_telefone)
    except:
        bloqueios = []

    if numero in bloqueios:
        bloqueios.remove(numero)
        agente.desativados_por_telefone = json.dumps(bloqueios)
        db.session.commit()
        print(f"✅ Número {numero} removido dos bloqueios do agente {agente.id}")
    else:
        print(f"⚠ Número {numero} não estava bloqueado para o agente {agente.id}")

    flash(f"Agente reativado para o número {numero}!", "success")
    return redirect(url_for('cliente.dashboard'))


@admin_bp.route("/cliente/delete/<int:cliente_id>", methods=["POST"])
@login_required(role="admin")
def delete_cliente(cliente_id):
    cliente = Cliente.query.get_or_404(cliente_id)

    # 1. Deleta conversas antes de deletar agentes
    for agente in cliente.agentes:
        if hasattr(agente, 'conversas'):
            for conversa in agente.conversas:
                db.session.delete(conversa)
        db.session.delete(agente)

    # 2. Deleta o usuário vinculado
    user = User.query.filter_by(cliente_id=cliente.id).first()
    if user:
        db.session.delete(user)

    # 3. Deleta o cliente
    db.session.delete(cliente)
    db.session.commit()

    flash("Cliente excluído com sucesso!", "success")
    return redirect(url_for('admin.dashboard'))


@admin_bp.route("/agente/ativar/<int:agente_id>")
@login_required(role="admin")
def ativar_agente_global(agente_id):
    agente = Agente.query.get_or_404(agente_id)
    agente.ativo = True
    db.session.commit()
    flash("Agente ativado globalmente!", "success")
    return redirect(url_for('cliente.dashboard'))

@admin_bp.route("/agente/desativar/<int:agente_id>")
@login_required(role="admin")
def desativar_agente_global(agente_id):
    agente = Agente.query.get_or_404(agente_id)
    agente.ativo = False
    db.session.commit()
    flash("Agente desativado globalmente!", "success")
    return redirect(url_for('cliente.dashboard'))

@admin_bp.route("/agente/desativar_numero/<int:agente_id>", methods=["POST"])
def desativar_agente_telefone(agente_id):
    agente = Agente.query.get_or_404(agente_id)
    numero = request.form['telefone'].strip()

    try:
        bloqueios = json.loads(agente.desativados_por_telefone)
        print(bloqueios)
    except:
        bloqueios = []


    if numero not in bloqueios:
        bloqueios.append(numero)

        agente.desativados_por_telefone = json.dumps(bloqueios)
        db.session.commit()
        print(f"✅ Número {numero} adicionado à lista de bloqueios do agente {agente.id}")
    else:
        print(f"⚠ Número {numero} já estava bloqueado para o agente {agente.id}")

    flash(f"Agente desativado para o número {numero}!", "success")
    return redirect(url_for('cliente.dashboard'))

@admin_bp.route("/cliente/<int:cliente_id>/agentes", methods=["GET"])
@login_required(role="admin")
def listar_agentes(cliente_id):
    cliente = Cliente.query.get_or_404(cliente_id)
    agentes = Agente.query.filter_by(cliente_id=cliente.id).all()
    return render_template("admin_listar_agentes.html", cliente=cliente, agentes=agentes)

@admin_bp.route("/agente/edit/<int:agente_id>", methods=["GET", "POST"])
@login_required(role="admin")
def editar_agente(agente_id):
    agente = Agente.query.get_or_404(agente_id)
    cliente = agente.cliente

    if request.method == "POST":
        nome = request.form['nome']
        api_key = request.form['api_key']
        instance_key = request.form['instance_key']
        numero_operador = request.form['numero_operador'].strip()
        instrucoes_texto = request.form['instrucoes_texto']
        params_json = request.form['params_json']

        try:
            json.loads(params_json)
        except json.JSONDecodeError:
            flash("Params JSON inválido!", "danger")
            return redirect(url_for('admin.editar_agente', agente_id=agente.id))

        agente.nome = nome
        agente.api_key = api_key
        agente.instance_key = instance_key
        agente.numero_operador = numero_operador
        agente.arquivo_instrucoes = instrucoes_texto
        agente.arquivo_params = params_json

        db.session.commit()
        flash("Agente atualizado com sucesso!", "success")
        return redirect(url_for('admin.listar_agentes', cliente_id=cliente.id))

    return render_template("admin_editar_agente.html", agente=agente, cliente=cliente)
@admin_bp.route("/agente/delete/<int:agente_id>", methods=["POST"])
@login_required(role="admin")
def excluir_agente(agente_id):
    agente = Agente.query.get_or_404(agente_id)
    cliente_id = agente.cliente_id

    # Exclui conversas associadas (se existirem)
    if hasattr(agente, 'conversas'):
        for conversa in agente.conversas:
            db.session.delete(conversa)

    # Exclui logs de disparo associados (se existirem)
    if hasattr(agente, 'disparo_logs'):
        for log in agente.disparo_logs:
            db.session.delete(log)

    # Agora sim, exclui o agente
    db.session.delete(agente)
    db.session.commit()

    flash(f"Agente {agente.nome} excluído com sucesso!", "success")
    return redirect(url_for('admin.listar_agentes', cliente_id=cliente_id))

