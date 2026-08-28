# Proxima Quote AI — MVP prêt à lancer


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
