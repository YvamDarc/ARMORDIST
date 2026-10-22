"""State, OCR, editable entries and exports; independent of Streamlit."""
import copy
import hashlib
import io
import json
import re
import zipfile
from datetime import date, datetime
from decimal import Decimal
import pdfplumber
from converter import DEFAULTS, FIELDS, parse_pdf, parse_invoice, entries, invoice_entries, fec_bytes, zip_bytes, money

COLS = ['CompteNum','CompteLib','Debit','Credit']
BUY = {'0.00':'607000','2.10':'607021','5.50':'607055','10.00':'607100','20.00':'607200'}

def blank_row(account='', label=''):
    return dict(zip(COLS, [account,label,'0,00','0,00']))

def new_doc(name, data):
    key=hashlib.sha256(data).hexdigest()
    return {'id':key,'name':name,'pdf':data,'date':date.today().isoformat(),'ref':'PIECE-'+key[:10], 'journal':'HA','rows':[], 'selected':True,'validated':False,'message':'À traiter ou à saisir','ocr_text':'','revision':0,'origin':'Manuel'}

def set_rows(doc, rows):
    doc['rows'] = [{k:str(r.get(k,'') or '') for k in COLS} for r in rows]
    doc['revision']+=1
    doc['validated']=False

def edited_rows(base, delta):
    rows=copy.deepcopy(base)
    for index, changes in delta.get('edited_rows',{}).items():
        for k,v in changes.items():
            if k in COLS: rows[int(index)][k]='' if v is None else str(v)
    rows=[r for i,r in enumerate(rows) if i not in delta.get('deleted_rows',[])]
    for r in delta.get('added_rows',[]):
        rows.append({k:str(r.get(k,'') or '') for k in COLS})
    return rows

def read_text(data):
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        return '\n'.join(p.extract_text() or '' for p in pdf.pages)

def ocr_pdf(data):
    import pypdfium2 as pdfium
    import pytesseract
    from pypdf import PdfReader, PdfWriter
    available=pytesseract.get_languages(config='')
    lang='fra+eng' if 'fra' in available and 'eng' in available else ('fra' if 'fra' in available else 'eng')
    source=pdfium.PdfDocument(data)
    writer=PdfWriter(); texts=[]
    try:
        for i in range(len(source)):
            page=source[i]
            bitmap=page.render(scale=300/72)
            im=bitmap.to_pil()
            try:
                raw=pytesseract.image_to_pdf_or_hocr(im,extension='pdf',lang=lang,config='--psm 6',timeout=90)
                reader=PdfReader(io.BytesIO(raw))
                for p in reader.pages:writer.add_page(p)
                texts.append(read_text(raw))
            finally:
                im.close();bitmap.close();page.close()
    finally:source.close()
    out=io.BytesIO();writer.write(out)
    return out.getvalue(),'\n'.join(texts)

def process(doc, settings, force_ocr=False, auto_ocr=True):
    """Create a proposal without destroying an existing entry on failure."""
    original=doc['pdf']; working=original; text=read_text(original)
    used_ocr=False
    if force_ocr or (auto_ocr and len(text.strip())<50):
        working,text=ocr_pdf(original);used_ocr=True
        doc['ocr_text']=text
    if 'Relevé de presse du' in text:
        p=parse_pdf(working)
        extras=p['extras']
        # Temporary accounts only allow generation; blank them immediately for user assignment.
        for x in extras:x['Compte']='471'
        result=entries(p['date'],p['ref'],1,p['values'],settings['accounts'],extras)
        if extras:
            for r in result[-len(extras):]:r['CompteNum']=''
        journal='PR'
        message='Compte à renseigner pour les opérations complémentaires.' if extras else 'Lecture rapprochée avec le relevé.'
    else:
        p=parse_invoice(working)
        result=invoice_entries(p,1,settings['packaging'],settings['purchases'],settings['vat'],settings['accounts'][5][0])
        journal='HA';message='Articles et TVA rapprochés. Vérifiez les affectations proposées.'
    doc.update(date=p['date'].isoformat(),ref=p['ref'],journal=journal,message=message,origin='OCR' if used_ocr else 'PDF texte')
    set_rows(doc,result)

def template(name,settings):
    if name=='Presse':return [blank_row(a,l) for a,l in settings['accounts']]
    if name=='Écriture libre':return [blank_row(),blank_row()]
    purchase=settings['packaging'] if name=='Consignes' else settings['purchases']['20.00']
    rows=[blank_row(purchase,'EMBALLAGES' if name=='Consignes' else 'ACHATS'),blank_row(settings['vat']['20.00'],'TVA DEDUCTIBLE'),blank_row(settings['accounts'][5][0],'HORS PRESSE')]
    return rows

