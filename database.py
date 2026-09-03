# -*- coding: utf-8 -*-
"""Schéma et données de démonstration de l'application Suivi Livraison.

Le schéma est commun à SQLite et PostgreSQL ; seule la déclaration de la clé
primaire auto-incrémentée diffère et est fournie par le module bd.
"""
import os
import secrets
import sys
from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

import bd
from bd import BASE_DIR, DB_PATH, POSTGRES, get_db

SCHEMA_MODELE = """
CREATE TABLE IF NOT EXISTS users (
    id {CLE},
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'convoyeur')),
    nom TEXT NOT NULL,
    telephone TEXT DEFAULT '',
    fonction TEXT DEFAULT 'Convoyeur',      -- rôle de l'intervenant qui livre
    actif INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS livraisons (
    id {CLE},
    code TEXT NOT NULL UNIQUE,               -- identifiant unique généré (RG: étape 2)
    reservation_num TEXT NOT NULL,
    client_nom TEXT NOT NULL,
    client_prenom TEXT NOT NULL,
    client_tel TEXT NOT NULL,
    client_email TEXT NOT NULL,
    pays_depart TEXT DEFAULT '',              -- pays de départ du client (facultatif)
    vehicule TEXT NOT NULL,
    immatriculation TEXT DEFAULT '',          -- facultatif
    date_livraison TEXT NOT NULL,            -- YYYY-MM-DD
    heure_livraison TEXT NOT NULL,           -- HH:MM
    lieu_livraison TEXT NOT NULL,
    date_retour TEXT NOT NULL,
    heure_retour TEXT NOT NULL,
    lieu_retour TEXT NOT NULL,
    convoyeur_id INTEGER REFERENCES users(id),   -- facultatif : livraison non affectée
    statut TEXT NOT NULL DEFAULT 'Créée',
    heure_reelle TEXT DEFAULT NULL,          -- HH:MM renseignée par le convoyeur
    commentaire_convoyeur TEXT DEFAULT '',
    token TEXT NOT NULL UNIQUE,              -- lien sécurisé (RG02)
    token_expire_le TEXT NOT NULL,           -- expiration après 30 jours (§11)
    cree_le TEXT NOT NULL,
    modifie_le TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS avis (
    id {CLE},
    livraison_id INTEGER NOT NULL UNIQUE REFERENCES livraisons(id),  -- une seule réponse (RG03)
    q1_a_lheure INTEGER NOT NULL,            -- 1 = oui, 0 = non
    q2_etat INTEGER NOT NULL,                -- notes 1..5
    q3_professionnalisme INTEGER NOT NULL,
    q4_proprete INTEGER NOT NULL,
    q5_conformite INTEGER NOT NULL,
    q6_recommandation INTEGER NOT NULL,
    commentaire TEXT DEFAULT '',
    score REAL NOT NULL,                     -- calculé automatiquement (RG07)
    cree_le TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS emails (
    id {CLE},
    livraison_id INTEGER NOT NULL,
    type TEXT NOT NULL,                      -- creation / rappel / livraison / remerciement
    destinataire TEXT NOT NULL,
    objet TEXT NOT NULL,
    corps_html TEXT NOT NULL,
    statut_envoi TEXT NOT NULL DEFAULT 'simulé',   -- simulé / envoyé / erreur
    message_erreur TEXT DEFAULT '',          -- motif de l'échec SMTP, pour diagnostic
    envoye_le TEXT NOT NULL                  -- tous les emails sont enregistrés (RG06)
);

CREATE TABLE IF NOT EXISTS historique (
    id {CLE},
    livraison_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    details TEXT DEFAULT '',
    utilisateur TEXT DEFAULT 'système',
    cree_le TEXT NOT NULL                    -- toutes les actions sont historisées (RG05, §11)
);
"""


SCHEMA = SCHEMA_MODELE.format(CLE=bd.CLE_PRIMAIRE)


def nouveau_code(db):
    annee = datetime.now().year
    n = db.execute("SELECT COUNT(*) AS n FROM livraisons").fetchone()["n"] + 1
    while True:
        code = f"LIV-{annee}-{n:04d}"
        if not db.execute("SELECT 1 FROM livraisons WHERE code = ?", (code,)).fetchone():
            return code
        n += 1


