# -*- coding: utf-8 -*-
"""Suivi Livraison — digitalisation de la livraison des véhicules.

Application web Flask : préparation des livraisons, suivi des convoyeurs,
confirmation, emails automatiques, avis clients et statistiques.
"""
import logging
import os
import secrets
import sys
from datetime import datetime, timedelta
from functools import wraps

from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

import emails as mailer
from bd import BASE_DIR, DB_PATH, POSTGRES, description_cible, get_db
from database import init_db, nouveau_code, nouveau_token
from donnees import LIEUX, PAYS, TOUS_LES_LIEUX

# Clé de signature des sessions.
# En production, elle vient de la variable d'environnement SECRET_KEY : le
# disque d'un hébergeur est souvent éphémère, un fichier local déconnecterait
# tout le monde à chaque redémarrage. En local, elle est générée une fois.
SECRET_KEY = os.environ.get("SECRET_KEY", "").strip()
if not SECRET_KEY:
    _KEY_FILE = os.path.join(BASE_DIR, ".secret_key")
    if not os.path.exists(_KEY_FILE):
        with open(_KEY_FILE, "w") as f:
            f.write(secrets.token_hex(32))
    with open(_KEY_FILE) as f:
        SECRET_KEY = f.read().strip()

if getattr(sys, "frozen", False):
    # Exécutable PyInstaller : gabarits et fichiers statiques embarqués
    _RESSOURCES = sys._MEIPASS
    app = Flask(__name__,
                template_folder=os.path.join(_RESSOURCES, "templates"),
                static_folder=os.path.join(_RESSOURCES, "static"))
else:
    app = Flask(__name__)
app.config["SECRET_KEY"] = SECRET_KEY

# États d'une livraison (§8 de la spécification)
STATUTS = ["Créée", "Email envoyé", "En attente", "En cours", "Livrée",
           "Avis envoyé", "Avis reçu", "Terminée"]

MOIS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
           "août", "septembre", "octobre", "novembre", "décembre"]
JOURS_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


# ---------------------------------------------------------------------------
# Base de données & helpers
# ---------------------------------------------------------------------------

def db():
    if "db" not in g:
        g.db = get_db()
    return g.db


@app.teardown_appcontext
def close_db(exc):
    d = g.pop("db", None)
    if d is not None:
        d.close()


def maintenant():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def historiser(livraison_id, action, details="", utilisateur=None):
    """RG05 / §11 : toutes les actions et dates sont historisées."""
    if utilisateur is None:
        utilisateur = session.get("nom", "système")
    db().execute(
        "INSERT INTO historique (livraison_id, action, details, utilisateur, cree_le)"
        " VALUES (?, ?, ?, ?, ?)",
        (livraison_id, action, details, utilisateur, maintenant()),
    )


def changer_statut(liv_id, statut, utilisateur="système"):
    db().execute("UPDATE livraisons SET statut = ?, modifie_le = ? WHERE id = ?",
                 (statut, maintenant(), liv_id))
    historiser(liv_id, f"Statut : {statut}", "", utilisateur)


def charger_livraison(liv_id=None, token=None):
    """Livraison + convoyeur + avis, sous forme de dict (ou None)."""
    q = """SELECT l.*, u.nom AS convoyeur_nom, u.telephone AS convoyeur_tel,
                  a.score AS avis_score, a.commentaire AS avis_commentaire, a.id AS avis_id
           FROM livraisons l
           LEFT JOIN users u ON u.id = l.convoyeur_id
           LEFT JOIN avis a ON a.livraison_id = l.id """
    if token is not None:
        row = db().execute(q + "WHERE l.token = ?", (token,)).fetchone()
    else:
        row = db().execute(q + "WHERE l.id = ?", (liv_id,)).fetchone()
    return dict(row) if row else None


def minutes(hhmm):
    try:
        h, m = hhmm.split(":")
        return int(h) * 60 + int(m)
    except (AttributeError, ValueError):
        return None


def retard_minutes(liv):
    """Écart en minutes entre l'heure réelle et l'heure prévue (None si non livrée)."""
    prevu, reel = minutes(liv["heure_livraison"]), minutes(liv["heure_reelle"])
    if prevu is None or reel is None:
        return None
    return reel - prevu


SEUIL_RETARD = 15  # minutes de tolérance avant de compter un retard


# ---------------------------------------------------------------------------
# Filtres et variables de gabarits
# ---------------------------------------------------------------------------

