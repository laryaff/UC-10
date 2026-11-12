"""
Atividade 005 - Estacionamento Sempre Rápido: Text-to-SQL na web (Flask).

Rodar a partir da raiz da UC10:
    pip install flask requests
    python aula-05/app_estacionamento_sql.py

Abrir no navegador:
    http://localhost:5003/                       painel do supervisor (static/index.html)

Testar no Postman:
    GET  http://localhost:5003/api/status
    GET  http://localhost:5003/api/patio
    POST http://localhost:5003/api/consulta-nl   {"pergunta": "Quantos carros estão no pátio agora?"}
"""

import os
import sqlite3

import requests
from flask import Flask, jsonify, request

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "..", "_bancoDeDados", "estacionamento", "estacionamento.db")
OLLAMA_API_URL = "http://localhost:11434/api/generate"
MODELO_LLM = "gemma4:12b"

# Tudo o que o modelo sabe sobre o banco. Colunas sensíveis ficam de fora.
SCHEMA = """
Tabelas do banco SQLite do estacionamento:

Vagas(id, localizacao, tipo)
  -- localizacao: 'Setor A-01', 'Setor B-02'...; tipo: 'Pequena', 'Média' ou 'Grande'
Veiculos(id, cliente_id, placa, modelo, cor)
RegistrosEstacionamento(id, veiculo_id, vaga_id, operador_id,
                        data_hora_entrada, data_hora_saida, valor_total)
Usuarios(id, nome, perfil)
  -- perfil: 0=Cliente, 1=Operador, 2=Gerente, 3=System

Relações:
- RegistrosEstacionamento.veiculo_id -> Veiculos.id
- RegistrosEstacionamento.vaga_id -> Vagas.id
- RegistrosEstacionamento.operador_id -> Usuarios.id
- Veiculos.cliente_id -> Usuarios.id

Regras de negócio:
- data_hora_saida IS NULL significa que o veículo está no pátio e a vaga está ocupada.
- Faturamento é a soma de valor_total.
"""

app = Flask(__name__)


# ---------------------------------------------------------------------------
# Banco de dados
# ---------------------------------------------------------------------------
def consultar_banco(sql):
    """Executa o SQL em modo somente leitura e devolve uma lista de dicionários."""
    with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(sql)
        return [dict(linha) for linha in cursor.fetchall()]


# ---------------------------------------------------------------------------
# IA (Ollama)
# ---------------------------------------------------------------------------
def limpar_sql(texto):
    """Tira markdown, 'SQL:' e ';' do fim, e fica só com o primeiro comando."""
    texto = texto.replace("```sql", "").replace("```", "").strip()
    if texto.upper().startswith("SQL:"):
        texto = texto[4:].strip()
    return texto.split(";")[0].strip()


def gerar_sql(pergunta):
    """Pede ao modelo um SELECT para a pergunta, usando o SCHEMA como contexto."""
    prompt = f"""Você é um assistente de banco de dados SQLite.
Gere APENAS uma consulta SELECT em uma única linha, sem markdown e sem explicação.
Use somente as tabelas e colunas do esquema abaixo.
Dê nomes claros às colunas calculadas usando AS (ex.: COUNT(*) AS total).

{SCHEMA}

Pergunta: {pergunta}
SQL:"""

    resp = requests.post(OLLAMA_API_URL, json={
        "model": MODELO_LLM,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0},
    }, timeout=120)
    resp.raise_for_status()
    return limpar_sql(resp.json().get("response", ""))


# ---------------------------------------------------------------------------
# Rotas da API
# ---------------------------------------------------------------------------
@app.route("/")
def painel():
    """Entrega a página do front end (aula-05/static/index.html)."""
    return app.send_static_file("index.html")


@app.route("/api/status", methods=["GET"])
def status():
    try:
        ollama_ok = requests.get("http://localhost:11434/api/version", timeout=2).ok
    except requests.RequestException:
        ollama_ok = False
    return jsonify({
        "status": "ok",
        "app": "Estacionamento Text-to-SQL",
        "modelo": MODELO_LLM,
        "banco_encontrado": os.path.exists(DB_PATH),
        "ollama_respondendo": ollama_ok,
    }), 200


@app.route("/api/patio", methods=["GET"])
def patio():
    """Mapa do pátio: consulta fixa (sem IA), uma linha por vaga."""
    sql = """
        SELECT g.id, g.localizacao, g.tipo, v.placa, v.modelo, v.cor, r.data_hora_entrada
        FROM Vagas g
        LEFT JOIN RegistrosEstacionamento r ON r.vaga_id = g.id AND r.data_hora_saida IS NULL
        LEFT JOIN Veiculos v ON v.id = r.veiculo_id
        ORDER BY g.localizacao
    """
    try:
        vagas = consultar_banco(sql)
    except sqlite3.Error as e:
        return jsonify({"erro": "Não foi possível ler o pátio.", "detalhes": str(e)}), 500
    ocupadas = sum(1 for v in vagas if v["placa"])
    return jsonify({"vagas": vagas, "total": len(vagas),
                    "ocupadas": ocupadas, "livres": len(vagas) - ocupadas}), 200


@app.route("/api/consulta-nl", methods=["POST"])
def consulta_nl():
    dados = request.get_json(silent=True) or {}
    pergunta = str(dados.get("pergunta", "")).strip()
    if not pergunta:
        return jsonify({"erro": "Envie o campo 'pergunta' com texto."}), 400

    try:
        sql = gerar_sql(pergunta)
    except requests.exceptions.ConnectionError:
        return jsonify({"erro": "O Ollama não está respondendo. Rode 'ollama serve' no WSL."}), 503
    except requests.exceptions.Timeout:
        return jsonify({"erro": "O modelo demorou demais para responder."}), 504
    except requests.exceptions.RequestException as e:
        return jsonify({"erro": f"Erro ao falar com o Ollama: {e}"}), 502

    if not sql.upper().startswith("SELECT"):
        return jsonify({"erro": "Só consultas SELECT são permitidas.", "sql_gerado": sql}), 422

    try:
        linhas = consultar_banco(sql)
    except sqlite3.Error as e:
        return jsonify({"erro": "O SQL gerado não pôde ser executado.",
                        "sql_gerado": sql, "detalhes": str(e)}), 422

    return jsonify({
        "pergunta": pergunta,
        "sql_executado": sql,
        "total_registros": len(linhas),
        "dados": linhas,
    }), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5003, debug=True)
