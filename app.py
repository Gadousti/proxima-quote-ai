import os
import io
import json
import math
import unicodedata
from datetime import date, timedelta
from pathlib import Path
from typing import List, Optional, Literal

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from openai import OpenAI

load_dotenv()

APP_DIR = Path(__file__).parent
CATALOG_PATH = APP_DIR / "catalogue.csv"
RULES_PATH = APP_DIR / "regles_tarifaires.csv"

st.set_page_config(page_title="Proxima Quote AI", page_icon="🧾", layout="wide")

# ---------------------------
# Models
# ---------------------------
Category = Literal["bureau", "chaise", "table_reunion", "armoire", "cloison", "lampe", "autre"]
Range = Literal["standard", "premium", "indeterminee"]

class ClientInfo(BaseModel):
    nom: Optional[str] = None
    contact: Optional[str] = None
    site: Optional[str] = None
    adresse: Optional[str] = None

class NeedItem(BaseModel):
    categorie: Category
    description_client: str
    quantite: Optional[int] = Field(default=None, ge=1)
    longueur_cm: Optional[float] = None
    largeur_cm: Optional[float] = None
    capacite_personnes: Optional[int] = None
    couleur: Optional[str] = None
    gamme: Range = "indeterminee"
    contraintes: List[str] = []
    demande_expresse: bool = True

class CommercialNeed(BaseModel):
    client: ClientInfo
    besoins: List[NeedItem]
    date_cible: Optional[str] = None
    livraison: Optional[bool] = None
    installation: Optional[bool] = None
    reprise: Optional[bool] = None
    variantes_standard_premium: bool = False
    informations_manquantes: List[str] = []
    recommandations_autorisees: bool = True

