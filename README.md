# Suivi Livraison

Application web de **digitalisation de la livraison des véhicules** pour une agence de
location, réalisée d'après la spécification fonctionnelle `Suivi Livraison.docx`
(v1.0, El Mehdi BABA) : préparation des livraisons, suivi des convoyeurs, confirmation,
emails automatiques, avis clients et statistiques.

## Lancement

Trois possibilités :

- **`SuiviLivraison.exe`** — exécutable autonome, aucun prérequis (ni Python ni
  Flask). Double-clic, le navigateur s'ouvre tout seul. Il peut être copié sur
  n'importe quel PC Windows ; la base `suivi.db` se crée à côté de lui.
  Au premier lancement, Windows SmartScreen peut demander confirmation
  (« Informations complémentaires » → « Exécuter quand même ») : l'exécutable
  n'est pas signé numériquement, c'est normal.
- **`Lancer l'application.bat`** — lance les sources Python (installe Flask si besoin).
- En ligne de commande :

```bash
pip install flask
python app.py
```

L'application est ensuite disponible sur **http://127.0.0.1:5000**.
Pour une mise en ligne sur Internet, voir **`DEPLOIEMENT.md`**.

Au premier lancement, une base de démonstration `suivi.db` est créée automatiquement
(10 livraisons, 5 avis, emails et historiques) pour découvrir l'application remplie.

### Comptes de démonstration

| Rôle | Identifiant | Mot de passe |
|---|---|---|
| Administrateur | `admin` | `admin123` |
| Convoyeur | `karim` / `yassine` / `sofia` | `conv123` |

> Changez ces mots de passe (« Mot de passe » en bas de la barre latérale) avant tout
> usage réel.

### Réinitialiser la base

```bash
python database.py --reset            # base de démonstration
python database.py --reset --no-demo  # base vide (seul le compte admin)
```

Une base créée par une version antérieure est **migrée automatiquement** au
démarrage : ajout du champ « pays de départ » et passage de l'immatriculation et
du convoyeur en facultatifs, sans perte des livraisons, avis, emails ni historique.

## Parcours implémenté (conforme à la spécification)

1. **Création** (admin) — formulaire en 5 blocs : client, réservation, livraison,
   retour, convoyeur. À la validation, l'application génère l'identifiant unique
   (`LIV-AAAA-0000`), le **lien client sécurisé** et le statut.
   Champs **facultatifs** : immatriculation, convoyeur et pays de départ — une
   réservation peut donc être enregistrée avant l'attribution du véhicule ou la
   désignation du convoyeur. Les **lieux de livraison et de retour** se choisissent
   dans des listes (villes, aéroports et ports du Maroc), avec une option
   « Autre » pour une adresse précise (hôtel, agence, domicile).
2. **Email automatique** « Votre véhicule sera livré prochainement » (RG01), avec
   date, heure, lieu, nom et téléphone du convoyeur.
3. **Livraison** (convoyeur, sur mobile) — boutons *Démarrer* puis *Livraison
   effectuée*, saisie de l'**heure réelle** (pré-remplie) et d'un commentaire.
4. **Email de confirmation** « Votre véhicule a été livré » avec récapitulatif et
   bouton **« Donner mon avis »**.
5. **Formulaire de satisfaction** — les 7 questions de la spécification (à l'heure ?,
   état, professionnalisme, propreté, conformité, recommandation, commentaire libre),
   puis « Merci pour votre retour. » et email de remerciement.

Chaîne d'états (§8) : Créée → Email envoyé → En attente → En cours → Livrée →
Avis envoyé → Avis reçu → Terminée — visible sur la fiche livraison et la page
client (« Parcours »).

### Règles de gestion

| Règle | Implémentation |
|---|---|
| RG01 email automatique à la création | envoi + historisation dans `nouvelle_livraison` |
| RG02 lien d'avis unique | jeton aléatoire unique par livraison (`secrets.token_urlsafe`) |
| RG03 une seule réponse client | contrainte `UNIQUE` + garde applicative |
| RG04 livraison validée une seule fois | garde sur le statut avant confirmation |
| RG05 dates historisées | table `historique` alimentée à chaque action |
| RG06 emails enregistrés | table `emails` (consultables depuis la fiche livraison) |
| RG07 score calculé automatiquement | moyenne des 5 notes étoilées, sur 5 |
| §11 expiration des liens | 30 jours après la date de livraison (page « lien expiré ») |

