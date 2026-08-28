# Quotexia — MVP prêt à lancer


## Démarrage sur macOS

1. Décompresse le ZIP.
2. Ouvre le dossier `proxima_quote_ai`.
3. Clic droit sur `INSTALLER_MAC.command` → **Ouvrir**.
4. Confirme l'ouverture si macOS affiche un avertissement.
5. Une fois l'installation terminée, ouvre `LANCER_MAC.command`.

Si macOS bloque encore le fichier, va dans :
**Réglages Système → Confidentialité et sécurité → Ouvrir quand même**.

Si nécessaire, dans Terminal :

```bash
cd /chemin/vers/proxima_quote_ai
chmod +x INSTALLER_MAC.command LANCER_MAC.command
./INSTALLER_MAC.command
./LANCER_MAC.command
```


Prototype scolaire de génération assistée de brouillons de devis.

## Ce que fait l'application

1. Accepte une note commerciale en texte **ou** un fichier audio.
2. Transcrit l'audio via l'API OpenAI.
3. Utilise un modèle OpenAI pour extraire un besoin structuré.
4. Cherche des références uniquement dans `catalogue.csv`.
5. Applique les règles de prix de `regles_tarifaires.csv`.
6. Produit deux variantes (standard / premium).
7. Signale les informations manquantes et les problèmes de stock.
8. Génère un brouillon de devis téléchargeable **seulement après validation humaine**.
9. Permet de télécharger une trace JSON des sources.

## Important

Le catalogue, les stocks et les règles tarifaires sont **simulés pour le projet scolaire**.
Aucune donnée réelle de Proxima Équipements n'a été inventée.

## Démarrage le plus simple

### Windows

1. Installe Python 3.11 ou 3.12 depuis python.org.
2. Décompresse le dossier.
3. Double-clique sur `INSTALLER_WINDOWS.bat`.
4. Puis double-clique sur `LANCER_WINDOWS.bat`.
5. Le navigateur s'ouvre sur l'application.

### macOS / Linux

Dans le Terminal :

