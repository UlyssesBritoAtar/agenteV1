from flask import Flask, render_template
from models import db, Agente  # Certifique-se de importar os modelos corretamente

app = Flask(__name__)


@app.route('/')
def index():
    # Supondo que o cliente logado tenha um `cliente_id` no banco
    # Aqui estamos buscando o agente relacionado ao cliente logado
    cliente_id = 1  # Isso pode vir de algum sistema de autenticação, como o Flask-Login
    agente = Agente.query.filter_by(cliente_id=cliente_id, ativo=True).first()

    if not agente:
        return "Agente não encontrado", 404

    evolution_token = '8279e194810ee3e15b93083744fb2805'
    instance_id = agente.instance_key  # Pega a instance_key do banco
    apiKey = agente.api_key  # Pega a api_key do banco

    return render_template('index.html', instance_id=instance_id, evolution_token=evolution_token, apiKey=apiKey)


if __name__ == '__main__':
    app.run(debug=True)