def nouveau_token():
    return secrets.token_urlsafe(24)


COLONNES_LIVRAISON = [
    "code", "reservation_num", "client_nom", "client_prenom", "client_tel",
    "client_email", "pays_depart", "vehicule", "immatriculation", "date_livraison",
    "heure_livraison", "lieu_livraison", "date_retour", "heure_retour", "lieu_retour",
    "convoyeur_id", "statut", "heure_reelle", "commentaire_convoyeur", "token",
    "token_expire_le", "cree_le", "modifie_le",
]


def _bloc_creation(nom_table):
    """Extrait du schéma l'instruction CREATE TABLE d'une table donnée."""
    for bloc in SCHEMA.split(");"):
        if f"CREATE TABLE IF NOT EXISTS {nom_table} (" in bloc:
            return bloc.strip() + "\n);"
    raise KeyError(nom_table)


def _reparer_references(db):
    """Répare les clés étrangères pointant vers « livraisons_ancienne ».

    Une version antérieure renommait la table « livraisons » pendant la
    migration. SQLite répercute un renommage sur les clés étrangères des
    autres tables : « avis » s'est donc mise à référencer une table
    supprimée juste après, ce qui faisait échouer tout dépôt d'avis.
    """
    cassees = [r["name"] for r in db.brut.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
        " AND sql LIKE '%livraisons_ancienne%'").fetchall()]
    if not cassees:
        return

    db.commit()
    ancien_mode = db.brut.isolation_level
    db.brut.isolation_level = None          # autocommit : les PRAGMA prennent effet
    db.brut.execute("PRAGMA foreign_keys = OFF")
    db.brut.execute("PRAGMA legacy_alter_table = ON")   # le renommage ne réécrit plus les références
    try:
        for nom in cassees:
            colonnes = ", ".join(c["name"] for c in db.brut.execute(
                f"PRAGMA table_info({nom})").fetchall())
            db.brut.execute(f"ALTER TABLE {nom} RENAME TO {nom}_a_reparer")
            db.brut.executescript(_bloc_creation(nom))
            db.brut.execute(f"INSERT INTO {nom} ({colonnes})"
                            f" SELECT {colonnes} FROM {nom}_a_reparer")
            db.brut.execute(f"DROP TABLE {nom}_a_reparer")
            print(f"Base réparée : la table « {nom} » référence de nouveau « livraisons ».")
    finally:
        db.brut.execute("PRAGMA legacy_alter_table = OFF")
        db.brut.execute("PRAGMA foreign_keys = ON")
        db.brut.isolation_level = ancien_mode


def migrer(db):
    """Met à jour une base créée par une version antérieure.

    Ajoute « pays_depart » et retire les contraintes NOT NULL devenues
    facultatives sur « immatriculation » et « convoyeur_id ». SQLite ne sachant
    pas modifier une contrainte, la table est reconstruite en préservant les
    données, les identifiants et les liens vers les avis et l'historique.
    """
    if not POSTGRES:
        _reparer_references(db)

    colonnes_users = db.colonnes("users")
    if colonnes_users and "fonction" not in colonnes_users:
        db.execute("ALTER TABLE users ADD COLUMN fonction TEXT DEFAULT 'Convoyeur'")
        db.execute("UPDATE users SET fonction = 'Convoyeur'"
                   " WHERE role = 'convoyeur' AND (fonction IS NULL OR fonction = '')")
        print("Base migrée : la fonction de l'intervenant est disponible.")

    colonnes_emails = db.colonnes("emails")
    if colonnes_emails and "message_erreur" not in colonnes_emails:
        db.execute("ALTER TABLE emails ADD COLUMN message_erreur TEXT DEFAULT ''")

    infos = db.colonnes("livraisons")   # {nom: obligatoire ?}
    if not infos:
        return
    if "pays_depart" not in infos:
        db.execute("ALTER TABLE livraisons ADD COLUMN pays_depart TEXT DEFAULT ''")
        infos = db.colonnes("livraisons")

    if not (infos["immatriculation"] or infos["convoyeur_id"]):
        return  # déjà au bon format

    if POSTGRES:
        # PostgreSQL sait retirer une contrainte sans reconstruire la table.
        db.execute("ALTER TABLE livraisons ALTER COLUMN immatriculation DROP NOT NULL")
        db.execute("ALTER TABLE livraisons ALTER COLUMN convoyeur_id DROP NOT NULL")
    else:
        # SQLite ne le sait pas : la table est reconstruite en préservant les
        # données, les identifiants et les liens vers les avis et l'historique.
        colonnes = ", ".join(COLONNES_LIVRAISON)
        db.commit()
        ancien_mode = db.brut.isolation_level
        db.brut.isolation_level = None      # autocommit : les PRAGMA prennent effet
        db.brut.execute("PRAGMA foreign_keys = OFF")
        # Sans ceci, le renommage réécrirait les clés étrangères des autres
        # tables et les ferait pointer vers une table sur le point d'être supprimée.
        db.brut.execute("PRAGMA legacy_alter_table = ON")
        try:
            db.brut.execute("ALTER TABLE livraisons RENAME TO livraisons_ancienne")
            db.brut.executescript(SCHEMA)
            db.brut.execute(f"INSERT INTO livraisons (id, {colonnes}) "
                            f"SELECT id, {colonnes} FROM livraisons_ancienne")
            db.brut.execute("DROP TABLE livraisons_ancienne")
        finally:
            db.brut.execute("PRAGMA legacy_alter_table = OFF")
            db.brut.execute("PRAGMA foreign_keys = ON")
            db.brut.isolation_level = ancien_mode
    print("Base migrée : immatriculation et convoyeur sont désormais facultatifs.")