# ---------------------------
# Data loading
# ---------------------------
@st.cache_data
def load_catalog():
    df = pd.read_csv(CATALOG_PATH)
    for c in ["longueur_cm","largeur_cm","capacite_personnes","prix_achat_ht","prix_vente_ht","stock"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df

@st.cache_data
def load_rules():
    df = pd.read_csv(RULES_PATH)
    return {r["regle"]: float(r["valeur"]) for _, r in df.iterrows()}

catalog = load_catalog()
rules = load_rules()

# ---------------------------
# Helpers
# ---------------------------
def normalize(s):
    if s is None:
        return ""
    s = str(s).lower().strip()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return s

def get_api_key():
    # 1) Secret Streamlit Cloud
    try:
        if "OPENAI_API_KEY" in st.secrets:
            key = str(st.secrets["OPENAI_API_KEY"]).strip()
            if key:
                return key
    except Exception:
        pass

    # 2) Variable d'environnement / .env en local
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if key:
        return key

    # 3) Champ manuel uniquement pour les tests locaux
    return st.session_state.get("api_key_input", "").strip()

def client_from_sidebar():
    key = get_api_key()
    if not key:
        return None
    return OpenAI(api_key=key)

def transcribe_audio(client, uploaded_file, model):
    uploaded_file.seek(0)
    result = client.audio.transcriptions.create(
        model=model,
        file=(uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type or "audio/mpeg"),
        language="fr",
    )
    return result.text

SYSTEM_PROMPT = """
Tu analyses la note d'un commercial après un rendez-vous client pour préparer un brouillon de devis.
Ta mission est UNIQUEMENT d'extraire le besoin et de le normaliser.

Règles impératives :
- N'invente aucune information.
- Toute information absente ou incertaine doit être null ou placée dans informations_manquantes.
- Ne propose JAMAIS de référence produit, de prix, de stock ou de disponibilité : ils proviennent d'une base externe.
- Distingue la demande explicite du client d'une recommandation.
- Catégories autorisées : bureau, chaise, table_reunion, armoire, cloison, lampe, autre.
- Gamme autorisée : standard, premium, indeterminee.
- Convertis les dimensions en centimètres quand c'est possible.
- Si le client demande deux options de niveau de gamme, variantes_standard_premium = true.
- livraison, installation et reprise valent true seulement si demandées/confirmées, false seulement si explicitement exclues, sinon null.
- Les informations manquantes doivent être courtes et directement actionnables.
"""

def extract_with_ai(client, text, model):
    # Official Responses API structured outputs through Pydantic.
    response = client.responses.parse(
        model=model,
        instructions=SYSTEM_PROMPT,
        input=text,
        text_format=CommercialNeed,
    )
    # Most recent SDK exposes output_parsed; fallback to parsed content.
    parsed = getattr(response, "output_parsed", None)
    if parsed is not None:
        return parsed
    for out in response.output:
        if getattr(out, "type", None) == "message":
            for item in out.content:
                p = getattr(item, "parsed", None)
                if p is not None:
                    return p
    # Fallback: parse output_text in case SDK shape differs.
    return CommercialNeed.model_validate_json(response.output_text)

def demo_need():
    return CommercialNeed(
        client=ClientInfo(
            nom="Dupont Consulting",
            site="Lyon",
            adresse=None,
            contact=None,
        ),
        besoins=[
            NeedItem(
                categorie="table_reunion",
                description_client="une table de réunion pour environ 12 personnes",
                quantite=1,
                capacite_personnes=12,
                gamme="premium",
                contraintes=["usage salle de réunion"],
                demande_expresse=True,
            ),
            NeedItem(
                categorie="chaise",
                description_client="douze chaises ergonomiques noires",
                quantite=12,
                couleur="noir",
                gamme="premium",
                contraintes=["ergonomique"],
                demande_expresse=True,
            ),
        ],
        date_cible="20 septembre 2026",
        livraison=True,
        installation=True,
        reprise=None,
        variantes_standard_premium=True,
        informations_manquantes=[
            "Adresse exacte du site",
            "Nom et coordonnées du contact",
            "Contraintes d'accès pour la livraison",
        ],
    )

def score_candidate(row, need, target_range=None):
    if row["categorie"] != need.categorie:
        return -9999, []

    score = 40.0
    reasons = ["catégorie compatible"]

    wanted_range = target_range or (None if need.gamme == "indeterminee" else need.gamme)
    if wanted_range:
        if row["gamme"] == wanted_range:
            score += 22
            reasons.append(f"gamme {wanted_range}")
        else:
            score -= 12

    if need.couleur:
        if normalize(row["couleur"]) == normalize(need.couleur):
            score += 15
            reasons.append("couleur correspondante")
        else:
            score -= 5

    if need.longueur_cm and not pd.isna(row["longueur_cm"]):
        diff = abs(float(row["longueur_cm"]) - need.longueur_cm)
        if diff <= 10:
            score += 15
            reasons.append("dimension proche")
        elif diff <= 30:
            score += 8
        else:
            score -= min(12, diff/20)

    if need.largeur_cm and not pd.isna(row["largeur_cm"]):
        diff = abs(float(row["largeur_cm"]) - need.largeur_cm)
        if diff <= 10:
            score += 10
        elif diff <= 25:
            score += 5

    if need.capacite_personnes and not pd.isna(row["capacite_personnes"]):
        capacity = int(row["capacite_personnes"])
        if capacity >= need.capacite_personnes:
            score += 18
            reasons.append("capacité suffisante")
            score -= max(0, capacity - need.capacite_personnes) * 0.5
        else:
            score -= 30
            reasons.append("capacité insuffisante")

    text = normalize(f"{row['nom']} {row['description']} {row['mots_cles']}")
    query_tokens = set(normalize(need.description_client + " " + " ".join(need.contraintes)).split())
    useful = [t for t in query_tokens if len(t) >= 4 and t in text]
    score += min(15, len(useful)*3)
    if useful:
        reasons.append("mots-clés : " + ", ".join(useful[:4]))

    return score, reasons

def find_candidates(need, target_range=None, top_n=3):
    scores = []
    for idx, row in catalog.iterrows():
        score, reasons = score_candidate(row, need, target_range)
        if score > -100:
            scores.append((score, idx, reasons))
    scores.sort(reverse=True, key=lambda x: x[0])
    results = []
    for score, idx, reasons in scores[:top_n]:
        r = catalog.loc[idx].to_dict()
        r["score"] = round(score, 1)
        r["raisons"] = reasons
        results.append(r)
    return results

def quantity_discount(qty):
    if qty >= 50:
        return rules["remise_qte_50_pct"] / 100
    if qty >= 20:
        return rules["remise_qte_20_pct"] / 100
    return 0.0

def select_variant(need, target_range):
    cands = find_candidates(need, target_range, 3)
    if not cands:
        return None, []
    return cands[0], cands

def build_variant(need_obj, target_range):
    lines = []
    warnings = []
    total_products = 0.0
    total_cost = 0.0

    for need in need_obj.besoins:
        if need.categorie == "autre":
            warnings.append(f"Produit non couvert par le catalogue simulé : {need.description_client}")
            continue
        if not need.quantite:
            warnings.append(f"Quantité manquante : {need.description_client}")
            continue

        product, candidates = select_variant(need, target_range)
        if not product:
            warnings.append(f"Aucune référence certaine trouvée pour : {need.description_client}")
            continue

        qty = int(need.quantite)
        unit_price = float(product["prix_vente_ht"])
        cost = float(product["prix_achat_ht"])
        discount = quantity_discount(qty)
        discounted_unit = unit_price * (1-discount)
        line_total = discounted_unit * qty
        margin_pct = ((discounted_unit - cost) / discounted_unit * 100) if discounted_unit else 0
        stock = int(product["stock"])

        if stock < qty:
            warnings.append(
                f"{product['reference']} : stock catalogue {stock}, quantité demandée {qty}. "
                "Disponibilité non confirmée : validation requise."
            )
        if margin_pct < rules["marge_minimale_pct"]:
            warnings.append(
                f"{product['reference']} : marge {margin_pct:.1f}% sous le minimum "
                f"{rules['marge_minimale_pct']:.0f}%. Validation commerciale requise."
            )

        lines.append({
            "reference": product["reference"],
            "designation": product["nom"],
            "categorie": product["categorie"],
            "quantite": qty,
            "prix_catalogue": unit_price,
            "remise_pct": discount*100,
            "prix_unitaire_net": discounted_unit,
            "total_ht": line_total,
            "stock_catalogue": stock,
            "marge_pct": margin_pct,
            "score_matching": product["score"],
            "source_reference": "catalogue.csv",
            "source_prix": "catalogue.csv",
            "source_quantite": "note commerciale / extraction IA",
            "candidats": candidates,
        })
        total_products += line_total
        total_cost += cost * qty

    delivery = rules["livraison_standard_ht"] if need_obj.livraison is True else 0.0
    install_qty = sum(l["quantite"] for l in lines)
    installation = rules["installation_unitaire_ht"] * install_qty if need_obj.installation is True else 0.0
    total = total_products + delivery + installation

    return {
        "gamme": target_range,
        "lignes": lines,
        "livraison_ht": delivery,
        "installation_ht": installation,
        "total_ht": total,
        "warnings": warnings,
    }

def missing_questions(need_obj, variants):
    qs = list(dict.fromkeys(need_obj.informations_manquantes))
    if not need_obj.client.nom:
        qs.append("Quel est le nom exact du client ?")
    if not need_obj.client.site and not need_obj.client.adresse:
        qs.append("Quel est le site / l'adresse de livraison ?")
    if not need_obj.date_cible:
        qs.append("Quelle est la date cible ?")
    if need_obj.livraison is None:
        qs.append("La livraison doit-elle être incluse ?")
    if need_obj.installation is None:
        qs.append("L'installation doit-elle être incluse ?")
    for v in variants:
        for w in v["warnings"]:
            if "stock catalogue" in w:
                qs.append("Confirmer la disponibilité / le délai de la référence concernée.")
            if "Aucune référence" in w:
                qs.append("Préciser le besoin produit pour permettre une correspondance catalogue certaine.")
    return list(dict.fromkeys(qs))

def money(x):
    return f"{x:,.2f} €".replace(",", " ").replace(".", ",")

def quote_html(need_obj, variant):
    today = date.today()
    validity = int(rules["validite_devis_jours"])
    lines_html = ""
    for l in variant["lignes"]:
        lines_html += f"""
        <tr>
          <td>{l['reference']}</td><td>{l['designation']}</td><td>{l['quantite']}</td>
          <td>{money(l['prix_unitaire_net'])}</td><td>{money(l['total_ht'])}</td>
        </tr>"""
    return f"""<!doctype html>
<html lang="fr"><meta charset="utf-8">
<title>Brouillon de devis Proxima</title>
<style>
body{{font-family:Arial,sans-serif;max-width:960px;margin:40px auto;color:#222}}
h1{{margin-bottom:4px}} .muted{{color:#666}} .warning{{background:#fff3cd;padding:12px;border-radius:8px}}
table{{width:100%;border-collapse:collapse;margin:20px 0}} th,td{{border:1px solid #ddd;padding:8px;text-align:left}}
th{{background:#f5f5f5}} .total{{font-size:1.25rem;font-weight:bold;text-align:right}}
</style>
<h1>PROXIMA ÉQUIPEMENTS</h1>
<div class="muted">BROUILLON DE DEVIS — VALIDATION HUMAINE REQUISE</div>
<p><b>Client :</b> {need_obj.client.nom or "À confirmer"}<br>
<b>Site :</b> {need_obj.client.adresse or need_obj.client.site or "À confirmer"}<br>
<b>Contact :</b> {need_obj.client.contact or "À confirmer"}<br>
<b>Date cible :</b> {need_obj.date_cible or "À confirmer"}<br>
<b>Variante :</b> {variant['gamme'].capitalize()}</p>
<table><thead><tr><th>Référence</th><th>Désignation</th><th>Qté</th><th>PU net HT</th><th>Total HT</th></tr></thead>
<tbody>{lines_html}</tbody></table>
<p>Livraison : {money(variant['livraison_ht'])}<br>
Installation : {money(variant['installation_ht'])}</p>
<div class="total">TOTAL HT : {money(variant['total_ht'])}</div>
<p>Validité de l'offre : {validity} jours (jusqu'au {(today+timedelta(days=validity)).strftime("%d/%m/%Y")}).</p>
<div class="warning"><b>Important :</b> ceci est un brouillon. Aucune référence, disponibilité ou remise hors cadre
ne doit être envoyée au client sans validation humaine.</div>
</html>"""

# ---------------------------
# UI
# ---------------------------
st.title("🧾 Proxima Quote AI")
st.caption("Prototype scolaire — note commerciale → besoin structuré → catalogue vérifié → brouillon de devis")

with st.sidebar:
    st.header("Configuration")
    if get_api_key():
        st.success("API OpenAI configurée")
    else:
        st.warning("API OpenAI non configurée")
        with st.expander("Clé API pour test local"):
            st.text_input(
                "Clé API OpenAI",
                type="password",
                key="api_key_input",
                help="En ligne, la clé doit être ajoutée dans les Secrets Streamlit."
            )
    text_model = st.text_input("Modèle texte", value=(st.secrets.get("OPENAI_TEXT_MODEL", os.getenv("OPENAI_TEXT_MODEL", "gpt-5.6-luna")) if hasattr(st, "secrets") else os.getenv("OPENAI_TEXT_MODEL", "gpt-5.6-luna")))
    transcribe_model = st.text_input("Modèle transcription", value=(st.secrets.get("OPENAI_TRANSCRIBE_MODEL", os.getenv("OPENAI_TRANSCRIBE_MODEL", "gpt-4o-mini-transcribe")) if hasattr(st, "secrets") else os.getenv("OPENAI_TRANSCRIBE_MODEL", "gpt-4o-mini-transcribe")))
    st.divider()
    st.metric("Références catalogue", len(catalog))
    st.caption("Base simulée pour le MVP. Prix, stock et références viennent uniquement du CSV.")

tab1, tab2, tab3 = st.tabs(["1. Saisie", "2. Analyse & catalogue", "3. Devis"])

with tab1:
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Note commerciale")
        default_text = (
            "Je reviens de chez Dupont Consulting à Lyon. Ils aménagent une nouvelle salle de réunion. "
            "Ils veulent une table pour environ douze personnes et douze chaises ergonomiques noires. "
            "Ils aimeraient quelque chose d'assez qualitatif, avec une variante standard et une variante premium. "
            "Livraison souhaitée avant le 20 septembre 2026. Il faudra probablement prévoir l'installation. "
            "Je n'ai pas encore l'adresse exacte du site ni le nom du contact."
        )
        note_text = st.text_area("Texte / résumé du rendez-vous", value=default_text, height=240)

    with col2:
        st.subheader("Ou importer une note vocale")
        audio = st.file_uploader("Audio", type=["mp3","wav","m4a","mp4","mpeg","mpga","ogg","webm"])
        if audio is not None:
            st.audio(audio)

        if st.button("🎙️ Transcrire l'audio", use_container_width=True, disabled=audio is None):
            client = client_from_sidebar()
            if not client:
                st.error("Ajoute une clé API OpenAI dans la barre latérale pour transcrire l'audio.")
            else:
                try:
                    with st.spinner("Transcription..."):
                        tr = transcribe_audio(client, audio, transcribe_model)
                    st.session_state["transcription"] = tr
                    st.success("Transcription terminée.")
                except Exception as e:
                    st.error(f"Erreur de transcription : {e}")

        if "transcription" in st.session_state:
            st.text_area("Transcription", st.session_state["transcription"], height=190, key="transcription_view")
            if st.button("Utiliser cette transcription"):
                st.session_state["text_for_analysis"] = st.session_state["transcription"]
                st.success("La transcription sera utilisée pour l'analyse.")

    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🤖 Analyser avec l'IA", type="primary", use_container_width=True):
            client = client_from_sidebar()
            if not client:
                st.error("Ajoute une clé API OpenAI, ou utilise le bouton Mode démonstration.")
            else:
                text_to_use = st.session_state.get("text_for_analysis", note_text).strip()
                if not text_to_use:
                    st.warning("Ajoute une note commerciale.")
                else:
                    try:
                        with st.spinner("Extraction structurée du besoin..."):
                            need = extract_with_ai(client, text_to_use, text_model)
                        st.session_state["need_json"] = need.model_dump(mode="json")
                        st.session_state["source_note"] = text_to_use
                        st.success("Besoin extrait. Ouvre l'onglet « Analyse & catalogue ».")
                    except Exception as e:
                        st.error(f"Erreur API : {e}")
    with c2:
        if st.button("🧪 Mode démonstration sans API", use_container_width=True):
            need = demo_need()
            st.session_state["need_json"] = need.model_dump(mode="json")
            st.session_state["source_note"] = default_text
            st.success("Scénario de démonstration chargé.")

with tab2:
    if "need_json" not in st.session_state:
        st.info("Commence par analyser une note dans l'onglet 1.")
    else:
        need = CommercialNeed.model_validate(st.session_state["need_json"])
        st.subheader("Besoin structuré")
        a,b,c,d = st.columns(4)
        a.metric("Client", need.client.nom or "À confirmer")
        b.metric("Site", need.client.site or "À confirmer")
        c.metric("Date cible", need.date_cible or "À confirmer")
        d.metric("Nb. besoins", len(need.besoins))

        with st.expander("Voir le JSON extrait"):
            st.json(need.model_dump(mode="json"))

        st.subheader("Correspondances catalogue")
        for i, item in enumerate(need.besoins, 1):
            st.markdown(f"**{i}. {item.description_client}**")
            cols = st.columns(2)
            for j, target in enumerate(["standard","premium"]):
                product, candidates = select_variant(item, target)
                with cols[j]:
                    st.markdown(f"**Variante {target}**")
                    if product:
                        st.success(f"{product['reference']} — {product['nom']}")
                        st.write(
                            f"{product['description']} · **{money(float(product['prix_vente_ht']))} HT** "
                            f"· stock catalogue : **{int(product['stock'])}**"
                        )
                        st.caption("Match : " + ", ".join(product["raisons"]))
                        with st.expander("Voir les 3 candidats"):
                            df = pd.DataFrame([{
                                "Référence": x["reference"],
                                "Désignation": x["nom"],
                                "Gamme": x["gamme"],
                                "Prix HT": x["prix_vente_ht"],
                                "Stock": int(x["stock"]),
                                "Score": x["score"],
                            } for x in candidates])
                            st.dataframe(df, use_container_width=True, hide_index=True)
                    else:
                        st.error("Aucun produit certain trouvé.")

        variants = [build_variant(need, "standard"), build_variant(need, "premium")]
        st.session_state["variants"] = variants

        questions = missing_questions(need, variants)
        st.subheader("Questions / validations restantes")
        if questions:
            for q in questions:
                st.warning(q, icon="⚠️")
        else:
            st.success("Aucune information critique manquante détectée.")

        with st.expander("Traçabilité"):
            st.markdown(
                "- **Demande / quantités / contraintes** : note commerciale, interprétée par l'IA.\n"
                "- **Références / prix / stock** : `catalogue.csv`.\n"
                "- **Remises / livraison / installation / validité** : `regles_tarifaires.csv`.\n"
                "- **Envoi client** : jamais automatique dans ce prototype."
            )

with tab3:
    if "need_json" not in st.session_state:
        st.info("Analyse d'abord une note.")
    else:
        need = CommercialNeed.model_validate(st.session_state["need_json"])
        variants = st.session_state.get("variants") or [build_variant(need, "standard"), build_variant(need, "premium")]

        for variant in variants:
            st.subheader(f"Variante {variant['gamme'].capitalize()}")
            if not variant["lignes"]:
                st.error("Impossible de produire cette variante avec les données actuelles.")
                continue

            df = pd.DataFrame([{
                "Référence": l["reference"],
                "Désignation": l["designation"],
                "Qté": l["quantite"],
                "PU catalogue HT": money(l["prix_catalogue"]),
                "Remise": f"{l['remise_pct']:.0f}%",
                "PU net HT": money(l["prix_unitaire_net"]),
                "Total HT": money(l["total_ht"]),
                "Stock catalogue": l["stock_catalogue"],
            } for l in variant["lignes"]])
            st.dataframe(df, use_container_width=True, hide_index=True)

            c1,c2,c3 = st.columns(3)
            c1.metric("Produits + services HT", money(variant["total_ht"]))
            c2.metric("Livraison", money(variant["livraison_ht"]))
            c3.metric("Installation", money(variant["installation_ht"]))

            for w in variant["warnings"]:
                st.warning(w)

            approved = st.checkbox(
                f"Je valide humainement la variante {variant['gamme']}",
                key=f"approve_{variant['gamme']}"
            )
            html = quote_html(need, variant)

            st.download_button(
                "Télécharger le brouillon de devis (HTML)",
                data=html,
                file_name=f"devis_proxima_{variant['gamme']}.html",
                mime="text/html",
                disabled=not approved,
                key=f"download_{variant['gamme']}"
            )
            if not approved:
                st.caption("Le téléchargement final est verrouillé tant que la validation humaine n'est pas cochée.")
            st.divider()

        trace = {
            "note_source": st.session_state.get("source_note"),
            "besoin_structure": need.model_dump(mode="json"),
            "variantes": variants,
            "regles_tarifaires": rules,
        }
        st.download_button(
            "Télécharger la trace complète (JSON)",
            data=json.dumps(trace, ensure_ascii=False, indent=2),
            file_name="trace_proxima_quote_ai.json",
            mime="application/json"
        )

st.caption(
    "MVP pédagogique : aucune disponibilité réelle Proxima n'est interrogée. "
    "Le catalogue et les règles sont simulés et doivent être remplacés par les systèmes réels en production."
)
