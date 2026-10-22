# Armor Distripresse → Pennylane — V3 OCR et saisie

## Mettre à jour Streamlit Cloud

Déposer/remplacer à la racine du dépôt **les six fichiers** :

- app.py
- converter.py
- workspace.py
- requirements.txt
- packages.txt
- README.md (documentation)

Le point d’entrée reste app.py. Python 3.12 conseillé. packages.txt installe Tesseract et les langues française et anglaise sur Streamlit Cloud. Si les dépendances système ne sont pas prises en compte après mise à jour, redémarrer l’application depuis sa gestion Streamlit Cloud.

Ne pas publier les archives d’exemples dans un dépôt public : elles contiennent les PDF client.

## Téléchargement indépendant des traitements

Le bouton **Télécharger FEC + PJ** se trouve en haut de la barre latérale, disponible depuis tous les onglets. Il utilise uniquement les écritures déjà stockées dans le projet et ne relance ni le traitement PDF ni l’OCR.

Par défaut, il exporte toutes les pièces sélectionnées avec une écriture complète et équilibrée. Une pièce vide, déséquilibrée, avec compte manquant ou référence en double reste hors export. Les autres pièces peuvent être téléchargées. Le nombre de pièces exportées et la liste des exclusions sont visibles à côté du bouton ; un avertissement indique un export partiel. L’option « uniquement les pièces validées » est facultative.

Le pack contient ECRITURES.txt, PJ.zip, CONTROLE.json (inclusions et exclusions), LIRE_MOI.txt. Décompresser le pack, importer le TXT au format FEC dans Pennylane puis joindre PJ.zip via le trombone. Chaque PDF original est nommé comme PieceRef ; l’extension n’est pas inscrite dans le FEC.

## Ajout et traitements

Dans l’onglet dédié, ajouter un ou plusieurs PDF ou un ZIP Pennylane, puis cliquer sur « Ajouter à la liste ». Les fichiers non PDF sont ignorés et listés. Les doublons exacts ne sont pas ajoutés une seconde fois.

Cliquer ensuite sur « Lire les pièces sans écriture » pour produire les propositions. Les écritures existantes ne sont pas retraitées. L’OCR peut être activé automatiquement lorsqu’un PDF contient moins de 50 caractères de texte ; pour un scan avec quelques annotations ou pour relancer manuellement, utiliser le bouton OCR de la pièce.

Une nouvelle lecture d’une pièce déjà saisie crée une proposition séparée. Elle ne remplace la saisie que lorsque l’utilisateur clique sur « Appliquer la proposition ».

## Saisie

Dans « Pièces et saisie », rechercher et dérouler une pièce. L’aperçu du PDF est affichable à gauche, avec sélection de page. À droite : date, journal, référence et tableau de lignes modifiable.

Les colonnes Compte, Libellé, Débit, Crédit sont libres. Montants positifs avec virgule ou point. Utiliser le + en bas du tableau pour ajouter une ligne ; sélectionner une ou plusieurs lignes dans le tableau pour les supprimer. Valider une cellule avec Entrée avant de télécharger afin que l’édition soit enregistrée. Écart débit/crédit calculé à chaque modification.

Les modèles « Écriture libre », « Achat avec TVA », « Consignes » et « Presse » préparent les comptes sans inventer de montants. L’application d’un modèle remplace explicitement les lignes. Les avoirs se saisissent avec débits et crédits inversés ; leur sens est automatique lorsqu’ils sont reconnus par le lecteur.

La validation d’une pièce est facultative pour l’export par défaut ; une modification comptable retire cette validation. L’équilibre ne prouve ni l’exactitude des montants par rapport au PDF ni la bonne affectation des comptes : vérifier les propositions, surtout après OCR.

## Comptes

Relevés : PR, schéma initial conservé. Factures et avoirs : HA, emballages/consignes 6022, marchandises selon TVA (607055 à 5,5 %, 607200 à 20 %), TVA 44566 par défaut, fournisseur 401HORSP0. Tous les comptes proposés sont paramétrables. Le 401 hors presse est commun à PR et HA. Les factures HA sont comptabilisées intégralement même si leur paiement est différé ; PR transfère les échéances, sans comptabiliser une seconde fois les charges.

La cotisation de 213 € du relevé 2026-27 produit une ligne avec compte vide à renseigner. Aucune TVA n’y est inventée. Le relevé créditeur 2026-28 est pris en charge.

## OCR

Tesseract gratuit, exécuté sur le serveur Streamlit, sans service OCR externe payant. Chaque page est rendue à 300 dpi avant lecture. Le PDF original reste toujours la PJ exportée. Le texte OCR est accessible dans la pièce pour aider la saisie. Les tableaux mal reconnus peuvent nécessiter une saisie manuelle : l’OCR ne garantit pas la reconstitution automatique des écritures. En cas d’erreur de lecture, les corrections existantes sont conservées.

## Sauvegarde et reprise

La session conserve pièces, saisies et paramètres lors des changements de pièce, recherches et ajouts de documents. Elle n’est pas une base de données durable. Avant de quitter, télécharger « Sauvegarder le travail et les PDF » dans « Sauvegarde / reprise ». Le ZIP PROJET_ARMOR contient les données du projet et les PDF, et permet de reprendre après expiration de la session. La restauration remplace le projet ouvert uniquement via le bouton dédié et sa case de confirmation.

## Vérifications effectuées

- V2 : 18 factures/avoirs, 100 lignes articles, 62 lignes HA équilibrées ; 15 relevés PR reconnus, dont un compte supplémentaire à compléter.
- V3 : modification/ajout/suppression de lignes, export partiel, rapprochement des noms de PJ, conservation exacte du PDF, sauvegarde/restauration et démarrage de l’interface avec modification de référence et recherche.
- Test OCR réel sur une facture transformée en PDF image ; récupération du texte vérifiée. La reconstruction peut nécessiter une saisie selon le résultat OCR.

L’import final dans Pennylane n’est pas exécuté par l’application. Fichier partiel au format FEC, pas le FEC fiscal complet ; ValidDate reste vide. Adapter la numérotation entre lots et ne pas réimporter de pièces déjà comptabilisées.
