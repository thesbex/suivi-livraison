# -*- coding: utf-8 -*-
"""Composition, enregistrement (RG06) et envoi des emails de l'application.

Sans configuration SMTP, les emails sont « simulés » : ils sont composés,
enregistrés en base et consultables dans l'interface d'administration.
Pour un envoi réel, définir les variables d'environnement :
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM
"""
import json
import os
import smtplib
import urllib.error
import urllib.request
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:5000").rstrip("/")

ENCRE = "#131A26"
ACCENT = "#E85D1F"
PAPIER = "#F5F2EB"

MOIS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
           "août", "septembre", "octobre", "novembre", "décembre"]


def date_longue(iso):
    try:
        d = datetime.strptime(iso, "%Y-%m-%d")
        return f"{d.day} {MOIS_FR[d.month - 1]} {d.year}"
    except (ValueError, TypeError):
        return iso or ""


def _logo_disponible():
    """Nom du fichier logo s'il a été déposé dans static/, sinon None."""
    dossier = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
    for ext in ("png", "webp", "jpg", "jpeg", "svg"):
        if os.path.exists(os.path.join(dossier, f"logo.{ext}")):
            return f"logo.{ext}"
    return None


def _entete_marque():
    """En-tête des emails : le logo de l'agence s'il existe, sinon le nom.

    L'image est référencée en URL absolue (BASE_URL) : un client mail ne sait
    pas résoudre un chemin relatif. Le texte reste en repli si les images
    sont bloquées, ce que font beaucoup de messageries par défaut.
    """
    logo = _logo_disponible()
    marque = os.environ.get("MARQUE", "BABA Car")
    if logo and not logo.endswith(".svg"):   # les clients mail ignorent le SVG
        # Le logo est centré et occupe toute la largeur du cadre d'en-tête.
        # « width » en attribut : Outlook ignore les largeurs en CSS seul.
        return (f'<img src="{BASE_URL}/static/{logo}" alt="{marque}" width="300" '
                f'style="display:block;margin:0 auto;width:100%;max-width:300px;'
                f'height:auto;border:0;outline:none;text-decoration:none;">')
    return (f'<span style="font-family:Arial,Helvetica,sans-serif;font-size:20px;'
            f'font-weight:bold;letter-spacing:3px;color:{ENCRE};">{marque.upper()}</span>'
            f'<span style="font-family:Arial,Helvetica,sans-serif;font-size:11px;'
            f'letter-spacing:1px;color:#6b7280;display:block;padding-top:4px;">'
            f'AGENCE DE LOCATION DE VÉHICULES</span>')


def _gabarit(titre, contenu, bouton=None):
    """Gabarit HTML commun, compatible clients mail (tables + styles en ligne)."""
    bloc_bouton = ""
    if bouton:
        libelle, url = bouton
        bloc_bouton = f"""
        <tr><td align="center" style="padding:28px 40px 8px 40px;">
          <a href="{url}" style="display:inline-block;background:{ACCENT};color:#ffffff;
             text-decoration:none;font-weight:bold;font-size:16px;padding:14px 36px;
             border-radius:6px;font-family:Arial,Helvetica,sans-serif;">{libelle}</a>
        </td></tr>"""
    return f"""<!DOCTYPE html>
<html lang="fr"><body style="margin:0;padding:0;background:{PAPIER};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{PAPIER};padding:32px 12px;">
<tr><td align="center">
<table role="presentation" width="560" cellpadding="0" cellspacing="0"
       style="background:#ffffff;border-radius:10px;overflow:hidden;max-width:560px;width:100%;">
  <tr><td style="height:6px;background:repeating-linear-gradient(45deg,{ACCENT},{ACCENT} 14px,{ENCRE} 14px,{ENCRE} 28px);font-size:0;line-height:0;">&nbsp;</td></tr>
  <tr><td align="center" style="background:#ffffff;padding:26px 30px 22px 30px;
                                border-bottom:1px solid #eee9df;text-align:center;">
    {_entete_marque()}
  </td></tr>
  <tr><td style="padding:36px 40px 8px 40px;font-family:Georgia,'Times New Roman',serif;
                 font-size:22px;color:{ENCRE};font-weight:bold;">{titre}</td></tr>
  <tr><td style="padding:8px 40px 0 40px;font-family:Arial,Helvetica,sans-serif;
                 font-size:15px;line-height:1.65;color:#3d4757;">{contenu}</td></tr>
  {bloc_bouton}
  <tr><td style="padding:30px 40px 34px 40px;font-family:Arial,Helvetica,sans-serif;
                 font-size:12px;color:#8a92a0;border-top:1px solid #eee9df;">
    Cet email vous a été envoyé automatiquement par votre agence de location.<br>
    Merci de ne pas y répondre directement.
  </td></tr>
</table>
</td></tr></table>
</body></html>"""


