from io import BytesIO
from datetime import date, timedelta

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
)

NAVY = colors.HexColor("#0A0F2C")
BLUE = colors.HexColor("#2563EB")
PURPLE = colors.HexColor("#7C3AED")
LIGHT = colors.HexColor("#F4F7FB")
BORDER = colors.HexColor("#E3E8F0")
MUTED = colors.HexColor("#667085")


def _money(x):
    s = f"{float(x):,.2f}".replace(",", " ").replace(".", ",")
    return f"{s} EUR"


def build_quote_pdf(meta, variant, seller_company="Entreprise vendeuse", tva_pct=20.0, validity_days=30, human_notes=""):
    """Return the final client quote as PDF bytes."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title="Devis commercial Quotexia",
        author="Quotexia",
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="QXTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=23,
        textColor=NAVY,
        spaceAfter=3,
    ))
    styles.add(ParagraphStyle(
        name="QXDoc",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=10,
        textColor=BLUE,
        alignment=TA_RIGHT,
    ))
    styles.add(ParagraphStyle(
        name="QXSmall",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        textColor=MUTED,
    ))
    styles.add(ParagraphStyle(
        name="QXBody",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor("#111827"),
    ))
    styles.add(ParagraphStyle(
        name="QXSection",
        parent=styles["Heading3"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        textColor=NAVY,
        spaceBefore=7,
        spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        name="QXTotal",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=11.5,
        leading=14,
        textColor=NAVY,
        alignment=TA_RIGHT,
    ))

    story = []

    # Header: seller company issues the quote. The buyer remains in the client information table.
    seller_name = (seller_company or "Entreprise vendeuse").upper()
    header = Table([
        [Paragraph(seller_name, styles["QXTitle"]),
         Paragraph("DEVIS COMMERCIAL", styles["QXDoc"])]
    ], colWidths=[122 * mm, 48 * mm])
    header.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "BOTTOM"),
        ("LINEBELOW", (0,0), (-1,-1), 2.2, NAVY),
        ("BOTTOMPADDING", (0,0), (-1,-1), 8),
    ]))
    story += [header, Spacer(1, 8 * mm)]

    # Client meta
    meta_rows = [
        ["Entreprise vendeuse", seller_company or "Entreprise vendeuse"],
        ["Client", meta.get("client_nom") or "A confirmer"],
        ["Contact", meta.get("contact") or "A confirmer"],
        ["Site", meta.get("site") or "A confirmer"],
        ["Adresse", meta.get("adresse") or "A confirmer"],
        ["Date cible", meta.get("date_cible") or "A confirmer"],
        ["Variante", str(variant.get("gamme", "")).capitalize()],
    ]
    meta_table = Table(meta_rows, colWidths=[34 * mm, 136 * mm])
    meta_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), LIGHT),
        ("BOX", (0,0), (-1,-1), 0.7, BORDER),
        ("INNERGRID", (0,0), (-1,-1), 0.35, BORDER),
        ("FONTNAME", (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTNAME", (1,0), (1,-1), "Helvetica"),
        ("FONTSIZE", (0,0), (-1,-1), 9),
        ("TEXTCOLOR", (0,0), (-1,-1), colors.HexColor("#111827")),
        ("LEFTPADDING", (0,0), (-1,-1), 7),
        ("RIGHTPADDING", (0,0), (-1,-1), 7),
        ("TOPPADDING", (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
    ]))
    story += [meta_table, Spacer(1, 7 * mm)]

    # Quote lines
    data = [["Reference", "Designation", "Qte", "PU net HT", "Total HT"]]
    for line in variant.get("lignes", []):
        data.append([
            str(line["reference"]),
            str(line["designation"]),
            str(line["quantite"]),
            _money(line["prix_unitaire_net"]),
            _money(line["total_ht"]),
        ])

    items = Table(data, colWidths=[29*mm, 63*mm, 15*mm, 31*mm, 32*mm], repeatRows=1)
    items.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), NAVY),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTNAME", (0,1), (-1,-1), "Helvetica"),
        ("FONTSIZE", (0,0), (-1,-1), 8.5),
        ("ALIGN", (2,1), (-1,-1), "RIGHT"),
        ("GRID", (0,0), (-1,-1), 0.45, BORDER),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#FAFBFD")]),
        ("LEFTPADDING", (0,0), (-1,-1), 5),
        ("RIGHTPADDING", (0,0), (-1,-1), 5),
        ("TOPPADDING", (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
    ]))
    story += [items, Spacer(1, 6 * mm)]

    delivery_txt = "Incluse" if meta.get("livraison") else "Non incluse"
    install_txt = "Incluse" if meta.get("installation") else "Non incluse"
    service = Paragraph(
        f"<b>Livraison :</b> {delivery_txt} - {_money(variant.get('livraison_ht', 0))}<br/>"
        f"<b>Installation :</b> {install_txt} - {_money(variant.get('installation_ht', 0))}",
        styles["QXBody"]
    )
    story += [service, Spacer(1, 5 * mm)]

    total_ht = float(variant.get("total_ht", 0))
    tva_amount = total_ht * float(tva_pct) / 100
    total_ttc = total_ht + tva_amount

    totals = Table([
        ["Total HT", _money(total_ht)],
        [f"TVA ({float(tva_pct):.0f} %)", _money(tva_amount)],
        ["TOTAL TTC", _money(total_ttc)],
    ], colWidths=[42 * mm, 40 * mm], hAlign="RIGHT")
    totals.setStyle(TableStyle([
        ("FONTNAME", (0,0), (-1,1), "Helvetica"),
        ("FONTNAME", (0,2), (-1,2), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,1), 9.5),
        ("FONTSIZE", (0,2), (-1,2), 12),
        ("TEXTCOLOR", (0,0), (-1,-1), NAVY),
        ("ALIGN", (1,0), (1,-1), "RIGHT"),
        ("LINEABOVE", (0,2), (-1,2), 1.5, NAVY),
        ("TOPPADDING", (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ]))
    story += [totals]

    # Only keep completed notes
    notes = []
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
        notes.append(visible)

    if notes:
        story += [Spacer(1, 6 * mm), Paragraph("Informations complementaires", styles["QXSection"])]
        for note in notes:
            story.append(Paragraph(f"- {note}", styles["QXBody"]))

    # Client-safe warnings only
    client_warnings = []
    for w in variant.get("warnings", []):
        wl = str(w).lower()
        if "stock catalogue" in wl or "disponibil" in wl:
            client_warnings.append("Disponibilite a confirmer pour une ou plusieurs references.")
        elif "marge" in wl:
            continue
        elif "reference" in wl:
            client_warnings.append("Une ou plusieurs references restent a confirmer.")

    client_warnings = list(dict.fromkeys(client_warnings))
    if client_warnings:
        story += [Spacer(1, 6 * mm), Paragraph("Points a confirmer", styles["QXSection"])]
        warn_data = [[Paragraph("<br/>".join(f"- {w}" for w in client_warnings), styles["QXBody"])]]
        warn = Table(warn_data, colWidths=[170 * mm])
        warn.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#FFF7D6")),
            ("BOX", (0,0), (-1,-1), 0.6, colors.HexColor("#F59E0B")),
            ("LEFTPADDING", (0,0), (-1,-1), 9),
            ("RIGHTPADDING", (0,0), (-1,-1), 9),
            ("TOPPADDING", (0,0), (-1,-1), 8),
            ("BOTTOMPADDING", (0,0), (-1,-1), 8),
        ]))
        story.append(warn)

    end_date = date.today() + timedelta(days=int(validity_days))
    story += [
        Spacer(1, 8 * mm),
        Paragraph(
            f"Validite de l'offre : {int(validity_days)} jours (jusqu'au {end_date.strftime('%d/%m/%Y')}).",
            styles["QXSmall"]
        )
    ]

    doc.build(story)
    return buffer.getvalue()
