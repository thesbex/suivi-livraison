# Envoi des emails et mise en ligne

## Partie 1 — Activer l'envoi réel des emails

Sans configuration, les emails sont **simulés** : composés et enregistrés (donc
consultables dans le menu « Emails »), mais non expédiés. Pour qu'ils partent
réellement, il faut un serveur SMTP.

### Le plus simple : Brevo (gratuit, 300 emails/jour)

1. Créez un compte sur **brevo.com** (gratuit, sans carte bancaire).
2. Confirmez votre adresse email.
3. Menu **SMTP & API** → onglet **SMTP** → *Générer une nouvelle clé SMTP*.
4. Notez le **login** (votre email) et la **clé SMTP** générée — c'est elle qui
   sert de mot de passe, pas celui de votre compte Brevo.
5. Double-cliquez sur **`Lancer avec emails reels.bat`**, choisissez `1` (Brevo)
   et saisissez ces deux informations.
6. Dans l'application : menu **Emails** → saisissez une adresse → **Envoyer le test**.
   L'email doit arriver en quelques secondes (vérifiez aussi les indésirables).

Le mot de passe est saisi de façon masquée et n'est **jamais écrit sur le disque** :
il n'est valable que pour la session en cours. Fermer la fenêtre l'efface.

### Autres services gratuits

| Service | Gratuité | Serveur SMTP | Port |
|---|---|---|---|
| **Brevo** | 300 / jour | `smtp-relay.brevo.com` | 587 |
| **Mailjet** | 200 / jour | `in-v3.mailjet.com` | 587 |
| **SMTP2GO** | 1000 / mois | `mail.smtp2go.com` | 587 |
| **Gmail** | 500 / jour | `smtp.gmail.com` | 587 |

Pour Gmail, le mot de passe habituel ne fonctionne pas : il faut un
**mot de passe d'application** (`myaccount.google.com/apppasswords`), qui exige
que la validation en deux étapes soit activée.

### Brancher ensuite le serveur de l'agence

Relancez le même fichier `.bat`, choisissez `5` (Autre serveur) et saisissez les
informations fournies par votre hébergeur. Rien d'autre à modifier.

### Vérifier que ça marche

Le menu **Emails** de l'application indique en permanence l'état :
« Envoi réel activé » ou « Mode simulé », le serveur utilisé, et la liste des
derniers emails avec leur statut (*envoyé*, *simulé*, *erreur*). En cas d'échec,
**le motif exact est affiché** sous l'email concerné — c'est ce qui permet de
distinguer un mauvais mot de passe d'un port bloqué par le pare-feu.

---

## Partie 2 — Mettre Suivi Livraison en ligne

L'application est un site Flask + SQLite classique : n'importe quel hébergeur Python
convient. Le fichier `suivi-livraison-deploiement.zip` (généré à côté de ce document)
contient exactement ce qu'il faut téléverser.

> **Important avant toute mise en ligne réelle**
> 1. Changez le mot de passe `admin` (menu « Mot de passe »).
> 2. Configurez les variables `SMTP_*` (partie 1 ci-dessus).
> 3. Définissez `BASE_URL` avec l'adresse publique du site (elle sert à construire
>    les liens de suivi et d'avis dans les emails).

## Environnement de test type production : Render + Neon (gratuit)

C'est le montage retenu : PostgreSQL comme en production, HTTPS, URL publique
à transmettre aux testeurs. L'application détecte automatiquement le moteur —
si `DATABASE_URL` est définie elle utilise PostgreSQL, sinon SQLite en local.

### 1. La base de données — Neon (5 min)

1. Créez un compte sur **neon.tech** (gratuit et permanent, 0,5 Go).
2. *Create project* → nom `suivi-livraison`, région **Europe (Frankfurt)**.
3. Copiez la **Connection string** proposée. Elle ressemble à :
   `postgresql://user:motdepasse@ep-xxx.eu-central-1.aws.neon.tech/neondb?sslmode=require`

### 2. Le code — GitHub (5 min)

Render déploie depuis un dépôt Git.

```bash
git init
git add .
git commit -m "Suivi Livraison"
gh repo create suivi-livraison --private --source=. --push
```

Vérifiez que `suivi.db`, `.secret_key` et `erreurs.log` ne sont pas envoyés :
le fichier `.gitignore` les exclut déjà.

### 3. Le serveur — Render (5 min)

