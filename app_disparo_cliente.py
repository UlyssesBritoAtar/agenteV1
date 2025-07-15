from flask import Blueprint, request, jsonify, current_app
from flask_login import current_user, login_required
from models import db, Agente, DisparoLog
import pandas as pd
import threading
import time
import re
import requests
import random
from tenacity import retry, stop_after_attempt, wait_exponential

disparo_bp = Blueprint("disparo", __name__, url_prefix='/disparo')

log_store = {}
pause_status = {}
store_lock = threading.Lock()

eventos_disparo = {}
respostas_esperadas_por_cliente = {}

def extrair_numeros(telefone: str) -> str:
    telefone_str = str(telefone).split(".")[0]  # Remove ".0" caso exista
    return re.sub(r"[^\d]", "", telefone_str)


def adicionar_log(cliente_id, mensagem):
    with store_lock:
        log_store.setdefault(cliente_id, []).append(mensagem)

def get_pause_status(cliente_id):
    with store_lock:
        pause_status.setdefault(cliente_id, {"paused": False, "running": False})
        return pause_status[cliente_id].copy()

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def enviar_whatsapp(api_key, instance_key, telefone, mensagem):
    numero_limpo = extrair_numeros(telefone)
    payload = {"number": numero_limpo, "text": mensagem}
    headers = {"apikey": api_key, "Content-Type": "application/json"}
    url = f"https://evolution.modware.com.br/message/sendText/{instance_key}"
    response = requests.post(url, json=payload, timeout=12, headers=headers)
    response.raise_for_status()
    return f"✅ Mensagem enviada para {numero_limpo}"

@disparo_bp.route("/cliente/disparar", methods=["POST"])
@login_required
def cliente_disparar():
    try:
        cliente_id = current_user.cliente_id
        if not cliente_id:
            return jsonify({"error": "Cliente não autenticado corretamente."}), 403

        agente = Agente.query.filter_by(cliente_id=cliente_id).first()
        if not agente:
            return jsonify({"error": "❌ Nenhum agente ativo para este cliente."}), 400

        if agente.disparo_ativo:
            return jsonify({"error": "Já existe um disparo em andamento."}), 400

        file = request.files.get('file')
        if not file or not file.filename.endswith('.xlsx'):
            return jsonify({"error": "❗ Arquivo inválido"}), 400

        df_temp = pd.read_excel(file)
        if df_temp.shape[1] < 2:
            return jsonify({"error": "Planilha precisa de ao menos duas colunas (nome e telefone)."}), 400

        telefone_coluna = df_temp.columns[1]
        df = pd.read_excel(file, dtype={telefone_coluna: str})

        if df.shape[1] < 2:
            return jsonify({"error": "Planilha precisa de ao menos duas colunas (nome e telefone)."}), 400



        intervalo = request.form['intervalo_mensagem']
        quantidade_pausa = request.form['quantidade_pausa']
        tempo_pausa = request.form['tempo_pausa']
        mensagem_modelo = request.form["mensagem"]


        with store_lock:
            log_store[cliente_id] = []
            pause_status[cliente_id] = {"paused": False, "running": True}
            eventos_disparo[cliente_id] = threading.Event()
            eventos_disparo[cliente_id].set()

        threading.Thread(
            target=executar_disparo,
            args=(df, intervalo, quantidade_pausa, tempo_pausa, mensagem_modelo,
                  agente.id, agente.api_key, agente.instance_key, cliente_id, current_app._get_current_object()),
            daemon=True
        ).start()

        agente.disparo_ativo = True
        db.session.commit()

        adicionar_log(cliente_id, "🚀 Disparo iniciado!")
        return jsonify({"status": "ok"})

    except Exception as e:
        print(f"❌ Erro ao disparar: {e}")
        return jsonify({"error": str(e)}), 500

