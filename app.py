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

st.set_page_config(page_title="Quotexia", page_icon="⚡", layout="wide")

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

def tax_totals(total_ht):
    tva_pct = float(rules.get("tva_pct", 20))
    tva_amount = float(total_ht) * tva_pct / 100
    total_ttc = float(total_ht) + tva_amount
    return tva_pct, tva_amount, total_ttc

def quote_html(need_obj, variant):
    today = date.today()
    validity = int(rules["validite_devis_jours"])
    tva_pct, tva_amount, total_ttc = tax_totals(variant["total_ht"])

    lines_html = ""
    for l in variant["lignes"]:
        lines_html += f"""
        <tr>
          <td>{l['reference']}</td>
          <td>{l['designation']}</td>
          <td>{l['quantite']}</td>
          <td>{money(l['prix_unitaire_net'])}</td>
          <td>{money(l['total_ht'])}</td>
        </tr>"""

    return f"""<!doctype html>
<html lang="fr"><meta charset="utf-8">
<title>Brouillon de devis commercial</title>
<style>
body{{font-family:Inter,Arial,sans-serif;max-width:960px;margin:40px auto;color:#111827}}
h1{{margin-bottom:4px;color:#0A0F2C}}
.muted{{color:#667085}}
.warning{{background:#FFF7D6;padding:12px;border-radius:10px}}
table{{width:100%;border-collapse:collapse;margin:20px 0}}
th,td{{border:1px solid #E3E8F0;padding:9px;text-align:left}}
th{{background:#F2F5FA;color:#0A0F2C}}
.totals{{margin-left:auto;width:340px;margin-top:24px}}
.totals div{{display:flex;justify-content:space-between;padding:7px 0}}
.ttc{{font-size:1.25rem;font-weight:bold;border-top:2px solid #0A0F2C;margin-top:4px;padding-top:10px!important}}
</style>
<h1>{(need_obj.client.nom or 'CLIENT').upper()}</h1>
<div class="muted">BROUILLON DE DEVIS — VALIDATION HUMAINE REQUISE</div>
<p>
<b>Client :</b> {need_obj.client.nom or "À confirmer"}<br>
<b>Site :</b> {need_obj.client.adresse or need_obj.client.site or "À confirmer"}<br>
<b>Contact :</b> {need_obj.client.contact or "À confirmer"}<br>
<b>Date cible :</b> {need_obj.date_cible or "À confirmer"}<br>
<b>Variante :</b> {variant['gamme'].capitalize()}
</p>
<table>
<thead><tr><th>Référence</th><th>Désignation</th><th>Qté</th><th>PU net HT</th><th>Total HT</th></tr></thead>
<tbody>{lines_html}</tbody>
</table>
<p>Livraison : {money(variant['livraison_ht'])}<br>
Installation : {money(variant['installation_ht'])}</p>
<div class="totals">
  <div><span>Total HT</span><b>{money(variant['total_ht'])}</b></div>
  <div><span>TVA ({tva_pct:.0f} %)</span><b>{money(tva_amount)}</b></div>
  <div class="ttc"><span>Total TTC</span><b>{money(total_ttc)}</b></div>
</div>
<p>Validité de l'offre : {validity} jours (jusqu'au {(today+timedelta(days=validity)).strftime("%d/%m/%Y")}).</p>
<div class="warning"><b>Important :</b> ceci est un brouillon. Aucune référence, disponibilité ou remise hors cadre
ne doit être envoyée au client sans validation humaine.</div>
</html>"""