1. Créez un compte sur **render.com**, connectez votre GitHub.
2. *New* → *Web Service* → choisissez le dépôt. Render lit `render.yaml`
   et pré-remplit tout (build, démarrage, région, plan gratuit).
3. Onglet **Environment**, ajoutez :

   | Variable | Valeur |
   |---|---|
   | `DATABASE_URL` | la chaîne Neon copiée à l'étape 1 |
   | `BASE_URL` | `https://suivi-livraison.onrender.com` (l'URL que Render vous donne) |
   | `SMTP_FROM` | votre adresse expéditeur validée chez Brevo |
   | `SMTP_HOST` | `smtp-relay.brevo.com` |
   | `SMTP_PORT` | `587` |
   | `SMTP_USER` | votre login SMTP Brevo |
   | `SMTP_PASS` | votre clé SMTP Brevo |

   `SECRET_KEY` est générée automatiquement par Render.

4. *Deploy*. Au premier démarrage, le schéma et les données de démonstration
   sont créés tout seuls.

### À savoir sur l'offre gratuite de Render

Le service **s'endort après 15 minutes sans visite** : le premier testeur qui
arrive attend une cinquantaine de secondes, les suivants non. Prévenez-les,
c'est le comportement normal du palier gratuit.

Pour repartir d'une base propre : `DATABASE_URL=... python database.py --reset`

---

## Autre option : PythonAnywhere (gratuit, avec SQLite)

PythonAnywhere conserve les fichiers entre les déploiements — la base SQLite y est
donc persistante, contrairement aux offres gratuites de Render/Railway/Heroku où le
disque est effacé à chaque redéploiement.

1. Créez un compte sur **www.pythonanywhere.com** (offre « Beginner » gratuite).
2. Onglet **Files** : téléversez `suivi-livraison-deploiement.zip`, puis dans une
   console **Bash** :
   ```bash
   unzip suivi-livraison-deploiement.zip -d suivi-livraison
   cd suivi-livraison
   pip install --user flask
   python database.py            # crée la base (ajoutez --no-demo pour partir à vide)
   ```
3. Onglet **Web** → *Add a new web app* → *Manual configuration* → version de
   Python la plus récente proposée.
4. Dans la section **Code** : *Source code* = `/home/VOTRE_NOM/suivi-livraison`.
5. Cliquez sur le lien du **WSGI configuration file** et remplacez tout son contenu
   par :
   ```python
   import os
   import sys

   sys.path.insert(0, "/home/VOTRE_NOM/suivi-livraison")
   os.environ["BASE_URL"] = "https://VOTRE_NOM.pythonanywhere.com"
   # Pour l'envoi réel des emails :
   # os.environ["SMTP_HOST"] = "smtp.example.com"
   # os.environ["SMTP_PORT"] = "587"
   # os.environ["SMTP_FROM"] = "agence@example.com"
   # os.environ["SMTP_USER"] = "agence@example.com"
   # os.environ["SMTP_PASS"] = "motdepasse"

   from app import app as application
   ```
   (remplacez `VOTRE_NOM` par votre identifiant PythonAnywhere)
6. Bouton vert **Reload** : le site est en ligne sur
   `https://VOTRE_NOM.pythonanywhere.com`, en HTTPS.

Les liens envoyés aux clients et aux convoyeurs fonctionneront alors depuis
n'importe quel téléphone.

## Alternatives

- **Render / Railway / Fly.io** — très bien aussi, mais avec SQLite il faut un
  disque persistant (payant sur les offres de base) sinon les données sont perdues
  à chaque redéploiement. Commande de démarrage : `gunicorn app:app`
  (ajoutez `gunicorn` à `requirements.txt`).
- **VPS (OVH, Contabo, etc.)** — `pip install flask gunicorn`, puis
  `gunicorn -b 127.0.0.1:8000 app:app` derrière Nginx en HTTPS.
- **Réseau local uniquement** (bureau de l'agence) : lancez simplement
  `SuiviLivraison.exe` sur un poste et remplacez dans `app.py`
  `host="127.0.0.1"` par `host="0.0.0.0"` pour que les collègues du même réseau
  y accèdent via l'adresse IP du poste.

## Contenu du zip de déploiement

`app.py`, `database.py`, `emails.py`, `templates/`, `static/`,
`requirements.txt`, `README.md` — sans la base de données ni la clé de session
(elles se créent automatiquement au premier lancement sur le serveur).
