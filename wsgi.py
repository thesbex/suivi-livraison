# -*- coding: utf-8 -*-
"""Point d'entrée pour un serveur WSGI de production (gunicorn, PythonAnywhere…).

Le schéma et les données de démonstration sont créés au premier démarrage,
puis les migrations éventuelles sont appliquées à chaque redémarrage.
"""
import os

from app import app as application
from database import init_db

# Sur PostgreSQL, la démo n'est insérée que si la base est vide (init_db le vérifie).
init_db(seed_demo=os.environ.get("DONNEES_DEMO", "1") == "1")

app = application

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