```bash
cd proxima_quote_ai
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Clé API OpenAI

L'application peut être testée sans clé grâce au bouton **Mode démonstration sans API**.

Pour activer la vraie extraction IA et la transcription :
- ouvre l'application ;
- colle ta clé dans la barre latérale « Clé API OpenAI ».

La clé n'est pas écrite par l'application dans le code.

Tu peux aussi créer un fichier `.env` en copiant `.env.example` :

```env
OPENAI_API_KEY=ta_cle
OPENAI_TEXT_MODEL=gpt-5.6-luna
OPENAI_TRANSCRIBE_MODEL=gpt-4o-mini-transcribe
```

## Scénario de démonstration conseillé

> Je reviens de chez Dupont Consulting à Lyon. Ils aménagent une nouvelle salle de réunion.
> Ils veulent une table pour environ douze personnes et douze chaises ergonomiques noires.
> Ils aimeraient quelque chose d'assez qualitatif, avec une variante standard et une variante premium.
> Livraison souhaitée avant le 20 septembre 2026. Il faudra probablement prévoir l'installation.
> Je n'ai pas encore l'adresse exacte du site ni le nom du contact.

## Fichiers

- `app.py` : application complète.
- `catalogue.csv` : 120 références synthétiques.
- `regles_tarifaires.csv` : règles du moteur de prix.
- `requirements.txt` : dépendances Python.
- `.env.example` : exemple de configuration.
- `INSTALLER_WINDOWS.bat` : installation automatique Windows.
- `LANCER_WINDOWS.bat` : lancement automatique Windows.

## Architecture de sécurité

L'IA n'invente ni référence ni prix :
- le modèle extrait seulement le besoin ;
- le programme filtre le catalogue ;
- les prix viennent du CSV ;
- le stock affiché vient du CSV ;
- si le stock est insuffisant, le système demande une validation ;
- le devis reste un brouillon jusqu'à validation humaine.

## Limite volontaire du MVP

Le système ne se connecte pas au véritable ERP/stock de Proxima. En production, `catalogue.csv`
serait remplacé par une base de données ou une API d'entreprise.

## V3 — édition humaine du devis

L'onglet **Devis** permet maintenant au commercial de :
- compléter client, contact, adresse et date cible ;
- modifier la quantité finale ;
- choisir une autre référence parmi la shortlist catalogue ;
- ajuster une remise dans la limite commerciale autorisée ;
- confirmer livraison et installation ;
- saisir les réponses obtenues auprès du client ;
- enregistrer les corrections et recalculer le devis ;
- consulter la traçabilité des modifications ;
- valider humainement avant téléchargement du devis final.

Les références et les prix restent issus du catalogue : l'édition humaine ne permet pas d'inventer une référence ou un prix.

## V4 — devis client épuré

Le devis téléchargé par le commercial n'affiche plus :
- la traçabilité détaillée des corrections humaines ;
- les anciennes valeurs et nouvelles valeurs ;
- les mentions techniques de type `False` ;
- le message interne de validation humaine ;
- les questions restées sans réponse.

Ces informations restent disponibles dans l'application et dans le fichier JSON de traçabilité interne.

Le devis client ne conserve que les informations commerciales utiles :
client, contact, site, adresse, lignes produits, quantités, prix, livraison, installation, informations complémentaires réellement renseignées, total et validité de l'offre.


## V5 — identité Quotexia, TVA et refonte visuelle

- L'application s'appelle désormais **Quotexia**.
- La charte visuelle reprend les codes fournis : bleu nuit, bleu électrique, violet et gris clair.
- Le contenu et le workflow métier restent identiques.
- Le devis affiche désormais :
  - Total HT ;
  - TVA ;
  - Total TTC.
- Le taux de TVA est paramétré dans `regles_tarifaires.csv` via `tva_pct` (20 % dans le MVP).
- Le devis client a également été modernisé visuellement.


## V6 — application mobile, enregistrement direct et PDF

- Interface mobile-first en une seule colonne.
- Enregistrement vocal directement dans Quotexia avec le microphone du téléphone.
- Transcription affichée et modifiable avant analyse IA.
- Saisie texte conservée comme solution de secours.
- Devis final téléchargé en PDF.
- Calcul HT, TVA et TTC conservé.


## V6.1 — correction visuelle mobile

- Correction du contraste sur iPhone / mobile.
- Thème clair forcé via `.streamlit/config.toml`.
- Recoloration explicite des labels, champs, cartes, onglets et métriques.
- Aucun changement fonctionnel métier.


## V7 — catalogue configurable par entreprise

Quotexia n'est plus lié à un seul catalogue de démonstration.

Chaque entreprise cliente peut :
- renseigner son nom ;
- importer son propre catalogue en CSV ou XLSX ;
- utiliser ses propres catégories de produits ;
- utiliser ses propres références, prix et stocks ;
- générer ensuite les devis uniquement à partir de ce catalogue actif.

Colonnes obligatoires :
`reference`, `categorie`, `nom`, `prix_vente_ht`.

Colonnes optionnelles :
`description`, `stock`, `gamme`, `prix_achat_ht`, `couleur`,
`longueur_cm`, `largeur_cm`, `capacite_personnes`, `mots_cles`.

Dans cette version MVP Streamlit, le catalogue importé est conservé pendant la session utilisateur.
Pour une version SaaS industrielle, les catalogues seraient stockés dans une base sécurisée par entreprise avec authentification.


## V7.1 — entreprise vendeuse affichée sur chaque devis

Le nom saisi dans **Catalogue de l’entreprise > Nom de l’entreprise vendeuse**
est désormais utilisé comme émetteur du devis.

Exemple :
- entreprise vendeuse : `Martin Électricité`
- client final détecté dans le rendez-vous : `Horizon Conseil`

Le PDF affiche **MARTIN ÉLECTRICITÉ** en en-tête, puis `Horizon Conseil`
dans la partie Client.

L’activation d’un catalogue personnalisé exige maintenant que le nom
de l’entreprise vendeuse soit renseigné.


## V7.1.1 — correctif démarrage

Correction d'un `NameError` au chargement du catalogue par défaut :
la normalisation des noms de colonnes est désormais autonome et ne dépend plus
d'une fonction définie plus bas dans le fichier.


## V7.1.2 — correctif pandas

Correction du chargement du catalogue :
les valeurs manquantes de `description`, `mots_cles` et `gamme`
sont maintenant complétées avec `Series.mask()`, compatible avec pandas récent.