### Champs facultatifs et référentiels de lieux

| Champ | Comportement |
|---|---|
| Immatriculation | facultative ; le badge de plaque disparaît simplement quand elle est absente |
| Convoyeur | facultatif ; la livraison est marquée **« Non affecté »**, comptée sur le tableau de bord et filtrable, le convoyeur pouvant être désigné plus tard |
| Pays de départ | facultatif, dans la section « Informations client » (liste de pays + saisie libre) |
| Lieu de livraison / retour | liste déroulante : **44 villes, 20 aéroports et 23 ports du Maroc**, plus « Autre » pour une adresse libre |

Quand aucun convoyeur n'est désigné, l'email client omet ses coordonnées et indique
qu'elles seront communiquées avant la livraison ; la page de suivi du client affiche
le même message. Le référentiel des lieux et des pays est dans `donnees.py` : il
suffit d'y ajouter une entrée pour l'enrichir.

### Écrans

- **Tableau de bord** (admin) : colonnes de la spécification §6 (réservation, client,
  véhicule, convoyeur, date, heure prévue, heure réelle, statut, satisfaction, avis),
  recherche et filtres (dont **« Non affectées »**), badges de retard (> 15 min).
- **Fiche livraison** : informations, parcours, historique complet, emails envoyés
  (avec aperçu), liens client à copier, rappel, modification, suppression.
- **Statistiques** (§7) : livraisons, retards, écart moyen, note moyenne, avis reçus,
  clients satisfaits, **classement / top convoyeurs**, répartition des notes.
- **Avis clients** : liste des avis avec notes détaillées et commentaires.
- **Convoyeurs** : création et activation/désactivation des comptes.
- **Espace convoyeur** : ses livraisons du jour / à venir / historique, pensé mobile.
- **Pages client** (sans compte, via lien sécurisé) : suivi de livraison et
  formulaire d'avis.

## Envoi réel des emails

Sans configuration, les emails sont **simulés** : composés et enregistrés en base
(consultables dans le menu « Emails »), mais non expédiés.

Pour les envoyer réellement, double-cliquez sur **`Lancer avec emails reels.bat`** :
il propose Brevo (gratuit, 300 emails/jour), Mailjet, Gmail, SMTP2GO ou le serveur
de votre agence, puis demande vos identifiants — saisis de façon masquée et jamais
écrits sur le disque. La marche à suivre complète est dans **`DEPLOIEMENT.md`**.

En ligne de commande, cela revient à définir avant le lancement :

```bash
set SMTP_HOST=smtp-relay.brevo.com
set SMTP_PORT=587
set SMTP_FROM=agence@example.com
set SMTP_USER=votre-login-smtp
set SMTP_PASS=votre-cle-smtp
set BASE_URL=https://votre-domaine.com
python app.py
```

`BASE_URL` sert à construire les liens de suivi et d'avis dans les emails.

### Le menu « Emails » de l'application

- **Les 4 modèles** envoyés au client (création, rappel, confirmation de livraison,
  remerciement), affichables tels que le client les recevra ;
- l'**état de la configuration** : envoi réel activé ou mode simulé, serveur utilisé ;
- un bouton **« Envoyer le test »** vers l'adresse de votre choix ;
- les **derniers emails** avec leur statut — et, en cas d'échec, le **motif exact**
  de l'erreur SMTP, indispensable pour distinguer un mauvais mot de passe d'un
  port bloqué.

## Technique

- **Python 3 + Flask + SQLite** — aucune autre dépendance, pas d'étape de build.
- `app.py` (routes et logique), `database.py` (schéma + démo), `emails.py`
  (gabarits et envoi), `templates/` (Jinja), `static/` (CSS/JS sans framework).
- Sécurité : mots de passe hachés, sessions signées (clé persistante `.secret_key`),
  jeton CSRF sur tous les formulaires, liens client à expiration, actions historisées.
- Interprétations assumées : « temps moyen de livraison » = écart moyen entre heure
  réelle et heure prévue ; un retard est compté au-delà de 15 minutes ; l'email de
  rappel (§9) s'envoie manuellement depuis la fiche livraison.
