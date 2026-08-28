# PROXIMA QUOTE AI — VERSION CLOUD

Cette version est prête à être déployée sur Streamlit Community Cloud.

## Ce qui change

- La clé OpenAI est stockée dans les **Secrets Streamlit**.
- Les visiteurs du site ne voient pas la clé.
- L'application conserve le mode démonstration sans API.
- Le moteur catalogue, les tarifs et le devis fonctionnent comme dans la version locale.

## Fichiers à mettre sur GitHub

Envoie le contenu de ce dossier dans ton dépôt GitHub.

### Ne jamais envoyer sur GitHub

- `.env`
- `.venv`
- `.streamlit/secrets.toml`
- ta vraie clé API OpenAI

## Déploiement

1. Crée un compte GitHub si nécessaire.
2. Crée un dépôt, par exemple `proxima-quote-ai`.
3. Ajoute les fichiers de ce dossier au dépôt.
4. Va sur Streamlit Community Cloud et connecte ton compte GitHub.
5. Clique sur **Create app**.
6. Sélectionne le dépôt.
7. Main file path : `app.py`.
8. Ouvre **Advanced settings**.
9. Dans **Secrets**, colle :

```toml
OPENAI_API_KEY = "TA_CLE_API_OPENAI"
OPENAI_TEXT_MODEL = "gpt-5.6-luna"
OPENAI_TRANSCRIBE_MODEL = "gpt-4o-mini-transcribe"
```

10. Clique sur **Save**, puis **Deploy**.

Après quelques minutes, tu obtiendras une URL publique en `streamlit.app`.

## Sécurité

Si une clé API est publiée par erreur sur GitHub :
- révoque-la immédiatement dans OpenAI Platform ;
- crée une nouvelle clé ;
- mets la nouvelle clé uniquement dans les Secrets Streamlit.
