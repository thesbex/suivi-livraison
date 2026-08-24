# -*- coding: utf-8 -*-
"""Référentiels de saisie : lieux de livraison / retour et pays de départ.

Les lieux sont regroupés par famille (villes, aéroports, ports du Maroc) pour
être présentés sous forme de listes déroulantes. La saisie libre reste possible
via l'option « Autre » afin de conserver les adresses précises (hôtels, agences,
adresses de particuliers) déjà utilisées.
"""

VILLES = [
    "Agadir", "Al Hoceïma", "Asilah", "Azrou", "Beni Mellal", "Benslimane",
    "Berkane", "Berrechid", "Casablanca", "Chefchaouen", "Dakhla", "El Jadida",
    "Errachidia", "Essaouira", "Fès", "Fnideq", "Guelmim", "Ifrane", "Kénitra",
    "Khémisset", "Khouribga", "Laâyoune", "Larache", "Marrakech", "Martil",
    "Meknès", "Mohammedia", "Nador", "Ouarzazate", "Oujda", "Rabat", "Safi",
    "Salé", "Settat", "Sidi Ifni", "Skhirat", "Tanger", "Tan-Tan", "Taroudant",
    "Taza", "Témara", "Tétouan", "Tiznit", "Zagora",
]

AEROPORTS = [
    "Aéroport Mohammed V, Casablanca (CMN)",
    "Aéroport Marrakech Ménara (RAK)",
    "Aéroport Rabat-Salé (RBA)",
    "Aéroport Tanger Ibn Battouta (TNG)",
    "Aéroport Agadir Al Massira (AGA)",
    "Aéroport Fès-Saïss (FEZ)",
    "Aéroport Oujda Angads (OUD)",
    "Aéroport Nador El Aroui (NDR)",
    "Aéroport Essaouira Mogador (ESU)",
    "Aéroport Ouarzazate (OZZ)",
    "Aéroport Al Hoceïma Chérif Al Idrissi (AHU)",
    "Aéroport Tétouan Saniat R'mel (TTU)",
    "Aéroport Dakhla (VIL)",
    "Aéroport Laâyoune Hassan Ier (EUN)",
    "Aéroport Errachidia Moulay Ali Chérif (ERH)",
    "Aéroport Beni Mellal (BEM)",
    "Aéroport Guelmim (GLN)",
    "Aéroport Tan-Tan Plage Blanche (TTA)",
    "Aéroport Zagora (OZG)",
    "Aéroport Bouarfa (UAR)",
]

PORTS = [
    "Port Tanger Med",
    "Port de Tanger Ville",
    "Port de Casablanca",
    "Port de Mohammedia",
    "Port de Jorf Lasfar, El Jadida",
    "Port de Safi",
    "Port d'Agadir",
    "Port de Nador",
    "Port Nador West Med",
    "Port d'Al Hoceïma",
    "Port de Kénitra Atlantique",
    "Port de Mehdia, Kénitra",
    "Port de Larache",
    "Port d'Essaouira",
    "Port de M'diq",
    "Port de Jebha",
    "Port de Ras Kebdana",
    "Port de Tan-Tan",
    "Port de Sidi Ifni",
    "Port de Tarfaya",
    "Port de Laâyoune",
    "Port de Dakhla",
    "Port de Boujdour",
]

# Groupes affichés dans les listes « Lieu de livraison » et « Lieu de retour »
LIEUX = [
    ("Villes", VILLES),
    ("Aéroports du Maroc", AEROPORTS),
    ("Ports du Maroc", PORTS),
]

TOUS_LES_LIEUX = VILLES + AEROPORTS + PORTS

PAYS = [
    "Maroc", "Algérie", "Tunisie", "Mauritanie", "Sénégal", "Côte d'Ivoire",
    "Mali", "Guinée", "Gabon", "Cameroun", "Égypte", "Libye",
    "France", "Espagne", "Portugal", "Italie", "Belgique", "Pays-Bas",
    "Allemagne", "Suisse", "Royaume-Uni", "Irlande", "Luxembourg", "Autriche",
    "Danemark", "Suède", "Norvège", "Finlande", "Pologne", "République tchèque",
    "Grèce", "Turquie", "Russie", "Ukraine", "Roumanie", "Hongrie",
    "États-Unis", "Canada", "Brésil", "Argentine", "Mexique",
    "Arabie saoudite", "Émirats arabes unis", "Qatar", "Koweït", "Bahreïn",
    "Oman", "Jordanie", "Liban", "Chine", "Japon", "Corée du Sud", "Inde",
    "Australie", "Afrique du Sud",
]