def _tableau_infos(lignes):
    tr = "".join(
        f"""<tr>
        <td style="padding:9px 14px;background:{PAPIER};font-family:Arial,sans-serif;font-size:13px;
            color:#6b7280;white-space:nowrap;border-bottom:2px solid #ffffff;">{k}</td>
        <td style="padding:9px 14px;background:{PAPIER};font-family:Arial,sans-serif;font-size:14px;
            color:{ENCRE};font-weight:bold;border-bottom:2px solid #ffffff;">{v}</td></tr>"""
        for k, v in lignes if v
    )
    return f"""<table role="presentation" width="100%" cellpadding="0" cellspacing="0"
               style="margin:18px 0 6px 0;border-radius:8px;overflow:hidden;">{tr}</table>"""


LIBELLE_INTERLOCUTEUR = "Votre interlocuteur pour la livraison"

_MENTION_CONVOYEUR = (
    "<p style='color:#6b7280;font-size:13.5px;'>Les coordonnées de votre "
    "interlocuteur vous seront communiquées avant la livraison.</p>"
)


def _interlocuteur(liv):
    """Nom de la personne qui livre, suivi de sa fonction quand elle est connue.

    Le libellé côté client est « Votre interlocuteur pour la livraison » : la
    livraison n'est pas toujours faite par un convoyeur, ce peut être le gérant,
    un responsable d'agence ou un collaborateur.
    """
    nom = liv.get("convoyeur_nom")
    if not nom:
        return None
    fonction = (liv.get("convoyeur_fonction") or "").strip()
    return f"{nom} — {fonction}" if fonction else nom


def _vehicule(liv):
    """« Marque Modèle · Immatriculation » — l'immatriculation étant facultative."""
    immat = (liv.get("immatriculation") or "").strip()
    return f"{liv['vehicule']} · {immat}" if immat else liv["vehicule"]


def composer(type_email, liv):
    """Retourne (objet, corps_html) pour un type d'email et une livraison donnés."""
    client = f"{liv['client_prenom']} {liv['client_nom']}"
    lien_suivi = f"{BASE_URL}/suivi/{liv['token']}"
    lien_avis = f"{BASE_URL}/avis/{liv['token']}"

    if type_email == "creation":
        objet = "Votre véhicule sera livré prochainement"
        contenu = (
            f"<p>Bonjour {client},</p>"
            f"<p>Votre véhicule sera livré selon les informations suivantes :</p>"
            + _tableau_infos([
                ("Date", date_longue(liv["date_livraison"])),
                ("Heure", liv["heure_livraison"]),
                ("Lieu", liv["lieu_livraison"]),
                ("Véhicule", _vehicule(liv)),
                (LIBELLE_INTERLOCUTEUR, _interlocuteur(liv)),
                ("Téléphone", liv.get("convoyeur_tel")),
            ])
            + (_MENTION_CONVOYEUR if not liv.get("convoyeur_nom") else "")
            + "<p>Nous vous remercions pour votre confiance.</p>"
        )
        return objet, _gabarit("Livraison de votre véhicule", contenu,
                               ("Suivre ma livraison", lien_suivi))

    if type_email == "rappel":
        objet = f"Rappel — livraison de votre véhicule le {date_longue(liv['date_livraison'])}"
        contenu = (
            f"<p>Bonjour {client},</p>"
            f"<p>Petit rappel : la livraison de votre véhicule est prévue prochainement.</p>"
            + _tableau_infos([
                ("Date", date_longue(liv["date_livraison"])),
                ("Heure", liv["heure_livraison"]),
                ("Lieu", liv["lieu_livraison"]),
                (LIBELLE_INTERLOCUTEUR, _interlocuteur(liv)),
                ("Téléphone", liv.get("convoyeur_tel")),
            ])
            + (_MENTION_CONVOYEUR if not liv.get("convoyeur_nom") else "")
            + "<p>Nous vous remercions pour votre confiance.</p>"
        )
        return objet, _gabarit("Rappel de livraison", contenu,
                               ("Suivre ma livraison", lien_suivi))

    if type_email == "livraison":
        objet = "Votre véhicule a été livré"
        contenu = (
            f"<p>Bonjour {client},</p>"
            f"<p>Votre véhicule vient de vous être livré. Voici le récapitulatif :</p>"
            + _tableau_infos([
                ("Véhicule", _vehicule(liv)),
                ("Lieu", liv["lieu_livraison"]),
                ("Date", date_longue(liv["date_livraison"])),
                ("Heure", liv.get("heure_reelle") or liv["heure_livraison"]),
                (LIBELLE_INTERLOCUTEUR, _interlocuteur(liv)),
            ])
            + "<p>Votre avis compte : il ne vous faudra qu'une minute pour évaluer votre livraison.</p>"
        )
        return objet, _gabarit("Véhicule livré ✔", contenu, ("Donner mon avis", lien_avis))

    if type_email == "remerciement":
        objet = "Merci pour votre retour"
        contenu = (
            f"<p>Bonjour {client},</p>"
            "<p>Nous avons bien reçu votre avis concernant la livraison de votre véhicule.</p>"
            "<p>Merci pour votre retour : il nous aide à améliorer la qualité de notre service "
            "et de nos convoyeurs.</p>"
            "<p>À très bientôt,<br>Votre agence de location.</p>"
        )
        return objet, _gabarit("Merci pour votre retour", contenu)

    raise ValueError(f"Type d'email inconnu : {type_email}")


