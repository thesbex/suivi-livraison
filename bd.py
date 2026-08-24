# -*- coding: utf-8 -*-
"""Couche d'accès aux données : SQLite en local, PostgreSQL en production.

Le reste de l'application écrit du SQL standard avec des paramètres « ? » et
ne se préoccupe pas du moteur utilisé. Le choix se fait sur la variable
d'environnement DATABASE_URL :

    absente               -> SQLite, fichier suivi.db à côté de l'application
    postgres://... ou     -> PostgreSQL (Neon, Render, Supabase…)
    postgresql://...

Les rares différences entre les deux moteurs sont traitées ici :
  - marqueurs de paramètres   ?      vs  %s
  - identifiant auto-généré   AUTOINCREMENT  vs  SERIAL, et lastrowid vs RETURNING
  - réglages de connexion     PRAGMA (SQLite uniquement)
"""
import os
import re
import sqlite3
import sys

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
POSTGRES = DATABASE_URL.startswith(("postgres://", "postgresql://"))

if POSTGRES:
    import psycopg
    from psycopg.rows import dict_row

# En exécutable PyInstaller, la base vit à côté du .exe ; sinon à côté des sources.
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "suivi.db")

# Type de la clé primaire auto-incrémentée, injecté dans le schéma
CLE_PRIMAIRE = "SERIAL PRIMARY KEY" if POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"

# Les paramètres sont écrits « ? » partout ; PostgreSQL attend « %s ».
# Le remplacement ignore les « ? » qui se trouveraient dans une chaîne SQL.
_CHAINES = re.compile(r"'(?:[^']|'')*'")


def _adapter(sql):
    if not POSTGRES:
        return sql
    morceaux, position = [], 0
    for m in _CHAINES.finditer(sql):
        morceaux.append(sql[position:m.start()].replace("?", "%s"))
        morceaux.append(m.group(0))
        position = m.end()
    morceaux.append(sql[position:].replace("?", "%s"))
    return "".join(morceaux)


class Connexion:
    """Interface commune aux deux moteurs."""

    def __init__(self):
        if POSTGRES:
            url = DATABASE_URL.replace("postgres://", "postgresql://", 1)
            self.brut = psycopg.connect(url, row_factory=dict_row,
                                        connect_timeout=15, autocommit=False)
        else:
            self.brut = sqlite3.connect(DB_PATH, timeout=15)
            self.brut.row_factory = sqlite3.Row
            self.brut.execute("PRAGMA foreign_keys = ON")
            # WAL : les lecteurs ne sont jamais bloqués par un écrivain.
            self.brut.execute("PRAGMA journal_mode = WAL")
            self.brut.execute("PRAGMA busy_timeout = 15000")

    def execute(self, sql, params=()):
        if POSTGRES:
            cur = self.brut.cursor()
            cur.execute(_adapter(sql), tuple(params))
            return cur
        return self.brut.execute(sql, tuple(params))

    def inserer(self, sql, params=()):
        """INSERT renvoyant l'identifiant créé, quel que soit le moteur."""
        if POSTGRES:
            cur = self.execute(sql.rstrip().rstrip(";") + " RETURNING id", params)
            return cur.fetchone()["id"]
        return self.execute(sql, params).lastrowid

    def script(self, sql):
        """Exécute plusieurs instructions séparées par des points-virgules."""
        if POSTGRES:
            with self.brut.cursor() as cur:
                cur.execute(sql)
        else:
            self.brut.executescript(sql)

    def colonnes(self, table):
        """Colonnes existantes d'une table, pour les migrations."""
        if POSTGRES:
            cur = self.execute(
                "SELECT column_name AS nom, is_nullable AS nullable "
                "FROM information_schema.columns WHERE table_name = ?", (table,))
            return {r["nom"]: (r["nullable"] == "NO") for r in cur.fetchall()}
        return {r["name"]: bool(r["notnull"])
                for r in self.brut.execute(f"PRAGMA table_info({table})")}

    def commit(self):
        self.brut.commit()

    def rollback(self):
        self.brut.rollback()

    def close(self):
        self.brut.close()


def get_db():
    return Connexion()


def moteur():
    return "PostgreSQL" if POSTGRES else "SQLite"


def description_cible():
    """Libellé lisible de la base utilisée, pour les journaux de démarrage."""
    if POSTGRES:
        sans_mdp = re.sub(r"//([^:]+):[^@]+@", r"//\1:***@", DATABASE_URL)
        return f"PostgreSQL — {sans_mdp}"
    return f"SQLite — {DB_PATH}"
