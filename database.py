import psycopg2
import psycopg2.extras
import streamlit as st


class _CursorWrapper:
    """Wrapper sobre cursor psycopg2 para manter interface compatível com sqlite3."""

    def __init__(self, cursor):
        self._cur = cursor

    def fetchall(self):
        try:
            return self._cur.fetchall() or []
        except psycopg2.ProgrammingError:
            return []

    def fetchone(self):
        try:
            return self._cur.fetchone()
        except psycopg2.ProgrammingError:
            return None

    def __iter__(self):
        return iter(self.fetchall())

    def __getitem__(self, key):
        return self.fetchall()[key]

    @property
    def rowcount(self):
        return self._cur.rowcount


class ConnectionWrapper:
    """Wrapper sobre conexão psycopg2 com interface compatível com sqlite3.
    Converte automaticamente placeholders ? → %s."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=()):
        sql = sql.replace("?", "%s")
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params or ())
        return _CursorWrapper(cur)

    def cursor(self):
        return self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self._conn.rollback()
        self.close()


def get_connection() -> ConnectionWrapper:
    conn = psycopg2.connect(st.secrets["DATABASE_URL"])
    return ConnectionWrapper(conn)


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id          SERIAL PRIMARY KEY,
        nome        TEXT UNIQUE NOT NULL,
        saldo_ec    REAL DEFAULT 10.0,
        avatar_style TEXT DEFAULT '⚽',
        senha_hash  TEXT,
        criado_em   TIMESTAMPTZ DEFAULT NOW()
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS palpites (
        id              SERIAL PRIMARY KEY,
        usuario         TEXT NOT NULL,
        jogo_id         TEXT NOT NULL,
        jogo            TEXT NOT NULL,
        liga            TEXT,
        palpite_casa    INTEGER NOT NULL,
        palpite_fora    INTEGER NOT NULL,
        gols_casa_real  INTEGER,
        gols_fora_real  INTEGER,
        pontos          REAL,
        moeda_apostada  REAL DEFAULT 0,
        moedas_ganhas   REAL,
        odds_casa       REAL,
        odds_empate     REAL,
        odds_fora       REAL,
        odd_apostada    REAL,
        criado_em       TIMESTAMPTZ DEFAULT NOW(),
        UNIQUE(usuario, jogo_id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS jogos (
        id                   TEXT PRIMARY KEY,
        liga                 TEXT NOT NULL,
        data                 TIMESTAMPTZ,
        casa                 TEXT NOT NULL,
        fora                 TEXT NOT NULL,
        logo_casa            TEXT,
        logo_fora            TEXT,
        gols_casa            INTEGER,
        gols_fora            INTEGER,
        status               TEXT DEFAULT 'SCHEDULED',
        lembrete_enviado     BOOLEAN DEFAULT FALSE,
        resultado_notificado BOOLEAN DEFAULT FALSE,
        criado_em            TIMESTAMPTZ DEFAULT NOW()
    )
    """)

    # Migração para tabelas existentes
    for col_sql in [
        "ALTER TABLE jogos ADD COLUMN IF NOT EXISTS lembrete_enviado BOOLEAN DEFAULT FALSE",
        "ALTER TABLE jogos ADD COLUMN IF NOT EXISTS resultado_notificado BOOLEAN DEFAULT FALSE",
    ]:
        try:
            cur.execute(col_sql)
        except Exception:
            pass

    conn.commit()
    conn.close()
