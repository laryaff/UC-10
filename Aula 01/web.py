from flask import Flask

from flask import Flask, jsonify

app = Flask(__name__)

@app.route("/api/ping", methods=["GET"])

def ping():
    return jsonify({"status": "online","mensagem": "API operacional"}), 200 

if __name__ == "__main__":
    app.run(debug=True, port=5000)