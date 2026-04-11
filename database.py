import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "palpites.db")


def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT UNIQUE NOT NULL,
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS palpites (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario TEXT NOT NULL,
        jogo_id TEXT NOT NULL,
        jogo TEXT NOT NULL,
        liga TEXT,
        palpite_casa INTEGER NOT NULL,
        palpite_fora INTEGER NOT NULL,
        gols_casa_real INTEGER,
        gols_fora_real INTEGER,
        pontos INTEGER,
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(usuario, jogo_id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS jogos_manuais (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        liga TEXT NOT NULL DEFAULT 'Brasileirão',
        data TEXT NOT NULL,
        casa TEXT NOT NULL,
        fora TEXT NOT NULL,
        gols_casa INTEGER,
        gols_fora INTEGER,
        status TEXT DEFAULT 'SCHEDULED'
    )
    """)

    # Migração: adicionar colunas novas à tabela antiga se necessário
    for col_sql in [
        "ALTER TABLE palpites ADD COLUMN liga TEXT",
        "ALTER TABLE palpites ADD COLUMN gols_casa_real INTEGER",
        "ALTER TABLE palpites ADD COLUMN gols_fora_real INTEGER",
        "ALTER TABLE palpites ADD COLUMN pontos INTEGER",
        "ALTER TABLE palpites ADD COLUMN criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "ALTER TABLE palpites ADD COLUMN moeda_apostada INTEGER DEFAULT 0",
        "ALTER TABLE palpites ADD COLUMN moedas_ganhas INTEGER",
    ]:
        try:
            cursor.execute(col_sql)
        except Exception:
            pass

    try:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN saldo_moedas INTEGER DEFAULT 10")
        cursor.execute("UPDATE usuarios SET saldo_moedas = 10 WHERE saldo_moedas IS NULL")
    except Exception:
        pass

    conn.commit()
    conn.close()