def init_db(seed_demo=True):
    db = get_db()
    db.script(SCHEMA)
    migrer(db)
    if not db.execute("SELECT 1 FROM users WHERE role = 'admin'").fetchone():
        db.execute(
            "INSERT INTO users (username, password_hash, role, nom, telephone) VALUES (?, ?, 'admin', ?, ?)",
            ("admin", generate_password_hash("admin123"), "Administrateur", "+212 6 00 00 00 00"),
        )
    if seed_demo and not db.execute("SELECT 1 FROM livraisons").fetchone():
        _seed(db)
    db.commit()
    db.close()


# ---------------------------------------------------------------------------
# Données de démonstration
# ---------------------------------------------------------------------------

def _ts(jour_delta, heure="09:00"):
    d = datetime.now() + timedelta(days=jour_delta)
    return d.strftime("%Y-%m-%d") + " " + heure + ":00"


def _seed(db):
    import emails as mailer  # import local pour éviter un cycle au chargement

    convoyeurs = [
        ("karim", "Karim Benali", "+212 6 61 22 33 44", "Convoyeur"),
        ("yassine", "Yassine Mouline", "+212 6 62 55 66 77", "Responsable d'agence"),
        ("sofia", "Sofia Alami", "+212 6 63 88 99 00", "Gérant"),
    ]
    ids = {}
    for username, nom, tel, fonction in convoyeurs:
        ids[username] = db.inserer(
            "INSERT INTO users (username, password_hash, role, nom, telephone, fonction)"
            " VALUES (?, ?, 'convoyeur', ?, ?, ?)",
            (username, generate_password_hash("conv123"), nom, tel, fonction),
        )

    # (jours, heure, client, véhicule, immat, lieu livraison, retour+lieu, convoyeur,
    #  état final, heure réelle, commentaire convoyeur, avis)
    # Le convoyeur et l'immatriculation peuvent être absents (livraison non affectée).
    demo = [
        (-9, "10:00", ("El Fassi", "Amine", "+212 6 11 11 11 11", "amine.elfassi@example.com", "France"),
         "Dacia Duster", "48215-A-1", "Aéroport Marrakech Ménara (RAK)", (5, "10:00", "Aéroport Marrakech Ménara (RAK)"),
         "karim", "Terminée", "09:55", "",
         (1, 5, 5, 5, 5, 5, "Livraison parfaite, convoyeur très professionnel.")),
        (-7, "14:30", ("Bennis", "Leïla", "+212 6 22 22 22 22", "leila.bennis@example.com", "Maroc"),
         "Renault Clio 5", "30974-B-6", "Gare Casa-Voyageurs, Casablanca", (4, "14:30", "Gare Casa-Voyageurs, Casablanca"),
         "yassine", "Terminée", "14:55", "Circulation dense au centre-ville.",
         (0, 4, 3, 3, 4, 3, "Véhicule correct mais 25 minutes de retard.")),
        (-6, "09:00", ("Chraibi", "Omar", "+212 6 33 33 33 33", "omar.chraibi@example.com", "Espagne"),
         "Peugeot 208", "51230-A-40", "Hôtel Sofitel, Rabat", (3, "09:00", "Port de Tanger Ville"),
         "sofia", "Terminée", "08:58", "",
         (1, 5, 5, 4, 5, 4, "Très bon accueil, voiture impeccable.")),
        (-4, "16:00", ("Berrada", "Nadia", "+212 6 44 44 44 44", "nadia.berrada@example.com", "Maroc"),
         "Hyundai Tucson", "77410-D-6", "Aéroport Mohammed V, Casablanca (CMN)", (6, "16:00", "Aéroport Mohammed V, Casablanca (CMN)"),
         "karim", "Terminée", "16:05", "",
         (1, 4, 5, 5, 5, 5, "Je recommande, service rapide et sérieux.")),
        (-3, "11:30", ("Tazi", "Mehdi", "+212 6 55 55 55 55", "mehdi.tazi@example.com", "Belgique"),
         "Fiat 500", "12894-A-26", "Port d'Agadir", (2, "11:30", "Aéroport Agadir Al Massira (AGA)"),
         "yassine", "Terminée", "11:50", "Client prévenu du retard.",
         (0, 4, 4, 4, 4, 4, "")),
        (-1, "15:00", ("Lahlou", "Salma", "+212 6 66 66 66 66", "salma.lahlou@example.com", "Émirats arabes unis"),
         "Kia Sportage", "65321-B-1", "Hôtel Royal Mansour, Marrakech", (7, "15:00", "Aéroport Marrakech Ménara (RAK)"),
         "sofia", "Avis envoyé", "15:02", "", None),
        (0, "10:30", ("Idrissi", "Youssef", "+212 6 77 77 77 77", "youssef.idrissi@example.com", "Maroc"),
         "Volkswagen Golf 8", "90217-A-6", "Twin Center, Casablanca", (5, "10:30", "Twin Center, Casablanca"),
         "karim", "En cours", None, "", None),
        (0, "17:30", ("Amrani", "Kenza", "+212 6 88 88 88 88", "kenza.amrani@example.com", "Canada"),
         "Dacia Logan", "20458-B-40", "Gare Rabat-Ville", (3, "17:30", "Aéroport Rabat-Salé (RBA)"),
         "yassine", "En attente", None, "", None),
        (1, "09:00", ("Squalli", "Reda", "+212 6 99 99 99 99", "reda.squalli@example.com", "Royaume-Uni"),
         "Range Rover Evoque", "11780-E-1", "Villa des Orangers, Marrakech", (10, "09:00", "Port Tanger Med"),
         "sofia", "En attente", None, "", None),
        # Réservation enregistrée à l'avance : véhicule non encore attribué,
        # convoyeur pas encore désigné (nouveaux champs facultatifs).
        (3, "12:00", ("Filali", "Imane", "+212 6 10 20 30 40", "imane.filali@example.com", "Allemagne"),
         "Toyota Yaris", "", "Aéroport Rabat-Salé (RBA)", (6, "12:00", "Aéroport Rabat-Salé (RBA)"),
         None, "En attente", None, "", None),
    ]

    num_resa = 4810
    for (jd, heure, client, vehicule, immat, lieu, retour, conv, statut_final,
         heure_reelle, comm_conv, note) in demo:
        nom, prenom, tel, email, pays = client
        jr, hr, lr = retour
        date_liv = (datetime.now() + timedelta(days=jd)).strftime("%Y-%m-%d")
        date_ret = (datetime.now() + timedelta(days=jd + jr)).strftime("%Y-%m-%d")
        cree = _ts(jd - 2, "09:12")
        token = nouveau_token()
        expire = (datetime.strptime(date_liv, "%Y-%m-%d") + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
        code = nouveau_code(db)
        num_resa += 7
        liv_id = db.inserer(
            """INSERT INTO livraisons (code, reservation_num, client_nom, client_prenom, client_tel,
               client_email, pays_depart, vehicule, immatriculation, date_livraison, heure_livraison,
               lieu_livraison, date_retour, heure_retour, lieu_retour, convoyeur_id, statut,
               heure_reelle, commentaire_convoyeur, token, token_expire_le, cree_le, modifie_le)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (code, f"RES-{num_resa}", nom, prenom, tel, email, pays, vehicule, immat,
             date_liv, heure, lieu, date_ret, hr, lr, ids.get(conv), statut_final,
             heure_reelle, comm_conv, token, expire, cree, cree),
        )
        liv = dict(db.execute("SELECT * FROM livraisons WHERE id = ?", (liv_id,)).fetchone())
        fiche_conv = dict(convoyeurs_par_username(convoyeurs)).get(conv)
        conv_nom = fiche_conv[0] if fiche_conv else None
        liv["convoyeur_nom"] = conv_nom
        liv["convoyeur_tel"] = fiche_conv[1] if fiche_conv else None

        def hist(action, details="", user="système", quand=cree):
            db.execute(
                "INSERT INTO historique (livraison_id, action, details, utilisateur, cree_le) VALUES (?, ?, ?, ?, ?)",
                (liv_id, action, details, user, quand),
            )

        def mail(type_, quand):
            objet, corps = mailer.composer(type_, liv)
            db.execute(
                "INSERT INTO emails (livraison_id, type, destinataire, objet, corps_html, statut_envoi, envoye_le)"
                " VALUES (?, ?, ?, ?, ?, 'simulé', ?)",
                (liv_id, type_, email, objet, corps, quand),
            )

        hist("Livraison créée", f"Réservation RES-{num_resa} · {vehicule}", "Administrateur", cree)
        mail("creation", cree)
        hist("Email de création envoyé", f"À {email}", "système", cree)
        hist("Statut : En attente", "", "système", cree)

        avancement = ["En cours", "Livrée", "Avis envoyé", "Avis reçu", "Terminée"]
        if statut_final in avancement:
            hist("Livraison démarrée", "", conv_nom, _ts(jd, _decale(heure, -20)))
        if statut_final in avancement[1:] or statut_final in ("Terminée", "Avis envoyé"):
            hist("Livraison effectuée", f"Heure réelle : {heure_reelle}",
                 conv_nom, _ts(jd, heure_reelle or heure))
            mail("livraison", _ts(jd, heure_reelle or heure))
            hist("Email de confirmation + lien d'avis envoyé", f"À {email}", "système",
                 _ts(jd, heure_reelle or heure))
        if note is not None:
            q1, q2, q3, q4, q5, q6, comm = note
            score = round((q2 + q3 + q4 + q5 + q6) / 5, 1)
            quand_avis = _ts(jd + 1, "18:30")
            db.execute(
                """INSERT INTO avis (livraison_id, q1_a_lheure, q2_etat, q3_professionnalisme,
                   q4_proprete, q5_conformite, q6_recommandation, commentaire, score, cree_le)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (liv_id, q1, q2, q3, q4, q5, q6, comm, score, quand_avis),
            )
            hist("Avis client reçu", f"Note : {score}/5", "client", quand_avis)
            mail("remerciement", quand_avis)
            hist("Email de remerciement envoyé", f"À {email}", "système", quand_avis)


def _decale(heure, minutes):
    h = datetime.strptime(heure, "%H:%M") + timedelta(minutes=minutes)
    return h.strftime("%H:%M")


def convoyeurs_par_username(convoyeurs):
    return {u: (n, t) for u, n, t, *_ in convoyeurs}


if __name__ == "__main__":
    if "--reset" in sys.argv:
        if POSTGRES:
            d = get_db()
            d.script("DROP TABLE IF EXISTS avis, historique, emails, livraisons, users CASCADE;")
            d.commit(); d.close()
            print("Tables PostgreSQL supprimées.")
        elif os.path.exists(DB_PATH):
            os.remove(DB_PATH)
            print("Base supprimée.")
    init_db(seed_demo="--no-demo" not in sys.argv)
    print(f"Base initialisée : {DB_PATH}")
    print("Comptes : admin/admin123 · karim/conv123 · yassine/conv123 · sofia/conv123")