def recalc_edited_variant(original_variant, edited_lines, delivery_enabled, installation_enabled):
    """Recalcule le devis à partir des corrections humaines, sans laisser l'IA fabriquer prix/références."""
    result_lines = []
    warnings = []

    for edited in edited_lines:
        ref = edited["reference"]
        qty = int(edited["quantite"])
        discount_pct = float(edited["remise_pct"])

        matches = catalog[catalog["reference"] == ref]
        if matches.empty:
            warnings.append(f"Référence {ref} introuvable dans le catalogue : ligne bloquée.")
            continue

        product = matches.iloc[0]
        unit_price = float(product["prix_vente_ht"])
        cost = float(product["prix_achat_ht"])
        stock = int(product["stock"])
        discount_pct = min(max(discount_pct, 0.0), rules["remise_max_commercial_pct"])
        net_unit = unit_price * (1 - discount_pct / 100)
        total = net_unit * qty
        margin_pct = ((net_unit - cost) / net_unit * 100) if net_unit else 0.0

        if stock < qty:
            warnings.append(
                f"{ref} : stock catalogue {stock}, quantité finale {qty}. "
                "Disponibilité à confirmer avant envoi."
            )
        if margin_pct < rules["marge_minimale_pct"]:
            warnings.append(
                f"{ref} : marge finale {margin_pct:.1f}% sous le minimum "
                f"{rules['marge_minimale_pct']:.0f}%. Validation managériale requise."
            )

        result_lines.append({
            "reference": ref,
            "designation": str(product["nom"]),
            "categorie": str(product["categorie"]),
            "quantite": qty,
            "prix_catalogue": unit_price,
            "remise_pct": discount_pct,
            "prix_unitaire_net": net_unit,
            "total_ht": total,
            "stock_catalogue": stock,
            "marge_pct": margin_pct,
            "source_reference": "catalogue.csv",
            "source_prix": "catalogue.csv",
            "source_quantite": "correction humaine",
            "source_remise": "correction humaine / règles tarifaires",
        })

    delivery = rules["livraison_standard_ht"] if delivery_enabled else 0.0
    install_qty = sum(l["quantite"] for l in result_lines)
    installation = rules["installation_unitaire_ht"] * install_qty if installation_enabled else 0.0

    return {
        "gamme": original_variant["gamme"],
        "lignes": result_lines,
        "livraison_ht": delivery,
        "installation_ht": installation,
        "total_ht": sum(l["total_ht"] for l in result_lines) + delivery + installation,
        "warnings": warnings,
    }


