import sqlite3

nomeUsuario = input("Digite o seu nome: ")
promptDoUsuario = input("Digite a sua consulta SQL: ")

print(f"Olá {nomeUsuario}. A sua consulta foi: {promptDoUsuario}!")

with sqlite3.connect("_bancoDeDados\estoque\estoque.db") as conn:
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(promptDoUsuario)
    resultado = [dict(linha) for linha in cur.fetchall()]

#print(produtos)

for item in resultado:
    print(item)