@app.template_filter("date_fr")
def date_fr(iso, avec_jour=False):
    try:
        d = datetime.strptime(iso[:10], "%Y-%m-%d")
    except (ValueError, TypeError):
        return iso or "—"
    if avec_jour:
        return f"{JOURS_FR[d.weekday()]} {d.day} {MOIS_FR[d.month - 1]} {d.year}"
    mois = MOIS_FR[d.month - 1]
    abrege = mois[:4] + "." if len(mois) > 4 else mois
    return f"{d.day:02d} {abrege} {d.year}"


@app.template_filter("date_longue")
def date_longue_f(iso):
    return date_fr(iso, avec_jour=True)


@app.template_filter("dt_fr")
def dt_fr(ts):
    try:
        d = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
        return f"{d.day:02d}/{d.month:02d}/{d.year} à {d.hour:02d}:{d.minute:02d}"
    except (ValueError, TypeError):
        return ts or ""


@app.template_filter("statut_cls")
def statut_cls(statut):
    return {
        "Créée": "st-neutre", "Email envoyé": "st-neutre", "En attente": "st-attente",
        "En cours": "st-cours", "Livrée": "st-livree", "Avis envoyé": "st-avis",
        "Avis reçu": "st-avis", "Terminée": "st-fini",
    }.get(statut, "st-neutre")


@app.context_processor
def inject_globals():
    return {
        "STATUTS": STATUTS,
        "csrf": session.get("csrf", ""),
        "aujourdhui": datetime.now().strftime("%Y-%m-%d"),
        "retard_minutes": retard_minutes,
        "SEUIL_RETARD": SEUIL_RETARD,
        "LIEUX": LIEUX,
        "TOUS_LES_LIEUX": TOUS_LES_LIEUX,
        "PAYS": PAYS,
    }


# ---------------------------------------------------------------------------
# Authentification & sécurité
# ---------------------------------------------------------------------------

@app.before_request
def avant_requete():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    if request.method == "POST":
        if request.form.get("_csrf") != session.get("csrf"):
            abort(400, "Jeton de sécurité invalide — rechargez la page.")


def role_requis(*roles):
    def deco(f):
        @wraps(f)
        def wrapper(*a, **kw):
            if "user_id" not in session:
                return redirect(url_for("login", suivant=request.path))
            if session.get("role") not in roles:
                abort(403)
            return f(*a, **kw)
        return wrapper
    return deco


