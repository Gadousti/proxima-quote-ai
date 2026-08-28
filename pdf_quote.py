from io import BytesIO
from datetime import date, timedelta
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

NAVY=colors.HexColor('#0A0F2C')
BLUE=colors.HexColor('#2563EB')
LIGHT=colors.HexColor('#F7F9FC')
LINE=colors.HexColor('#E3E8F0')
MUTED=colors.HexColor('#667085')

def money(v):
    return f"{float(v):,.2f} €".replace(',', ' ').replace('.', ',')

def build_quote_pdf(meta, variant, seller_company='Proxima Équipement', tva_pct=20.0, validity_days=30, human_notes=''):
    buf=BytesIO()
    doc=SimpleDocTemplate(buf,pagesize=A4,rightMargin=18*mm,leftMargin=18*mm,topMargin=18*mm,bottomMargin=18*mm,
                          title=f'Devis commercial - {seller_company}', author=seller_company)
    styles=getSampleStyleSheet()
    seller=ParagraphStyle('seller',parent=styles['Heading1'],fontName='Helvetica-Bold',fontSize=21,leading=24,textColor=NAVY,spaceAfter=2)
    docstyle=ParagraphStyle('doc',parent=styles['Normal'],fontName='Helvetica-Bold',fontSize=10,textColor=BLUE,alignment=TA_RIGHT)
    h2=ParagraphStyle('h2',parent=styles['Heading2'],fontName='Helvetica-Bold',fontSize=12,textColor=NAVY,spaceBefore=8,spaceAfter=6)
    normal=ParagraphStyle('normal',parent=styles['BodyText'],fontName='Helvetica',fontSize=9.5,leading=13,textColor=colors.HexColor('#111827'))
    story=[]
    header=Table([[Paragraph((seller_company or 'Proxima Équipement').upper(),seller),Paragraph('DEVIS COMMERCIAL',docstyle)]],colWidths=[120*mm,50*mm])
    header.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LINEBELOW',(0,0),(-1,-1),2,NAVY),('BOTTOMPADDING',(0,0),(-1,-1),8)]))
    story += [header,Spacer(1,8*mm)]
    meta_rows=[
        ['Entreprise vendeuse', seller_company or 'Proxima Équipement'],
        ['Client', meta.get('client_nom') or 'À confirmer'],
        ['Contact', meta.get('contact') or 'À confirmer'],
        ['Site', meta.get('site') or 'À confirmer'],
        ['Adresse', meta.get('adresse') or 'À confirmer'],
        ['Date cible', meta.get('date_cible') or 'À confirmer'],
        ['Variante', str(variant.get('gamme','standard')).capitalize()],
    ]
    mt=Table(meta_rows,colWidths=[45*mm,125*mm])
    mt.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),LIGHT),('TEXTCOLOR',(0,0),(0,-1),NAVY),('FONTNAME',(0,0),(0,-1),'Helvetica-Bold'),('FONTNAME',(1,0),(1,-1),'Helvetica'),('FONTSIZE',(0,0),(-1,-1),9),('GRID',(0,0),(-1,-1),0.4,LINE),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
    story += [mt,Spacer(1,7*mm)]
    rows=[['Référence','Désignation','Qté','PU net HT','Total HT']]
    for l in variant.get('lignes',[]):
        rows.append([str(l.get('reference','')),str(l.get('designation','')),str(l.get('quantite','')),money(l.get('prix_unitaire_net',0)),money(l.get('total_ht',0))])
    t=Table(rows,colWidths=[27*mm,68*mm,16*mm,29*mm,30*mm],repeatRows=1)
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),NAVY),('TEXTCOLOR',(0,0),(-1,0),colors.white),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTNAME',(0,1),(-1,-1),'Helvetica'),('FONTSIZE',(0,0),(-1,-1),8.7),('GRID',(0,0),(-1,-1),0.35,LINE),('VALIGN',(0,0),(-1,-1),'TOP'),('ALIGN',(2,1),(-1,-1),'RIGHT'),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
    story += [t,Spacer(1,5*mm)]
    total_ht=float(variant.get('total_ht',0)); tax=total_ht*float(tva_pct)/100; ttc=total_ht+tax
    services=[['Livraison HT',money(variant.get('livraison_ht',0))],['Installation HT',money(variant.get('installation_ht',0))],['TOTAL HT',money(total_ht)],[f'TVA ({float(tva_pct):.0f} %)',money(tax)],['TOTAL TTC',money(ttc)]]
    totals=Table(services,colWidths=[45*mm,35*mm],hAlign='RIGHT')
    totals.setStyle(TableStyle([('FONTNAME',(0,0),(-1,-1),'Helvetica'),('FONTNAME',(0,2),(-1,-1),'Helvetica-Bold'),('TEXTCOLOR',(0,2),(-1,-1),NAVY),('ALIGN',(1,0),(-1,-1),'RIGHT'),('LINEABOVE',(0,4),(-1,4),1.5,NAVY),('FONTSIZE',(0,0),(-1,-1),9.5),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4)]))
    story += [totals,Spacer(1,7*mm)]
    if human_notes and human_notes.strip():
        story += [Paragraph('Notes commerciales',h2),Paragraph(human_notes.replace('\n','<br/>'),normal),Spacer(1,4*mm)]
    end=(date.today()+timedelta(days=int(validity_days))).strftime('%d/%m/%Y')
    story.append(Paragraph(f'Validité du devis : {int(validity_days)} jours, soit jusqu’au {end}.',normal))
    doc.build(story)
    return buf.getvalue()