def check(doc):
    errors=[];debit=Decimal(0);credit=Decimal(0)
    try:datetime.strptime(doc['date'],'%Y-%m-%d')
    except (ValueError,TypeError):errors.append('Date invalide')
    if not re.fullmatch(r'[A-Za-z0-9_-]+',doc['ref']):errors.append('Référence invalide')
    if not re.fullmatch(r'[A-Za-z0-9]+',doc['journal']):errors.append('Journal invalide')
    if not doc['rows']:errors.append('Écriture vide')
    for i,r in enumerate(doc['rows'],1):
        if not re.fullmatch(r'[A-Za-z0-9]+',r['CompteNum'].strip()):errors.append(f'Ligne {i} : compte manquant ou invalide')
        try:
            d=money(r['Debit'] or '0');c=money(r['Credit'] or '0')
            if not d.is_finite() or not c.is_finite() or d<0 or c<0 or (d and c):raise ValueError()
            debit+=d;credit+=c
        except Exception:errors.append(f'Ligne {i} : montant invalide (positif, un seul sens)')
    if debit!=credit:errors.append(f'Écart : {debit-credit:.2f} €')
    if not debit and not credit:errors.append('Aucun montant saisi')
    return errors,debit,credit

def export_bundle(docs,start=1,validated_only=False):
    included=[];excluded=[];refs={};rows=[];pj={}
    candidates=[d for d in docs.values() if d['selected']]
    for d in candidates:refs[d['ref']]=refs.get(d['ref'],0)+1
    for d in docs.values():
        errors,debit,credit=check(d)
        if not d['selected']:errors=['Non sélectionnée']
        elif refs.get(d['ref'],0)>1:errors+=['Référence en double']
        elif validated_only and not d['validated']:errors+=['Non validée']
        if errors:
            excluded.append({'Pièce':d['name'],'Motif':'; '.join(errors)})
            continue
        num=start+len(included);day=d['date'].replace('-','')
        for r in d['rows']:
            line=dict.fromkeys(FIELDS,'')
            line.update(JournalCode=d['journal'],JournalLib={'HA':'ACHATS','PR':'PRESSE'}.get(d['journal'],d['journal']),EcritureNum=str(num),EcritureDate=day,CompteNum=r['CompteNum'].strip(),CompteLib=r['CompteLib'],PieceRef=d['ref'],PieceDate=day,EcritureLib=d['ref']+' - '+r['CompteLib'],Debit=format(money(r['Debit'] or '0'),'.2f').replace('.',','),Credit=format(money(r['Credit'] or '0'),'.2f').replace('.',','))
            rows.append(line)
        pj[d['ref']+'.pdf']=d['pdf']
        included.append({'Pièce':d['name'],'Référence':d['ref'],'Journal':d['journal'],'Débit':str(debit),'Crédit':str(credit),'Validée':d['validated']})
    if not rows:return None,included,excluded
    report=json.dumps({'incluses':included,'exclues':excluded},ensure_ascii=False,indent=2).encode()
    pack=zip_bytes({'ECRITURES.txt':fec_bytes(rows),'PJ.zip':zip_bytes(pj),'CONTROLE.json':report,'LIRE_MOI.txt':'Importer ECRITURES.txt puis joindre PJ.zip dans Pennylane. PDF originaux nommés selon PieceRef. Fichier partiel au format FEC. Les pièces exclues sont détaillées dans CONTROLE.json.'.encode()})
    return pack,included,excluded

def save_project(docs,settings):
    records=[];files={}
    for d in docs.values():
        row={k:v for k,v in d.items() if k!='pdf'}
        row['pdf_path']='documents/'+d['id']+'.pdf'
        files[row['pdf_path']]=d['pdf'];records.append(row)
    files['projet.json']=json.dumps({'version':1,'documents':records,'settings':settings},ensure_ascii=False).encode()
    return zip_bytes(files)

def load_project(data):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        if sum(x.file_size for x in z.infolist())>500_000_000:raise ValueError('Sauvegarde trop volumineuse')
        obj=json.loads(z.read('projet.json'))
        if obj.get('version')!=1:raise ValueError('Version de sauvegarde non reconnue')
        docs={}
        for record in obj['documents']:
            raw=z.read(record['pdf_path']);doc=new_doc(record['name'],raw)
            if doc['id']!=record['id']:raise ValueError('PDF différent de la sauvegarde')
            for key in ['date','ref','journal','message','ocr_text','origin']:
                if not isinstance(record[key],str):raise ValueError('Sauvegarde invalide')
                doc[key]=record[key]
            set_rows(doc,record['rows'])
            doc['selected']=bool(record['selected']);doc['validated']=bool(record['validated'])
            check(doc);docs[doc['id']]=doc
        return docs,obj['settings']