# Les quatre modèles envoyés au client (§9 de la spécification)
MODELES = [
    ("creation", "À la création de la livraison",
     "Envoyé automatiquement dès qu'une livraison est enregistrée (RG01)."),
    ("rappel", "Rappel avant livraison",
     "Envoyé manuellement depuis la fiche livraison, avant l'heure prévue."),
    ("livraison", "Confirmation de livraison",
     "Envoyé quand le convoyeur confirme ; contient le bouton « Donner mon avis »."),
    ("remerciement", "Remerciement après avis",
     "Envoyé automatiquement dès que le client a répondu au formulaire."),
]

# Livraison fictive servant à prévisualiser les modèles sans toucher aux données
EXEMPLE_LIVRAISON = {
    "id": 0,
    "client_prenom": "Amine", "client_nom": "El Fassi",
    "client_email": "client@exemple.ma",
    "vehicule": "Dacia Duster", "immatriculation": "48215-A-1",
    "reservation_num": "RES-4817",
    "date_livraison": "2026-08-20", "heure_livraison": "10:00",
    "heure_reelle": "09:55",
    "lieu_livraison": "Aéroport Marrakech Ménara (RAK)",
    "convoyeur_nom": "Karim Benali", "convoyeur_tel": "+212 6 61 22 33 44",
    "convoyeur_fonction": "Responsable d'agence",
    "token": "apercu-modele-exemple",
}


def composer_test():
    """Email de vérification de la configuration SMTP."""
    contenu = (
        "<p>Bonjour,</p>"
        "<p>Cet email confirme que l'envoi automatique est <strong>correctement "
        "configuré</strong> pour l'application Suivi Livraison.</p>"
        "<p>Vos clients recevront désormais réellement les emails de livraison "
        "et les invitations à donner leur avis.</p>"
        + _tableau_infos([
            ("Serveur SMTP", f"{os.environ.get('SMTP_HOST', '')}:{os.environ.get('SMTP_PORT', '')}"),
            ("Expéditeur", os.environ.get("SMTP_FROM", "")),
            ("Adresse du site", BASE_URL),
        ])
    )
    return "Test de configuration — Suivi Livraison", _gabarit(
        "Configuration email vérifiée ✔", contenu)


def api_configuree():
    """Envoi via l'API HTTP de Brevo : nécessaire là où le SMTP est bloqué
    (hébergements gratuits type PythonAnywhere)."""
    return bool(os.environ.get("BREVO_API_KEY") and os.environ.get("SMTP_FROM"))