def final_quote_html(meta, variant, human_notes="", modifications=None):
    """
    Devis CLIENT uniquement.
    Aucune traçabilité interne, aucune ancienne valeur, aucun statut technique.
    """
    today = date.today()
    validity = int(rules["validite_devis_jours"])
    tva_pct, tva_amount, total_ttc = tax_totals(variant["total_ht"])

    lines_html = ""
    for l in variant["lignes"]:
        lines_html += f"""
        <tr>
          <td>{l['reference']}</td>
          <td>{l['designation']}</td>
          <td>{l['quantite']}</td>
          <td>{money(l['prix_unitaire_net'])}</td>
          <td>{money(l['total_ht'])}</td>
        </tr>"""

    cleaned_notes = []
    for raw in (human_notes or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        visible = line[1:].strip() if line.startswith("-") else line
        if visible.endswith(":"):
            continue
        if ":" in visible:
            _, answer = visible.split(":", 1)
            if not answer.strip():
                continue
        cleaned_notes.append(visible)

    notes_html = ""
    if cleaned_notes:
        notes_html = "<ul>" + "".join(f"<li>{n}</li>" for n in cleaned_notes) + "</ul>"

    client_warnings = []
    for w in variant.get("warnings", []):
        wl = w.lower()
        if "stock catalogue" in wl or "disponibilité" in wl:
            client_warnings.append("Disponibilité à confirmer pour une ou plusieurs références.")
        elif "marge" in wl:
            continue
        elif "référence" in wl:
            client_warnings.append("Une ou plusieurs références restent à confirmer.")

    client_warnings = list(dict.fromkeys(client_warnings))
    warnings_html = ""
    if client_warnings:
        warnings_html = "<ul>" + "".join(f"<li>{w}</li>" for w in client_warnings) + "</ul>"

    livraison_txt = "Incluse" if meta.get("livraison") else "Non incluse"
    installation_txt = "Incluse" if meta.get("installation") else "Non incluse"

    return f"""<!doctype html>
<html lang="fr">
<meta charset="utf-8">
<title>Devis commercial</title>
<style>
:root{{
  --navy:#0A0F2C;
  --blue:#2563EB;
  --purple:#7C3AED;
  --line:#E3E8F0;
  --muted:#667085;
}}
body{{font-family:Inter,Arial,sans-serif;max-width:960px;margin:40px auto;color:#111827}}
.header{{display:flex;align-items:center;justify-content:space-between;border-bottom:3px solid var(--navy);padding-bottom:16px}}
.client-title{{font-size:32px;font-weight:850;color:var(--navy);letter-spacing:-0.6px}}
.doc-label{{font-size:13px;font-weight:800;letter-spacing:1.7px;color:var(--blue)}}
.meta{{background:#F7F9FC;border:1px solid var(--line);border-radius:14px;padding:18px;margin-top:22px;line-height:1.7}}
table{{width:100%;border-collapse:collapse;margin:24px 0}}
th,td{{border-bottom:1px solid var(--line);padding:11px 9px;text-align:left}}
th{{background:#0A0F2C;color:white;font-size:13px}}
th:first-child{{border-radius:8px 0 0 8px}}
th:last-child{{border-radius:0 8px 8px 0}}
.service{{color:var(--muted);line-height:1.7}}
.totals{{margin-left:auto;width:360px;margin-top:24px}}
.totals div{{display:flex;justify-content:space-between;padding:8px 0}}
.totals .ht{{color:#344054}}
.totals .tax{{color:#475467}}
.totals .ttc{{font-size:1.3rem;font-weight:850;color:var(--navy);border-top:2px solid var(--navy);margin-top:5px;padding-top:12px}}
.section{{margin-top:30px}}
.section h3{{color:var(--navy);font-size:17px}}
.warning{{background:#FFF7D6;border-left:4px solid #F59E0B;padding:13px 16px;border-radius:10px}}
.footer{{margin-top:34px;padding-top:16px;border-top:1px solid var(--line);color:var(--muted);font-size:13px}}
</style>

<div class="header">
  <div class="client-title">{(meta.get('client_nom') or 'CLIENT').upper()}</div>
  <div class="doc-label">DEVIS COMMERCIAL</div>
</div>

<div class="meta">
<b>Client :</b> {meta.get('client_nom') or "À confirmer"}<br>
<b>Contact :</b> {meta.get('contact') or "À confirmer"}<br>
<b>Site :</b> {meta.get('site') or "À confirmer"}<br>
<b>Adresse :</b> {meta.get('adresse') or "À confirmer"}<br>
<b>Date cible :</b> {meta.get('date_cible') or "À confirmer"}<br>
<b>Variante :</b> {variant['gamme'].capitalize()}
</div>

<table>
<thead>
<tr>
<th>Référence</th>
<th>Désignation</th>
<th>Qté</th>
<th>PU net HT</th>
<th>Total HT</th>
</tr>
</thead>
<tbody>{lines_html}</tbody>
</table>

<div class="service">
<b>Livraison :</b> {livraison_txt} — {money(variant['livraison_ht'])}<br>
<b>Installation :</b> {installation_txt} — {money(variant['installation_ht'])}
</div>

<div class="totals">
  <div class="ht"><span>Total HT</span><b>{money(variant['total_ht'])}</b></div>
  <div class="tax"><span>TVA ({tva_pct:.0f} %)</span><b>{money(tva_amount)}</b></div>
  <div class="ttc"><span>Total TTC</span><b>{money(total_ttc)}</b></div>
</div>

{"<div class='section'><h3>Informations complémentaires</h3>" + notes_html + "</div>" if notes_html else ""}

{"<div class='warning section'><b>Points à confirmer :</b>" + warnings_html + "</div>" if warnings_html else ""}

<div class="footer">
Validité de l'offre : {validity} jours (jusqu'au {(today+timedelta(days=validity)).strftime("%d/%m/%Y")}).
</div>
</html>"""

def compare_values(field, old, new, modifications):
    old_s = "" if old is None else str(old)
    new_s = "" if new is None else str(new)
    if old_s != new_s:
        modifications.append({
            "champ": field,
            "ancienne_valeur": old_s or "non renseigné",
            "nouvelle_valeur": new_s or "non renseigné",
        })

# ---------------------------
# UI
# ---------------------------
st.markdown("""
<style>
:root {
    --qx-navy: #0A0F2C;
    --qx-blue: #2563EB;
    --qx-purple: #7C3AED;
    --qx-light: #E8EFF0;
    --qx-ink: #111827;
    --qx-muted: #667085;
}

/* App background */
[data-testid="stAppViewContainer"] {
    background:
        radial-gradient(circle at 90% 0%, rgba(124,58,237,0.08), transparent 28%),
        radial-gradient(circle at 12% 5%, rgba(37,99,235,0.08), transparent 25%),
        #F7F9FC;
}
[data-testid="stHeader"] {
    background: rgba(247,249,252,0.88);
}

/* Sidebar */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0A0F2C 0%, #111A3A 100%);
    border-right: 1px solid rgba(255,255,255,0.08);
}
[data-testid="stSidebar"] * {
    color: #F8FAFC;
}
[data-testid="stSidebar"] [data-testid="stMetricValue"] {
    color: #FFFFFF;
}
[data-testid="stSidebar"] input {
    color: #111827 !important;
    background: #FFFFFF !important;
}

/* Main content width */
.block-container {
    max-width: 1180px;
    padding-top: 2.1rem;
    padding-bottom: 3rem;
}

/* Brand hero */
.qx-brand {
    display:flex;
    align-items:center;
    gap:16px;
    margin-bottom:4px;
}
.qx-mark {
    width:54px;
    height:54px;
    border-radius:18px;
    background: linear-gradient(135deg, #2563EB 0%, #7C3AED 100%);
    display:flex;
    align-items:center;
    justify-content:center;
    color:#FFFFFF;
    font-size:31px;
    font-weight:900;
    line-height:1;
    box-shadow: 0 12px 32px rgba(37,99,235,0.22);
}
.qx-name {
    font-size:46px;
    line-height:1;
    font-weight:850;
    letter-spacing:-1.8px;
    color:#0A0F2C;
}
.qx-tagline {
    color:#667085;
    margin: 10px 0 22px 70px;
    font-size:15px;
}

/* Headings */
h1, h2, h3 {
    color:#0A0F2C !important;
    letter-spacing:-0.4px;
}

/* Tabs */
button[data-baseweb="tab"] {
    font-weight:700;
    color:#667085;
}
button[data-baseweb="tab"][aria-selected="true"] {
    color:#2563EB !important;
}
div[data-baseweb="tab-highlight"] {
    background: linear-gradient(90deg,#2563EB,#7C3AED) !important;
}

/* Inputs and upload */
div[data-baseweb="input"] > div,
div[data-baseweb="textarea"] > div,
[data-testid="stFileUploaderDropzone"] {
    border-radius:14px !important;
    border-color:#D7DFEA !important;
    background:#FFFFFF !important;
}
textarea, input {
    border-radius:12px !important;
}

/* Primary button */
.stButton > button[kind="primary"],
.stDownloadButton > button {
    border:0 !important;
    border-radius:12px !important;
    background: linear-gradient(90deg,#2563EB 0%,#7C3AED 100%) !important;
    color:#FFFFFF !important;
    font-weight:750 !important;
    min-height:46px;
}
.stButton > button:not([kind="primary"]) {
    border-radius:12px !important;
    border:1px solid #D7DFEA !important;
    background:#FFFFFF !important;
    color:#0A0F2C !important;
    font-weight:650 !important;
    min-height:46px;
}

/* Cards, expanders, dataframes */
[data-testid="stExpander"],
[data-testid="stDataFrame"],
[data-testid="stMetric"] {
    background:#FFFFFF;
    border:1px solid #E3E8F0;
    border-radius:16px;
}
[data-testid="stMetric"] {
    padding:14px 16px;
}

/* Alerts */
[data-testid="stAlert"] {
    border-radius:14px;
}

/* Divider */
hr {
    border-color:#E5EAF1 !important;
}

/* Mobile */
@media (max-width: 700px) {
    .qx-name { font-size:36px; }
    .qx-mark { width:48px; height:48px; border-radius:15px; }
    .qx-tagline { margin-left:0; }
    .block-container { padding-top:1.2rem; }
}
</style>

<div class="qx-brand">
    <div class="qx-mark">Q</div>
    <div class="qx-name">Quotexia</div>
</div>
<div class="qx-tagline">Prototype scolaire — note commerciale → besoin structuré → catalogue vérifié → brouillon de devis</div>
""", unsafe_allow_html=True)

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
        variants = st.session_state.get("variants") or [
            build_variant(need, "standard"),
            build_variant(need, "premium")
        ]

        st.subheader("✏️ Édition humaine du devis")
        st.caption(
            "Le brouillon généré par l'outil peut être complété ou corrigé par le commercial. "
            "Les références et prix restent obligatoirement issus du catalogue."
        )

        for variant in variants:
            gamme = variant["gamme"]
            st.markdown(f"## Variante {gamme.capitalize()}")

            if not variant["lignes"]:
                st.error("Impossible de produire cette variante avec les données actuelles.")
                st.divider()
                continue

            saved_key = f"edited_quote_{gamme}"
            saved = st.session_state.get(saved_key)

            with st.form(f"edit_form_{gamme}"):
                st.markdown("### 1. Informations client à compléter")
                c1, c2 = st.columns(2)

                with c1:
                    client_nom = st.text_input(
                        "Nom du client",
                        value=(saved["meta"]["client_nom"] if saved else (need.client.nom or "")),
                        key=f"client_nom_{gamme}"
                    )
                    contact = st.text_input(
                        "Contact",
                        value=(saved["meta"]["contact"] if saved else (need.client.contact or "")),
                        key=f"contact_{gamme}"
                    )
                    site = st.text_input(
                        "Site / ville",
                        value=(saved["meta"]["site"] if saved else (need.client.site or "")),
                        key=f"site_{gamme}"
                    )

                with c2:
                    adresse = st.text_input(
                        "Adresse exacte",
                        value=(saved["meta"]["adresse"] if saved else (need.client.adresse or "")),
                        key=f"adresse_{gamme}"
                    )
                    date_cible = st.text_input(
                        "Date cible",
                        value=(saved["meta"]["date_cible"] if saved else (need.date_cible or "")),
                        key=f"date_cible_{gamme}"
                    )
                    livraison_enabled = st.checkbox(
                        "Inclure la livraison",
                        value=(saved["meta"]["livraison"] if saved else (need.livraison is True)),
                        key=f"delivery_{gamme}"
                    )
                    installation_enabled = st.checkbox(
                        "Inclure l'installation",
                        value=(saved["meta"]["installation"] if saved else (need.installation is True)),
                        key=f"installation_{gamme}"
                    )

                st.markdown("### 2. Lignes du devis")

                edited_inputs = []
                for i, line in enumerate(variant["lignes"]):
                    st.markdown(f"**Ligne {i+1} — {line['designation']}**")
                    l1, l2, l3 = st.columns([2.2, 1, 1])

                    # Safe reference choices: original candidate shortlist + current ref
                    refs = [line["reference"]]
                    for cand in line.get("candidats", []):
                        if cand["reference"] not in refs:
                            refs.append(cand["reference"])

                    # If saved, preserve saved reference if valid
                    saved_line = None
                    if saved and i < len(saved["variant"]["lignes"]):
                        saved_line = saved["variant"]["lignes"][i]
                        if saved_line["reference"] not in refs:
                            refs.append(saved_line["reference"])

                    with l1:
                        selected_ref = st.selectbox(
                            "Référence catalogue",
                            options=refs,
                            index=refs.index(saved_line["reference"]) if saved_line else 0,
                            key=f"ref_{gamme}_{i}",
                            help="Seules des références réellement présentes dans le catalogue peuvent être choisies."
                        )
                        row = catalog[catalog["reference"] == selected_ref].iloc[0]
                        st.caption(
                            f"{row['nom']} · {row['description']} · "
                            f"Prix catalogue {money(float(row['prix_vente_ht']))} HT · stock {int(row['stock'])}"
                        )

                    with l2:
                        quantity = st.number_input(
                            "Quantité finale",
                            min_value=1,
                            step=1,
                            value=int(saved_line["quantite"] if saved_line else line["quantite"]),
                            key=f"qty_{gamme}_{i}"
                        )

                    with l3:
                        default_disc = float(saved_line["remise_pct"] if saved_line else line["remise_pct"])
                        discount = st.number_input(
                            "Remise (%)",
                            min_value=0.0,
                            max_value=float(rules["remise_max_commercial_pct"]),
                            step=1.0,
                            value=default_disc,
                            key=f"disc_{gamme}_{i}",
                            help=f"Plafond commercial : {rules['remise_max_commercial_pct']:.0f}%."
                        )

                    edited_inputs.append({
                        "reference": selected_ref,
                        "quantite": int(quantity),
                        "remise_pct": float(discount),
                    })

                st.markdown("### 3. Réponses aux questions / hypothèses")
                default_notes = saved["meta"].get("human_notes", "") if saved else ""
                if not default_notes and need.informations_manquantes:
                    default_notes = "\n".join(f"- {q} : " for q in need.informations_manquantes)

                human_notes = st.text_area(
                    "Notes complétées par le commercial",
                    value=default_notes,
                    height=150,
                    key=f"notes_{gamme}",
                    help="Exemple : adresse confirmée, contrainte d'accès, nom du contact, précision donnée par le client."
                )

                save_clicked = st.form_submit_button(
                    "💾 Enregistrer les corrections humaines",
                    type="primary",
                    use_container_width=True
                )

            if save_clicked:
                edited_variant = recalc_edited_variant(
                    variant,
                    edited_inputs,
                    livraison_enabled,
                    installation_enabled
                )

                meta = {
                    "client_nom": client_nom.strip(),
                    "contact": contact.strip(),
                    "site": site.strip(),
                    "adresse": adresse.strip(),
                    "date_cible": date_cible.strip(),
                    "livraison": bool(livraison_enabled),
                    "installation": bool(installation_enabled),
                    "human_notes": human_notes.strip(),
                }

                modifications = []
                compare_values("Nom du client", need.client.nom, meta["client_nom"], modifications)
                compare_values("Contact", need.client.contact, meta["contact"], modifications)
                compare_values("Site", need.client.site, meta["site"], modifications)
                compare_values("Adresse", need.client.adresse, meta["adresse"], modifications)
                compare_values("Date cible", need.date_cible, meta["date_cible"], modifications)
                compare_values("Livraison", need.livraison, meta["livraison"], modifications)
                compare_values("Installation", need.installation, meta["installation"], modifications)

                for i, (orig, edited) in enumerate(zip(variant["lignes"], edited_variant["lignes"]), 1):
                    compare_values(f"Ligne {i} — référence", orig["reference"], edited["reference"], modifications)
                    compare_values(f"Ligne {i} — quantité", orig["quantite"], edited["quantite"], modifications)
                    compare_values(
                        f"Ligne {i} — remise",
                        f"{orig['remise_pct']:.0f}%",
                        f"{edited['remise_pct']:.0f}%",
                        modifications
                    )

                st.session_state[saved_key] = {
                    "meta": meta,
                    "variant": edited_variant,
                    "modifications": modifications,
                }
                st.success("Corrections humaines enregistrées. Le devis a été recalculé.")

            saved = st.session_state.get(saved_key)

            if saved:
                st.markdown("### 4. Aperçu du devis corrigé")
                edited_variant = saved["variant"]
                meta = saved["meta"]

                preview_df = pd.DataFrame([{
                    "Référence": l["reference"],
                    "Désignation": l["designation"],
                    "Qté finale": l["quantite"],
                    "PU catalogue HT": money(l["prix_catalogue"]),
                    "Remise": f"{l['remise_pct']:.0f}%",
                    "PU net HT": money(l["prix_unitaire_net"]),
                    "Total HT": money(l["total_ht"]),
                    "Source quantité": l["source_quantite"],
                } for l in edited_variant["lignes"]])
                st.dataframe(preview_df, use_container_width=True, hide_index=True)

                tva_pct, tva_amount, total_ttc = tax_totals(edited_variant["total_ht"])
                m1, m2, m3 = st.columns(3)
                m1.metric("Total HT", money(edited_variant["total_ht"]))
                m2.metric(f"TVA ({tva_pct:.0f} %)", money(tva_amount))
                m3.metric("Total TTC", money(total_ttc))

                s1, s2 = st.columns(2)
                s1.metric("Livraison", money(edited_variant["livraison_ht"]))
                s2.metric("Installation", money(edited_variant["installation_ht"]))

                # Remaining critical fields
                still_missing = []
                if not meta["client_nom"]:
                    still_missing.append("Nom du client")
                if not meta["contact"]:
                    still_missing.append("Contact")
                if not meta["adresse"] and not meta["site"]:
                    still_missing.append("Site / adresse")
                if not meta["date_cible"]:
                    still_missing.append("Date cible")

                for w in edited_variant["warnings"]:
                    st.warning(w)

                if still_missing:
                    st.warning(
                        "Informations encore manquantes : " + ", ".join(still_missing) +
                        ". Le commercial peut néanmoins conserver le brouillon, mais la validation finale est bloquée."
                    )

                with st.expander("Voir la traçabilité des corrections humaines"):
                    if saved["modifications"]:
                        for mod in saved["modifications"]:
                            st.write(
                                f"**{mod['champ']}** : {mod['ancienne_valeur']} → "
                                f"{mod['nouvelle_valeur']} · source finale : **correction humaine**"
                            )
                    else:
                        st.write("Aucune modification par rapport au brouillon automatique.")

                final_ok = st.checkbox(
                    f"Je confirme avoir relu et validé humainement la variante {gamme}",
                    key=f"final_approve_{gamme}",
                    disabled=bool(still_missing)
                )

                html = final_quote_html(
                    meta,
                    edited_variant,
                    meta.get("human_notes", ""),
                    saved["modifications"]
                )

                st.download_button(
                    "⬇️ Télécharger le devis final validé (HTML)",
                    data=html,
                    file_name=f"devis_quotexia_{gamme}.html",
                    mime="text/html",
                    disabled=not final_ok,
                    key=f"final_download_{gamme}",
                    use_container_width=True
                )

                if still_missing:
                    st.caption("Complète les champs critiques puis clique de nouveau sur « Enregistrer les corrections humaines ».")
                elif not final_ok:
                    st.caption("Le téléchargement final reste verrouillé jusqu'à la validation humaine.")

            else:
                st.info(
                    "Le devis automatique est encore un brouillon. "
                    "Complète ou corrige les informations ci-dessus puis enregistre les corrections."
                )

            st.divider()

        # Global audit trace includes both AI draft and human corrections
        edited_quotes = {
            v["gamme"]: st.session_state.get(f"edited_quote_{v['gamme']}")
            for v in variants
            if st.session_state.get(f"edited_quote_{v['gamme']}")
        }

        trace = {
            "note_source": st.session_state.get("source_note"),
            "besoin_extrait_par_ia": need.model_dump(mode="json"),
            "brouillons_automatiques": variants,
            "devis_corriges_par_humain": edited_quotes,
            "regles_tarifaires": rules,
        }

        st.download_button(
            "📋 Télécharger la trace complète IA + catalogue + corrections humaines (JSON)",
            data=json.dumps(trace, ensure_ascii=False, indent=2),
            file_name="trace_quotexia_complete.json",
            mime="application/json",
            use_container_width=True
        )

st.caption(
    "MVP pédagogique : aucune disponibilité réelle Proxima n'est interrogée. "
    "Le catalogue et les règles sont simulés et doivent être remplacés par les systèmes réels en production."
)
