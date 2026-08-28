# Prototype final — Proxima Équipement

Ce projet représente **Quotexia déjà vendu et déployé en marque blanche chez Proxima Équipement**.

## Principe de la démonstration

Le commercial Proxima ouvre directement son application :
- aucun nom d'entreprise à saisir ;
- aucun catalogue à importer ;
- aucune configuration visible ;
- l'application est déjà au nom de **Proxima Équipement** ;
- le catalogue Proxima est déjà intégré ;
- les devis sont émis par **Proxima Équipement** ;
- le client acheteur est détecté dans l'entretien et reste modifiable avant validation.

## Catalogue intégré

Le fichier `catalogue.csv` contient **120 références synthétiques** réparties dans 6 familles :
- bureaux ;
- chaises ;
- tables de réunion ;
- armoires ;
- cloisons ;
- lampes.

Chaque référence comporte notamment :
- une référence produit ;
- une catégorie ;
- une désignation ;
- une description ;
- des dimensions ou capacités lorsque pertinentes ;
- une couleur ;
- une gamme standard ou premium ;
- un prix d'achat HT ;
- un prix de vente HT ;
- un stock ;
- des mots-clés de recherche.

## Exemple de note pour la soutenance

« Je reviens d'un rendez-vous avec Horizon Conseil à Bordeaux. Ils souhaitent aménager
une nouvelle zone de travail. Il leur faut 20 bureaux blancs d'environ 140 cm, 20 chaises
ergonomiques noires et une table de réunion pour 10 à 12 personnes. Ils veulent comparer
une proposition standard et une proposition premium. La livraison est souhaitée avant
le 15 octobre et l'installation doit être incluse. Je n'ai pas encore l'adresse exacte du site
ni les contraintes d'accès. »

Quotexia doit alors :
1. structurer le besoin ;
2. rechercher uniquement dans les 120 références Proxima ;
3. proposer les références les plus pertinentes ;
4. utiliser les prix et stocks du catalogue ;
5. faire remonter les informations manquantes ;
6. laisser le commercial valider ;
7. générer un devis PDF émis par **Proxima Équipement** et adressé à **Horizon Conseil**.
