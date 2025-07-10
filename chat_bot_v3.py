import json
import re
import time
import threading
import requests
import os
from flask import Blueprint, request, jsonify, current_app
from models import db, Agente, Conversa
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

# ✅ Respostas esperadas personalizadas (opcional)
try:
    from app_disparo_cliente import respostas_esperadas_por_cliente
except ImportError:
    respostas_esperadas_por_cliente = {}

chat_bot_v3_bp = Blueprint("chat_bot_v3", __name__, url_prefix='/chat_bot_v3')

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

ultima_resposta_lock = threading.Lock()
ultima_resposta_por_telefone = {}

def consultar_servicos_google():
    url = "https://script.google.com/macros/s/AKfycbw4wHoEbM2-ZYgAlOYSlowwdIPcavMyxbMOxX-hxlTCT3-SHLQbFlNtWABKOETcGyUh/exec"
    try:
        print("🔄 Consultando serviços no Google Sheets...")
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            servicos = response.json()
            print(f"✅ Consulta concluída. {len(servicos)} itens retornados.")
            return [s for s in servicos if s.get("ativo", "").lower() == "sim"]
        else:
            print(f"⚠️ Erro na resposta do Google Sheets: {response.status_code}")
    except Exception as e:
        print(f"❌ Erro ao consultar planilha do Google Sheets: {e}")
    return []

def buscar_produto_em_planilha(nome_produto):
    servicos = consultar_servicos_google()
    return [s for s in servicos if nome_produto.lower() in s.get("nome_do_serviço", "").lower()]

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def enviar_whatsapp(api_key: str, instance_key: str, phone: str, message: str):
    clean_phone = re.sub(r"[^\d]", "", phone.split("@")[0])
    payload = {"number": clean_phone, "text": message}
    headers = {"apikey": api_key, "Content-Type": "application/json"}
    url = f"https://evolution.modware.com.br/message/sendText/{instance_key}"
    try:
        response = requests.post(url, json=payload, timeout=12, headers=headers)
        response.raise_for_status()
        print(f"✅ [WHATSAPP] [{instance_key}] Mensagem enviada para {clean_phone}")
        return True
    except requests.exceptions.RequestException as e:
        print(f"❌ [WHATSAPP ERROR]: Falha ao enviar para {clean_phone}: {e}")
        return False

def salvar_mensagem(agente_id, telefone, role, conteudo):
    conversa = Conversa.query.filter_by(agente_id=agente_id, telefone=telefone).first()
    if not conversa:
        conversa = Conversa(agente_id=agente_id, telefone=telefone, mensagens="[]")
    mensagens = json.loads(conversa.mensagens)
    mensagens.append({"role": role, "content": conteudo})
    conversa.mensagens = json.dumps(mensagens[-10:])
    db.session.add(conversa)
    db.session.commit()

@chat_bot_v3_bp.route("/webhook", methods=["POST"])
def webhook_evolutionapi():
    try:
        payload = request.get_json(force=True, silent=True) or {}
        print("📡 Requisição recebida no webhook:", json.dumps(payload, indent=2, ensure_ascii=False))
        app = current_app._get_current_object()
        threading.Thread(target=processar_evento, args=(app, payload), daemon=True).start()
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        print(f"❌ Erro no webhook: {e}")
        return jsonify({"error": str(e)}), 500

def processar_evento(app, payload):
    with app.app_context():
        try:
            if payload.get("event", "").lower() != "messages.upsert":
                return

            message = payload.get("data", {})
            instance_key = payload.get("instance")
            telefone = message.get("key", {}).get("remoteJid", "")
            telefone_limpo = re.sub(r"[^\d]", "", telefone.split("@")[0])

            if message.get("key", {}).get("fromMe", False):
                print(f"⚠ Ignorado: mensagem enviada pelo próprio agente ({telefone_limpo})")
                return

            texto = ""
            if "conversation" in message.get("message", {}):
                texto = message["message"]["conversation"]
            elif "extendedTextMessage" in message.get("message", {}):
                texto = message["message"]["extendedTextMessage"].get("text", "")

            if not telefone or not texto or not instance_key:
                print(f"⚠ Dados incompletos. Telefone: {telefone}, Texto: {texto}, Instance: {instance_key}")
                return

            agente = Agente.query.filter_by(instance_key=instance_key).first()
            if not agente:
                print(f"❌ Nenhum agente vinculado à instância: {instance_key}")
                return

            if not agente.ativo:
                print(f"🚫 Agente {agente.nome} está desativado globalmente.")
                return

            try:
                bloqueios = json.loads(agente.desativados_por_telefone or "[]")
                if not isinstance(bloqueios, list):
                    raise ValueError("Campo desativados_por_telefone inválido.")
            except Exception as e:
                print(f"⚠ Erro ao carregar bloqueios: {e}")
                bloqueios = []

            if telefone_limpo in bloqueios:
                print(f"🚫 Número bloqueado: {telefone_limpo}")
                return

            agora = time.time()
            with ultima_resposta_lock:
                if telefone_limpo not in ultima_resposta_por_telefone:
                    operador_telefone = agente.numero_operador
                    mensagem_alerta = f"📲 Nova conversa iniciada!\nNúmero: {telefone_limpo}\nMensagem: {texto}"
                    print(f"🔔 Notificando operador {operador_telefone}: {mensagem_alerta}")
                    enviar_whatsapp(
                        api_key=agente.api_key,
                        instance_key=agente.instance_key,
                        phone=operador_telefone,
                        message=mensagem_alerta
                    )
                else:
                    tempo_desde_ultima = agora - ultima_resposta_por_telefone[telefone_limpo]
                    if tempo_desde_ultima < 10:
                        print(f"⏳ Ignorado (resposta enviada há {tempo_desde_ultima:.1f}s): {telefone_limpo}")
                        return

            print(f"📩 [{instance_key}] {telefone_limpo} enviou: {texto}")
            salvar_mensagem(agente.id, telefone_limpo, "user", texto)

            encontrados = buscar_produto_em_planilha(texto)
            if encontrados:
                resposta = "Encontrei os seguintes serviços relacionados:\n\n" + "\n".join(
                    f"- {s.get('nome_do_serviço')} (Categoria: {s.get('categoria')})" for s in encontrados
                )
                print(f"📚 Resposta baseada em planilha: {resposta}")
                salvar_mensagem(agente.id, telefone_limpo, "assistant", resposta)
                enviar_whatsapp(agente.api_key, agente.instance_key, telefone_limpo, resposta)
                ultima_resposta_por_telefone[telefone_limpo] = agora
                return

            historico = Conversa.query.filter_by(agente_id=agente.id, telefone=telefone_limpo).first()
            mensagens_contexto = json.loads(historico.mensagens) if historico else []
            mensagens_openai = [{"role": "system", "content": agente.arquivo_instrucoes + agente.arquivo_params}] + mensagens_contexto

            print("🤖 Enviando mensagem para OpenAI...")
            comp = client.chat.completions.create(
                model="gpt-4-turbo",
                temperature=0.2,
                max_tokens=350,
                timeout=20,
                messages=mensagens_openai
            )
            reply = comp.choices[0].message.content
            print(f"🧠 Resposta da IA: {reply}")
            salvar_mensagem(agente.id, telefone_limpo, "assistant", reply)
            enviar_whatsapp(agente.api_key, agente.instance_key, telefone_limpo, reply)
            ultima_resposta_por_telefone[telefone_limpo] = agora

        except Exception as e:
            print(f"❌ Erro interno no processamento do evento: {e}")
