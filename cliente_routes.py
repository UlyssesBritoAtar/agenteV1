from flask import Blueprint, request, redirect, url_for, render_template, jsonify, flash, abort
from flask_login import login_required, current_user
from models import db, Cliente, Agente
import os
import json
import requests

cliente_bp = Blueprint("cliente", __name__, url_prefix='/cliente')

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@cliente_bp.route("/dashboard", methods=["GET"])
@login_required
def dashboard():
    if not current_user.cliente_id:
        flash("Acesso negado: usuário sem cliente vinculado.", "danger")
        return redirect(url_for('auth.logout'))

    cliente = Cliente.query.get_or_404(current_user.cliente_id)
    agentes = cliente.agentes
    return render_template("cliente_dashboard.html", cliente=cliente, agentes=agentes)

# === ROTAS DE DISPARO — COMENTADAS (já tratadas em disparo_bp) ===

# @cliente_bp.route("/disparar", methods=["POST"])
# @login_required
# def disparar():
#     # Essa lógica está agora em /disparo/cliente/disparar
#     return redirect(url_for('cliente.dashboard'))

# @cliente_bp.route("/status")
# @login_required
# def status():
#     return jsonify({"logs": [], "paused": False})

# @cliente_bp.route("/pause", methods=["POST"])
# @login_required
# def pause():
#     return jsonify({"status": "⏸ Pausado"})

# @cliente_bp.route("/cancelar", methods=["POST"])
# @login_required
# def cancelar():
#     return jsonify({"status": "cancelado"})

# === ROTAS DE GERENCIAMENTO DE AGENTES ===

@cliente_bp.route("/agente/desativar_numero/<int:agente_id>", methods=["POST"])
@login_required
def desativar_agente_telefone(agente_id):
    agente = Agente.query.get_or_404(agente_id)
    if agente.cliente_id != current_user.cliente_id:
        flash("Acesso negado: agente não pertence ao seu cliente.", "danger")
        return redirect(url_for('cliente.dashboard'))

    numero = request.form['telefone'].strip()
    try:
        bloqueios = json.loads(agente.desativados_por_telefone or "[]")
    except json.JSONDecodeError:
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

@cliente_bp.route("/agente/reativar_numero/<int:agente_id>", methods=["POST"])
@login_required
def reativar_agente_telefone(agente_id):
    agente = Agente.query.get_or_404(agente_id)
    numero = request.form['telefone'].strip()

    try:
        bloqueios = json.loads(agente.desativados_por_telefone or "[]")
    except json.JSONDecodeError:
        bloqueios = []

    if numero in bloqueios:
        bloqueios.remove(numero)
        agente.desativados_por_telefone = json.dumps(bloqueios)
        db.session.commit()
        print(f"✅ Número {numero} removido dos bloqueios do agente {agente.id}")
        flash(f"Agente reativado para o número {numero}!", "success")
    else:
        print(f"⚠ Número {numero} não estava bloqueado para o agente {agente.id}")
        flash(f"O número {numero} não estava bloqueado.", "info")

    return redirect(url_for('cliente.dashboard'))

@cliente_bp.route("/agente/ativar/<int:agente_id>")
@login_required
def ativar_agente(agente_id):
    agente = Agente.query.get_or_404(agente_id)
    if not current_user.cliente_id or agente.cliente_id != current_user.cliente_id:
        abort(403)
    agente.ativo = True
    db.session.commit()
    db.session.refresh(agente)
    flash("Agente ativado com sucesso!", "success")
    return redirect(url_for('cliente.dashboard'))

@cliente_bp.route("/agente/desativar/<int:agente_id>")
@login_required
def desativar_agente(agente_id):
    agente = Agente.query.get_or_404(agente_id)
    if not current_user.cliente_id or agente.cliente_id != current_user.cliente_id:
        abort(403)
    agente.ativo = False
    db.session.commit()
    db.session.refresh(agente)
    flash("Agente desativado com sucesso!", "success")
    return redirect(url_for('cliente.dashboard'))

@cliente_bp.route("/conectar-instancia/<int:agente_id>")
@login_required
def conectar_instancia(agente_id):
    agente = Agente.query.get_or_404(agente_id)
    if not current_user.cliente_id or agente.cliente_id != current_user.cliente_id:
        abort(403)

    instance_key = agente.instance_key
    api_key = agente.api_key

    headers = {"apikey": api_key, "Content-Type": "application/json"}
    url = f"https://evolution.modware.com.br/instance/connect/{instance_key}"

    response = requests.request("GET", url, headers=headers)
    return response.json()