def smtp_configure():
    """L'envoi réel n'est tenté que si l'hôte, le port et l'expéditeur sont définis."""
    return all(os.environ.get(v) for v in ("SMTP_HOST", "SMTP_PORT", "SMTP_FROM"))


def envoi_actif():
    return api_configuree() or smtp_configure()


def config_smtp():
    """Configuration courante, pour affichage dans l'interface d'administration."""
    api = api_configuree()
    return {
        "actif": envoi_actif(),
        "methode": "API HTTP Brevo" if api else ("SMTP" if smtp_configure() else ""),
        "par_api": api,
        "hote": "api.brevo.com" if api else os.environ.get("SMTP_HOST", ""),
        "port": "443 (HTTPS)" if api else os.environ.get("SMTP_PORT", ""),
        "expediteur": os.environ.get("SMTP_FROM", ""),
        "utilisateur": os.environ.get("SMTP_USER", ""),
        "mot_de_passe_defini": bool(os.environ.get("BREVO_API_KEY") or os.environ.get("SMTP_PASS")),
        "base_url": BASE_URL,
    }


def _expedier_par_api(destinataire, objet, corps_html):
    """Envoi via l'API transactionnelle de Brevo (HTTPS, port 443)."""
    charge = json.dumps({
        "sender": {"email": os.environ["SMTP_FROM"],
                   "name": os.environ.get("SMTP_FROM_NOM", "Suivi Livraison")},
        "to": [{"email": destinataire}],
        "subject": objet,
        "htmlContent": corps_html,
    }).encode("utf-8")
    requete = urllib.request.Request(
        "https://api.brevo.com/v3/smtp/email", data=charge,
        headers={"api-key": os.environ["BREVO_API_KEY"],
                 "content-type": "application/json",
                 "accept": "application/json"})
    try:
        with urllib.request.urlopen(requete, timeout=20) as r:
            if r.status in (200, 201, 202):
                return "envoyé", ""
            return "erreur", f"Réponse inattendue : HTTP {r.status}"
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        return "erreur", f"HTTP {e.code} — {detail}"
    except Exception as e:
        return "erreur", f"{type(e).__name__} : {e}"[:400]


def expedier(destinataire, objet, corps_html):
    """Envoie réellement un message. Retourne (statut, message d'erreur éventuel).

    Gère les trois configurations courantes : port 465 (SSL implicite),
    port 587 ou 25 avec STARTTLS quand le serveur l'annonce, et serveur local
    de test sans chiffrement.
    """
    # L'API HTTP prime : elle passe là où le port SMTP est fermé.
    if api_configuree():
        return _expedier_par_api(destinataire, objet, corps_html)
    if not smtp_configure():
        return "simulé", ""
    port = int(os.environ["SMTP_PORT"])
    msg = MIMEMultipart("alternative")
    msg["Subject"] = objet
    msg["From"] = os.environ["SMTP_FROM"]
    msg["To"] = destinataire
    msg.attach(MIMEText(corps_html, "html", "utf-8"))
    try:
        if port == 465:
            connexion = smtplib.SMTP_SSL(os.environ["SMTP_HOST"], port, timeout=20)
        else:
            connexion = smtplib.SMTP(os.environ["SMTP_HOST"], port, timeout=20)
        with connexion as s:
            s.ehlo()
            if port != 465 and s.has_extn("starttls"):
                s.starttls()
                s.ehlo()
            if os.environ.get("SMTP_USER"):
                s.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASS", ""))
            s.sendmail(msg["From"], [destinataire], msg.as_string())
        return "envoyé", ""
    except Exception as e:
        # Le motif est conservé : sans lui, un échec SMTP est indiagnosticable.
        return "erreur", f"{type(e).__name__} : {e}"[:400]


def envoyer(db, type_email, liv, utilisateur="système"):
    """Compose, enregistre (RG06) et tente l'envoi réel si SMTP est configuré."""
    objet, corps = composer(type_email, liv)
    statut, erreur = expedier(liv["client_email"], objet, corps)
    quand = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    email_id = db.inserer(
        "INSERT INTO emails (livraison_id, type, destinataire, objet, corps_html,"
        " statut_envoi, message_erreur, envoye_le) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (liv["id"], type_email, liv["client_email"], objet, corps, statut, erreur, quand),
    )
    return email_id, statut