def executar_disparo(df, intervalo, quantidade_pausa, tempo_pausa, mensagem_modelo,
                     agente_id, api_key, instance_key, cliente_id, app):
    with app.app_context():
        print(get_valor_aleatorio(intervalo), get_valor_aleatorio(tempo_pausa), get_valor_aleatorio(quantidade_pausa))
        if df.empty:
            adicionar_log(cliente_id, "❌ Planilha está vazia.")
            return

        with store_lock:
            respostas_esperadas_por_cliente.setdefault(cliente_id, set())
            if cliente_id not in eventos_disparo:
                eventos_disparo[cliente_id] = threading.Event()
                eventos_disparo[cliente_id].set()

        for i in range(len(df)):
            row = df.iloc[i]

            with store_lock:
                if cliente_id not in eventos_disparo or not eventos_disparo[cliente_id].is_set():
                    break

            while get_pause_status(cliente_id)["paused"]:
                with store_lock:
                    if not eventos_disparo[cliente_id].is_set():
                        return
                time.sleep(1)

            nome = str(row.iloc[0])
            telefone = str(row.iloc[1])
            telefone_limpo = extrair_numeros(telefone)
            mensagem = mensagem_modelo.replace("{{nome}}", nome).replace("#nome", nome)

            with store_lock:
                respostas_esperadas_por_cliente[cliente_id].add(telefone_limpo)

            try:

                resultado = enviar_whatsapp(api_key, instance_key, telefone, mensagem)
                adicionar_log(cliente_id, resultado)
                db.session.add(DisparoLog(
                    agente_id=agente_id,
                    cliente_id=cliente_id,
                    telefone=telefone_limpo,
                    nome=nome,
                    mensagem=mensagem
                ))
                db.session.commit()
            except Exception as e:
                adicionar_log(cliente_id, f"❌ Erro ao enviar para {telefone}: {e}")

            aleatorio_intervalo=get_valor_aleatorio(intervalo)
            aleatorio_tempo_pausa=get_valor_aleatorio(tempo_pausa)
            aleatorio_quantidade_pausa=get_valor_aleatorio(quantidade_pausa)

            if i != len(df) - 1:
                for _ in range(aleatorio_intervalo):
                    with store_lock:
                        if not eventos_disparo[cliente_id].is_set():
                            return
                    time.sleep(1)

            if (i + 1) % aleatorio_quantidade_pausa == 0:
                adicionar_log(cliente_id, f"⏸ Pausa de {aleatorio_tempo_pausa}s após {aleatorio_quantidade_pausa} envios.")
                for _ in range(aleatorio_tempo_pausa):
                    with store_lock:
                        if not eventos_disparo[cliente_id].is_set():
                            return
                    time.sleep(1)

        adicionar_log(cliente_id, "✅ Disparo concluído!")

        with store_lock:
            pause_status[cliente_id]["running"] = False
            eventos_disparo.pop(cliente_id, None)

        agente = Agente.query.get(agente_id)
        if agente:
            agente.disparo_ativo = False
            db.session.commit()


def get_valor_aleatorio(valor_str):
    if ',' in valor_str:
        partes = valor_str.split(',')
        minimo = int(partes[0].strip())
        maximo = int(partes[1].strip())
        return random.randint(minimo, maximo)
        return int(valor_str.strip())


@disparo_bp.route("/cliente/status")
@login_required
def cliente_status():
    cliente_id = current_user.cliente_id
    status = get_pause_status(cliente_id)
    logs = log_store.get(cliente_id, [])
    return jsonify({
        "logs": logs,
        "paused": status["paused"],
        "running": status["running"],
        "numeroDisparos": sum(1 for log in logs if log.startswith("✅ Mensagem enviada"))
    })

@disparo_bp.route("/cliente/pause", methods=["POST"])
@login_required
def cliente_pause():

    cliente_id = current_user.cliente_id
    if pause_status[cliente_id]["running"]:
        status = get_pause_status(cliente_id)
        with store_lock:
            pause_status[cliente_id]["paused"] = not status["paused"]
        estado = "⏸ Pausado" if pause_status[cliente_id]["paused"] else "▶ Retomado"
        adicionar_log(cliente_id, estado)
        return jsonify({"status": estado})
    return jsonify({"status": "Já finalizado"})


@disparo_bp.route("/cliente/cancelar", methods=["POST"])
@login_required
def cliente_cancelar():
    cliente_id = current_user.cliente_id

    with store_lock:
        if cliente_id in eventos_disparo:
            eventos_disparo[cliente_id].clear()
        if cliente_id in pause_status:
            pause_status[cliente_id]["paused"] = False
            pause_status[cliente_id]["running"] = False
        if cliente_id in log_store:
            log_store[cliente_id] = []

    agente = Agente.query.filter_by(cliente_id=cliente_id).first()
    if agente:
        agente.disparo_ativo = False
        db.session.commit()

    adicionar_log(cliente_id, "🛑 Disparo cancelado pelo cliente.")
    return jsonify({"status": "cancelado", "message": "Disparo cancelado com sucesso."})

@disparo_bp.route("/cliente/limpar_logs", methods=["POST"])
@login_required
def cliente_limpar_logs():
    cliente_id = current_user.cliente_id
    with store_lock:
        if cliente_id in log_store:
            log_store[cliente_id] = []
    return jsonify({"status": "logs_limpos"})