@app.route("/connexion", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = db().execute("SELECT * FROM users WHERE username = ? AND actif = 1",
                         (request.form.get("username", "").strip().lower(),)).fetchone()
        if u and check_password_hash(u["password_hash"], request.form.get("password", "")):
            session["user_id"], session["role"], session["nom"] = u["id"], u["role"], u["nom"]
            session["csrf"] = secrets.token_hex(16)
            suivant = request.args.get("suivant")
            if suivant and suivant.startswith("/"):
                return redirect(suivant)
            return redirect(url_for("dashboard" if u["role"] == "admin" else "mes_livraisons"))
        flash("Identifiants incorrects.", "erreur")
    return render_template("login.html")


@app.route("/deconnexion", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/compte/mot-de-passe", methods=["GET", "POST"])
@role_requis("admin", "convoyeur")
def mot_de_passe():
    if request.method == "POST":
        u = db().execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
        if not check_password_hash(u["password_hash"], request.form.get("actuel", "")):
            flash("Mot de passe actuel incorrect.", "erreur")
        elif len(request.form.get("nouveau", "")) < 6:
            flash("Le nouveau mot de passe doit contenir au moins 6 caractères.", "erreur")
        elif request.form.get("nouveau") != request.form.get("confirmation"):
            flash("La confirmation ne correspond pas.", "erreur")
        else:
            db().execute("UPDATE users SET password_hash = ? WHERE id = ?",
                         (generate_password_hash(request.form["nouveau"]), u["id"]))
            db().commit()
            flash("Mot de passe modifié.", "succes")
            return redirect(url_for("dashboard" if session["role"] == "admin" else "mes_livraisons"))
    return render_template("mot_de_passe.html")


@app.route("/")
def accueil():
    if session.get("role") == "admin":
        return redirect(url_for("dashboard"))
    if session.get("role") == "convoyeur":
        return redirect(url_for("mes_livraisons"))
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Administration — tableau de bord & livraisons
# ---------------------------------------------------------------------------

def _requete_livraisons(filtres):
    sql = """SELECT l.*, u.nom AS convoyeur_nom, a.score AS avis_score,
                    a.commentaire AS avis_commentaire
             FROM livraisons l
             LEFT JOIN users u ON u.id = l.convoyeur_id
             LEFT JOIN avis a ON a.livraison_id = l.id WHERE 1=1 """
    params = []
    if filtres.get("statut"):
        sql += "AND l.statut = ? "
        params.append(filtres["statut"])
    if filtres.get("convoyeur") == "aucun":
        sql += "AND l.convoyeur_id IS NULL "
    elif filtres.get("convoyeur"):
        sql += "AND l.convoyeur_id = ? "
        params.append(filtres["convoyeur"])
    if filtres.get("q"):
        sql += ("AND (l.client_nom LIKE ? OR l.client_prenom LIKE ? OR l.code LIKE ? "
                "OR l.reservation_num LIKE ? OR l.vehicule LIKE ? "
                "OR COALESCE(l.immatriculation, '') LIKE ? OR COALESCE(l.pays_depart, '') LIKE ? "
                "OR l.lieu_livraison LIKE ?) ")
        params += [f"%{filtres['q']}%"] * 8
    sql += "ORDER BY l.date_livraison DESC, l.heure_livraison DESC"
    return [dict(r) for r in db().execute(sql, params).fetchall()]


@app.route("/admin")
@role_requis("admin")
def dashboard():
    filtres = {"statut": request.args.get("statut", ""),
               "convoyeur": request.args.get("convoyeur", ""),
               "q": request.args.get("q", "").strip()}
    livraisons = _requete_livraisons(filtres)
    convoyeurs = db().execute(
        "SELECT id, nom FROM users WHERE role = 'convoyeur' ORDER BY nom").fetchall()
    auj = datetime.now().strftime("%Y-%m-%d")
    compteurs = {
        "jour": sum(1 for l in livraisons if l["date_livraison"] == auj),
        "attente": sum(1 for l in livraisons if l["statut"] in ("En attente", "En cours")),
        "avis": sum(1 for l in livraisons if l["avis_score"] is not None),
        "non_affectees": sum(1 for l in livraisons if not l["convoyeur_id"]),
    }
    return render_template("dashboard.html", livraisons=livraisons,
                           convoyeurs=convoyeurs, filtres=filtres, compteurs=compteurs)


CHAMPS_LIVRAISON = ["reservation_num", "client_nom", "client_prenom", "client_tel",
                    "client_email", "pays_depart", "vehicule", "immatriculation",
                    "date_livraison", "heure_livraison", "lieu_livraison", "date_retour",
                    "heure_retour", "lieu_retour", "convoyeur_id"]

# Champs facultatifs : leur absence ne bloque pas la validation du formulaire.
CHAMPS_FACULTATIFS = {"immatriculation", "convoyeur_id", "pays_depart"}


def _lire_formulaire():
    donnees = {c: request.form.get(c, "").strip() for c in CHAMPS_LIVRAISON}
    # Le convoyeur non renseigné est enregistré à NULL (livraison non affectée)
    donnees["convoyeur_id"] = donnees["convoyeur_id"] or None
    erreurs = [c for c in CHAMPS_LIVRAISON
               if c not in CHAMPS_FACULTATIFS and not donnees[c]]
    return donnees, erreurs


@app.route("/admin/livraisons/nouvelle", methods=["GET", "POST"])
@role_requis("admin")
def nouvelle_livraison():
    convoyeurs = db().execute(
        "SELECT id, nom, telephone FROM users WHERE role = 'convoyeur' AND actif = 1 ORDER BY nom").fetchall()
    donnees = {}
    if request.method == "POST":
        donnees, erreurs = _lire_formulaire()
        if erreurs:
            flash("Merci de renseigner les champs obligatoires "
                  "(l'immatriculation, le convoyeur et le pays de départ sont facultatifs).",
                  "erreur")
        else:
            # Étape 2 — l'application génère identifiant unique, lien sécurisé, statut
            code = nouveau_code(db())
            token = nouveau_token()
            expire = (datetime.strptime(donnees["date_livraison"], "%Y-%m-%d")
                      + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")  # §11 : 30 jours
            # Colonnes dérivées de CHAMPS_LIVRAISON : ajouter un champ au formulaire
            # suffit, la requête suit automatiquement.
            colonnes = (["code"] + CHAMPS_LIVRAISON
                        + ["statut", "token", "token_expire_le", "cree_le", "modifie_le"])
            valeurs = ([code] + [donnees[c] for c in CHAMPS_LIVRAISON]
                       + ["Créée", token, expire, maintenant(), maintenant()])
            liv_id = db().inserer(
                f"INSERT INTO livraisons ({', '.join(colonnes)}) "
                f"VALUES ({', '.join('?' * len(valeurs))})", valeurs)
            historiser(liv_id, "Livraison créée",
                       f"{donnees['reservation_num']} · {donnees['vehicule']}")
            # La livraison est validée AVANT l'envoi : l'appel SMTP dure
            # plusieurs secondes et ne doit pas garder la base verrouillée.
            db().commit()
            # RG01 — email automatique à la création, puis passage « En attente »
            liv = charger_livraison(liv_id)
            _, statut_envoi = mailer.envoyer(db(), "creation", liv)
            historiser(liv_id, "Email de création envoyé",
                       f"À {liv['client_email']} ({statut_envoi})", "système")
            db().execute("UPDATE livraisons SET statut = 'Email envoyé' WHERE id = ?", (liv_id,))
            changer_statut(liv_id, "En attente")
            db().commit()
            flash(f"Livraison {code} créée — email envoyé au client.", "succes")
            return redirect(url_for("detail_livraison", liv_id=liv_id))
    return render_template("livraison_form.html", livraison=donnees,
                           convoyeurs=convoyeurs, mode="creation")


@app.route("/admin/livraisons/<int:liv_id>")
@role_requis("admin")
def detail_livraison(liv_id):
    liv = charger_livraison(liv_id)
    if not liv:
        abort(404)
    avis = db().execute("SELECT * FROM avis WHERE livraison_id = ?", (liv_id,)).fetchone()
    hist = db().execute(
        "SELECT * FROM historique WHERE livraison_id = ? ORDER BY cree_le, id", (liv_id,)).fetchall()
    mails = db().execute(
        "SELECT * FROM emails WHERE livraison_id = ? ORDER BY envoye_le, id", (liv_id,)).fetchall()
    etape = STATUTS.index(liv["statut"]) if liv["statut"] in STATUTS else 0
    return render_template("livraison_detail.html", liv=liv, avis=avis,
                           historique=hist, mails=mails, etape=etape)


@app.route("/admin/livraisons/<int:liv_id>/modifier", methods=["GET", "POST"])
@role_requis("admin")
def modifier_livraison(liv_id):
    liv = charger_livraison(liv_id)
    if not liv:
        abort(404)
    convoyeurs = db().execute(
        "SELECT id, nom, telephone FROM users WHERE role = 'convoyeur' AND actif = 1 ORDER BY nom").fetchall()
    if request.method == "POST":
        donnees, erreurs = _lire_formulaire()
        if erreurs:
            flash("Merci de renseigner les champs obligatoires "
                  "(l'immatriculation, le convoyeur et le pays de départ sont facultatifs).",
                  "erreur")
            donnees["id"] = liv_id
            return render_template("livraison_form.html", livraison=donnees,
                                   convoyeurs=convoyeurs, mode="edition")
        sets = ", ".join(f"{c} = ?" for c in CHAMPS_LIVRAISON)
        db().execute(f"UPDATE livraisons SET {sets}, modifie_le = ? WHERE id = ?",
                     tuple([donnees[c] for c in CHAMPS_LIVRAISON] + [maintenant(), liv_id]))
        historiser(liv_id, "Livraison modifiée")
        db().commit()
        flash("Livraison mise à jour.", "succes")
        return redirect(url_for("detail_livraison", liv_id=liv_id))
    return render_template("livraison_form.html", livraison=liv,
                           convoyeurs=convoyeurs, mode="edition")


@app.route("/admin/livraisons/<int:liv_id>/supprimer", methods=["POST"])
@role_requis("admin")
def supprimer_livraison(liv_id):
    liv = charger_livraison(liv_id)
    if not liv:
        abort(404)
    historiser(liv_id, "Livraison supprimée",
               f"{liv['code']} · {liv['reservation_num']} · {liv['client_prenom']} "
               f"{liv['client_nom']} · {liv['vehicule']}")
    db().execute("DELETE FROM avis WHERE livraison_id = ?", (liv_id,))
    db().execute("DELETE FROM livraisons WHERE id = ?", (liv_id,))
    db().commit()
    flash(f"Livraison {liv['code']} supprimée.", "succes")
    return redirect(url_for("dashboard"))


@app.route("/admin/livraisons/<int:liv_id>/rappel", methods=["POST"])
@role_requis("admin")
def envoyer_rappel(liv_id):
    liv = charger_livraison(liv_id)
    if not liv:
        abort(404)
    if liv["statut"] not in ("En attente", "En cours"):
        flash("Le rappel n'est possible qu'avant la livraison.", "erreur")
    else:
        _, statut_envoi = mailer.envoyer(db(), "rappel", liv)
        historiser(liv_id, "Email de rappel envoyé", f"À {liv['client_email']} ({statut_envoi})")
        db().commit()
        flash("Email de rappel envoyé au client.", "succes")
    return redirect(url_for("detail_livraison", liv_id=liv_id))


@app.route("/admin/emails", methods=["GET", "POST"])
@role_requis("admin")
def config_email():
    """Modèles d'emails, état de la configuration SMTP et envoi d'un email de test."""
    resultat = None
    if request.method == "POST":
        destinataire = request.form.get("destinataire", "").strip()
        if "@" not in destinataire or "." not in destinataire.split("@")[-1]:
            flash("Adresse email invalide.", "erreur")
        elif not mailer.smtp_configure():
            flash("Aucun serveur SMTP configuré : l'envoi resterait simulé. "
                  "Renseignez SMTP_HOST, SMTP_PORT et SMTP_FROM avant de tester.", "erreur")
        else:
            objet, corps = mailer.composer_test()
            statut, erreur = mailer.expedier(destinataire, objet, corps)
            resultat = {"statut": statut, "erreur": erreur, "destinataire": destinataire}
            if statut == "envoyé":
                flash(f"Email de test envoyé à {destinataire}. "
                      "Vérifiez la boîte de réception (et les indésirables).", "succes")
            else:
                flash("L'envoi a échoué — le motif est indiqué ci-dessous.", "erreur")

    derniers = db().execute(
        """SELECT e.*, l.code FROM emails e
           LEFT JOIN livraisons l ON l.id = e.livraison_id
           ORDER BY e.envoye_le DESC, e.id DESC LIMIT 12""").fetchall()
    stats_envoi = dict(db().execute(
        "SELECT SUM(CASE WHEN statut_envoi = 'envoyé'  THEN 1 ELSE 0 END) AS envoyes,"
        "       SUM(CASE WHEN statut_envoi = 'simulé'  THEN 1 ELSE 0 END) AS simules,"
        "       SUM(CASE WHEN statut_envoi = 'erreur'  THEN 1 ELSE 0 END) AS erreurs"
        "  FROM emails").fetchone())
    return render_template("config_email.html", cfg=mailer.config_smtp(),
                           modeles=mailer.MODELES, resultat=resultat,
                           derniers=derniers, stats_envoi=stats_envoi)


@app.route("/admin/emails/modele/<type_email>")
@role_requis("admin")
def apercu_modele(type_email):
    """Rendu d'un modèle d'email avec une livraison fictive."""
    if type_email not in [m[0] for m in mailer.MODELES]:
        abort(404)
    _, corps = mailer.composer(type_email, mailer.EXEMPLE_LIVRAISON)
    return corps


@app.route("/admin/emails/<int:email_id>")
@role_requis("admin")
def voir_email(email_id):
    mail = db().execute("SELECT * FROM emails WHERE id = ?", (email_id,)).fetchone()
    if not mail:
        abort(404)
    return render_template("email_view.html", mail=mail)


@app.route("/admin/emails/<int:email_id>/corps")
@role_requis("admin")
def corps_email(email_id):
    mail = db().execute("SELECT corps_html FROM emails WHERE id = ?", (email_id,)).fetchone()
    if not mail:
        abort(404)
    return mail["corps_html"]


# ---------------------------------------------------------------------------
# Administration — avis, statistiques, convoyeurs
# ---------------------------------------------------------------------------

@app.route("/admin/avis")
@role_requis("admin")
def liste_avis():
    rows = db().execute(
        """SELECT a.*, l.code, l.client_prenom, l.client_nom, l.vehicule,
                  l.date_livraison, l.id AS liv_id, u.nom AS convoyeur_nom
           FROM avis a JOIN livraisons l ON l.id = a.livraison_id
           LEFT JOIN users u ON u.id = l.convoyeur_id
           ORDER BY a.cree_le DESC""").fetchall()
    moyenne = db().execute("SELECT AVG(score) AS moyenne FROM avis").fetchone()["moyenne"]
    return render_template("avis_list.html", avis=rows, moyenne=moyenne)


@app.route("/admin/stats")
@role_requis("admin")
def stats():
    d = db()
    livraisons = [dict(r) for r in d.execute(
        "SELECT * FROM livraisons").fetchall()]
    livrees = [l for l in livraisons if l["heure_reelle"]]
    ecarts = [retard_minutes(l) for l in livrees]
    ecarts = [e for e in ecarts if e is not None]
    retards = [e for e in ecarts if e > SEUIL_RETARD]

    avis_rows = [dict(r) for r in d.execute("SELECT * FROM avis").fetchall()]
    scores = [a["score"] for a in avis_rows]
    satisfaits = sum(1 for s in scores if s >= 4)

    # Distribution des notes (arrondies) 1..5
    distribution = {n: 0 for n in range(1, 6)}
    for s in scores:
        distribution[max(1, min(5, round(s)))] += 1
    max_distrib = max(distribution.values()) if scores else 1

    # Classement des convoyeurs
    convoyeurs = []
    for u in d.execute("SELECT * FROM users WHERE role = 'convoyeur'").fetchall():
        livs = [l for l in livraisons if l["convoyeur_id"] == u["id"]]
        faites = [l for l in livs if l["heure_reelle"]]
        notes = [a["score"] for a in avis_rows
                 if any(l["id"] == a["livraison_id"] for l in livs)]
        ec = [retard_minutes(l) for l in faites]
        ec = [e for e in ec if e is not None]
        ponctuelles = sum(1 for e in ec if e <= SEUIL_RETARD)
        convoyeurs.append({
            "nom": u["nom"],
            "nb": len(faites),
            "note": round(sum(notes) / len(notes), 2) if notes else None,
            "ponctualite": round(100 * ponctuelles / len(ec)) if ec else None,
        })
    convoyeurs.sort(key=lambda c: (c["note"] is not None, c["note"] or 0, c["nb"]), reverse=True)

    tuiles = {
        "nb_livraisons": len(livraisons),
        "nb_livrees": len(livrees),
        "nb_retards": len(retards),
        "ecart_moyen": round(sum(ecarts) / len(ecarts)) if ecarts else None,
        "note_moyenne": round(sum(scores) / len(scores), 2) if scores else None,
        "nb_avis": len(scores),
        "nb_satisfaits": satisfaits,
        "taux_reponse": round(100 * len(scores) / len(livrees)) if livrees else None,
        "non_affectees": sum(1 for l in livraisons if not l["convoyeur_id"]),
    }
    return render_template("stats.html", t=tuiles, convoyeurs=convoyeurs,
                           distribution=distribution, max_distrib=max_distrib)


@app.route("/admin/convoyeurs", methods=["GET", "POST"])
@role_requis("admin")
def gestion_convoyeurs():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "creer":
            username = request.form.get("username", "").strip().lower()
            nom = request.form.get("nom", "").strip()
            mdp = request.form.get("password", "")
            if not username or not nom or len(mdp) < 6:
                flash("Identifiant, nom et mot de passe (6 caractères min.) requis.", "erreur")
            elif db().execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
                flash("Cet identifiant existe déjà.", "erreur")
            else:
                db().execute(
                    "INSERT INTO users (username, password_hash, role, nom, telephone)"
                    " VALUES (?, ?, 'convoyeur', ?, ?)",
                    (username, generate_password_hash(mdp), nom,
                     request.form.get("telephone", "").strip()))
                db().commit()
                flash(f"Convoyeur {nom} créé.", "succes")
        elif action == "basculer":
            uid = request.form.get("uid")
            u = db().execute("SELECT * FROM users WHERE id = ? AND role = 'convoyeur'", (uid,)).fetchone()
            if u:
                db().execute("UPDATE users SET actif = ? WHERE id = ?", (0 if u["actif"] else 1, uid))
                db().commit()
                flash(f"Compte {u['nom']} {'désactivé' if u['actif'] else 'réactivé'}.", "succes")
        return redirect(url_for("gestion_convoyeurs"))

    rows = db().execute(
        """SELECT u.*, COUNT(l.id) AS nb_livraisons,
                  (SELECT AVG(a.score) FROM avis a
                   JOIN livraisons l2 ON l2.id = a.livraison_id
                   WHERE l2.convoyeur_id = u.id) AS note
           FROM users u LEFT JOIN livraisons l ON l.convoyeur_id = u.id
           WHERE u.role = 'convoyeur' GROUP BY u.id ORDER BY u.nom""").fetchall()
    return render_template("convoyeurs.html", convoyeurs=rows)


# ---------------------------------------------------------------------------
# Espace convoyeur
# ---------------------------------------------------------------------------

@app.route("/convoyeur")
@role_requis("convoyeur")
def mes_livraisons():
    rows = [dict(r) for r in db().execute(
        """SELECT l.*, a.score AS avis_score FROM livraisons l
           LEFT JOIN avis a ON a.livraison_id = l.id
           WHERE l.convoyeur_id = ?
           ORDER BY l.date_livraison, l.heure_livraison""", (session["user_id"],)).fetchall()]
    auj = datetime.now().strftime("%Y-%m-%d")
    a_faire = [l for l in rows if l["statut"] in ("En attente", "En cours")]
    jour = [l for l in a_faire if l["date_livraison"] <= auj]
    a_venir = [l for l in a_faire if l["date_livraison"] > auj]
    faites = sorted([l for l in rows if l["statut"] not in ("En attente", "En cours")],
                    key=lambda l: (l["date_livraison"], l["heure_livraison"]), reverse=True)
    return render_template("mes_livraisons.html", jour=jour, a_venir=a_venir, faites=faites)


def _livraison_du_convoyeur(liv_id):
    liv = charger_livraison(liv_id)
    if not liv or liv["convoyeur_id"] != session["user_id"]:
        abort(404)
    return liv


@app.route("/convoyeur/livraisons/<int:liv_id>/demarrer", methods=["POST"])
@role_requis("convoyeur")
def demarrer_livraison(liv_id):
    liv = _livraison_du_convoyeur(liv_id)
    if liv["statut"] != "En attente":
        flash("Cette livraison ne peut pas être démarrée.", "erreur")
    else:
        changer_statut(liv_id, "En cours", session["nom"])
        db().commit()
        flash(f"Livraison {liv['code']} démarrée — bonne route !", "succes")
    return redirect(url_for("mes_livraisons"))


@app.route("/convoyeur/livraisons/<int:liv_id>/confirmer", methods=["POST"])
@role_requis("convoyeur")
def confirmer_livraison(liv_id):
    liv = _livraison_du_convoyeur(liv_id)
    # RG04 — la livraison ne peut être validée qu'une seule fois
    if liv["statut"] not in ("En attente", "En cours"):
        flash("Cette livraison a déjà été confirmée.", "erreur")
        return redirect(url_for("mes_livraisons"))
    heure = request.form.get("heure_reelle", "").strip()
    if minutes(heure) is None:
        flash("Heure réelle invalide (format HH:MM).", "erreur")
        return redirect(url_for("mes_livraisons"))
    commentaire = request.form.get("commentaire", "").strip()
    db().execute(
        "UPDATE livraisons SET heure_reelle = ?, commentaire_convoyeur = ?, modifie_le = ? WHERE id = ?",
        (heure, commentaire, maintenant(), liv_id))
    changer_statut(liv_id, "Livrée", session["nom"])
    historiser(liv_id, "Livraison effectuée",
               f"Heure réelle : {heure}" + (f" · {commentaire}" if commentaire else ""))
    # La livraison est actée en base avant l'envoi de l'email : si le serveur
    # SMTP est lent ou injoignable, la confirmation du convoyeur reste acquise
    # et la base n'est pas verrouillée pendant l'appel réseau.
    db().commit()
    # Étape 5 — email de confirmation automatique avec bouton « Donner mon avis »
    liv = charger_livraison(liv_id)
    _, statut_envoi = mailer.envoyer(db(), "livraison", liv)
    historiser(liv_id, "Email de confirmation + lien d'avis envoyé",
               f"À {liv['client_email']} ({statut_envoi})", "système")
    changer_statut(liv_id, "Avis envoyé")
    db().commit()
    flash(f"Livraison {liv['code']} confirmée — le client a reçu le lien d'avis.", "succes")
    return redirect(url_for("mes_livraisons"))


# ---------------------------------------------------------------------------
# Espace client (liens sécurisés — RG02, §11)
# ---------------------------------------------------------------------------

def _livraison_par_token(token):
    liv = charger_livraison(token=token)
    if not liv:
        abort(404)
    return liv


def _lien_expire(liv):
    return maintenant() > liv["token_expire_le"]


@app.route("/suivi/<token>")
def suivi_client(token):
    liv = _livraison_par_token(token)
    if _lien_expire(liv):
        return render_template("client_expire.html"), 410
    etape = STATUTS.index(liv["statut"]) if liv["statut"] in STATUTS else 0
    return render_template("client_suivi.html", liv=liv, etape=etape)


@app.route("/avis/<token>", methods=["GET", "POST"])
def avis_client(token):
    liv = _livraison_par_token(token)
    if _lien_expire(liv):
        return render_template("client_expire.html"), 410
    deja = db().execute("SELECT * FROM avis WHERE livraison_id = ?", (liv["id"],)).fetchone()
    if deja:  # RG03 — une seule réponse possible
        return render_template("client_merci.html", liv=liv, deja=True)
    if liv["statut"] not in ("Livrée", "Avis envoyé"):
        return render_template("client_suivi.html", liv=liv,
                               etape=STATUTS.index(liv["statut"]),
                               message="Le formulaire d'avis sera disponible après la livraison.")

    if request.method == "POST":
        try:
            q1 = {"oui": 1, "non": 0}[request.form.get("q1", "")]
            notes = {c: int(request.form.get(c, "")) for c in
                     ("q2", "q3", "q4", "q5", "q6")}
            assert all(1 <= n <= 5 for n in notes.values())
        except (KeyError, ValueError, AssertionError):
            flash("Merci de répondre à toutes les questions.", "erreur")
            return render_template("client_avis.html", liv=liv, reponses=request.form)
        # RG07 — score calculé automatiquement (moyenne des 5 notes étoilées)
        score = round(sum(notes.values()) / 5, 1)
        db().execute(
            """INSERT INTO avis (livraison_id, q1_a_lheure, q2_etat, q3_professionnalisme,
               q4_proprete, q5_conformite, q6_recommandation, commentaire, score, cree_le)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (liv["id"], q1, notes["q2"], notes["q3"], notes["q4"], notes["q5"],
             notes["q6"], request.form.get("q7", "").strip(), score, maintenant()))
        historiser(liv["id"], "Avis client reçu", f"Note : {score}/5", "client")
        changer_statut(liv["id"], "Avis reçu")
        # L'avis du client est enregistré avant l'email de remerciement :
        # un échec d'envoi ne doit jamais faire perdre sa réponse.
        db().commit()
        _, statut_envoi = mailer.envoyer(db(), "remerciement", liv)
        historiser(liv["id"], "Email de remerciement envoyé",
                   f"À {liv['client_email']} ({statut_envoi})", "système")
        changer_statut(liv["id"], "Terminée")
        db().commit()
        return render_template("client_merci.html", liv=liv, deja=False)

    return render_template("client_avis.html", liv=liv, reponses={})


# ---------------------------------------------------------------------------

# Journal des erreurs : sans lui, une exception disparaît avec la fenêtre
# de la console. Le fichier erreurs.log se crée à côté de l'application.
_journal = logging.FileHandler(os.path.join(BASE_DIR, "erreurs.log"), encoding="utf-8")
_journal.setLevel(logging.WARNING)
_journal.setFormatter(logging.Formatter(
    "%(asctime)s  %(levelname)s\n%(message)s\n" + "-" * 70))
app.logger.addHandler(_journal)
app.logger.setLevel(logging.INFO)


@app.errorhandler(500)
def page_500(e):
    return render_template("erreur.html", code=500,
                           message="Une erreur est survenue. Le détail a été "
                                   "enregistré dans le fichier erreurs.log."), 500


@app.errorhandler(404)
def page_404(e):
    return render_template("erreur.html", code=404,
                           message="Page introuvable ou lien invalide."), 404


@app.errorhandler(403)
def page_403(e):
    return render_template("erreur.html", code=403,
                           message="Accès non autorisé."), 403


if __name__ == "__main__":
    # Toujours appelé : crée la base si elle est absente, et applique les
    # migrations si elle a été créée par une version antérieure.
    base_absente = POSTGRES or not os.path.exists(DB_PATH)
    init_db(seed_demo=base_absente)
    print("Base :", description_cible())
    if base_absente and not POSTGRES:
        print("Base de démonstration créée — comptes : admin/admin123, karim/conv123")
    if getattr(sys, "frozen", False):
        print("Suivi Livraison — http://127.0.0.1:5000")
        print("Fermez cette fenêtre pour arrêter l'application.")
        if not os.environ.get("SUIVI_NO_BROWSER"):
            import threading
            import webbrowser
            threading.Timer(1.2, lambda: webbrowser.open("http://127.0.0.1:5000")).start()
    app.run(host="127.0.0.1", port=5000,
            debug=os.environ.get("FLASK_DEBUG", "") == "1")
