from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class User(db.Model, UserMixin):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(128), unique=True, nullable=False)
    password = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'admin' ou 'cliente'
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=True)
    cliente = db.relationship('Cliente', backref='usuario', uselist=False)


class Cliente(db.Model):
    __tablename__ = "clientes"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(128), nullable=False)
    telefone = db.Column(db.String(20), nullable=False)

    # Relacionamento com agentes
    agentes = db.relationship("Agente", back_populates="cliente", lazy=True)

    def __repr__(self):
        return f"<Cliente {self.nome}>"


class Agente(db.Model):
    __tablename__ = "agentes"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(255), nullable=False)
    cliente_id = db.Column(db.Integer, db.ForeignKey("clientes.id"), nullable=False)
    instance_key = db.Column(db.String(255), nullable=False)
    api_key = db.Column(db.String(255), nullable=False)
    ativo = db.Column(db.Boolean, default=True)
    desativados_por_telefone = db.Column(db.Text, default="[]")
    numero_operador = db.Column(db.String(20), nullable=True)
    arquivo_instrucoes = db.Column(db.Text, nullable=False)
    arquivo_params = db.Column(db.Text, nullable=False)
    disparo_ativo = db.Column(db.Boolean, default=False)

    # Relacionamento com cliente
    cliente = db.relationship("Cliente", back_populates="agentes")

    # Relacionamentos corrigidos com conversas e logs
    conversas = db.relationship("Conversa", back_populates="agente", cascade="all, delete-orphan")
    disparo_logs = db.relationship("DisparoLog", back_populates="agente", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Agente {self.nome}>"


class Conversa(db.Model):
    __tablename__ = "conversas"

    id = db.Column(db.Integer, primary_key=True)
    agente_id = db.Column(db.Integer, db.ForeignKey("agentes.id", ondelete="CASCADE"), nullable=False)
    telefone = db.Column(db.String(20), nullable=False)
    mensagens = db.Column(db.Text, default="[]")  # Armazena lista de mensagens como JSON

    # Relacionamento com agente
    agente = db.relationship("Agente", back_populates="conversas")


class DisparoLog(db.Model):
    __tablename__ = "disparo_logs"

    id = db.Column(db.Integer, primary_key=True)
    agente_id = db.Column(db.Integer, db.ForeignKey("agentes.id", ondelete="CASCADE"), nullable=False)
    cliente_id = db.Column(db.Integer, nullable=False)
    telefone = db.Column(db.String(20), nullable=False)
    nome = db.Column(db.String(100))
    mensagem = db.Column(db.Text)
    enviado_em = db.Column(db.DateTime, default=datetime.utcnow)

    # Relacionamento com agente
    agente = db.relationship("Agente", back_populates="disparo_logs")
