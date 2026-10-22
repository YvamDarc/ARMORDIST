import csv
import io
import re
import zipfile
from decimal import Decimal
from datetime import datetime
import pdfplumber

FIELDS = 'JournalCode JournalLib EcritureNum EcritureDate CompteNum CompteLib CompAuxNum CompAuxLib PieceRef PieceDate EcritureLib Debit Credit EcritureLet DateLet ValidDate Montantdevise Idevise'.split()
DEFAULTS = [('401ARMOR0', 'ARMOR DISTRIPRESSE'), ('46761', 'PRESSE'), ('7066', 'COMM PRESSE'), ('401ARMORDIF', 'ARMOR DISTRI DIFFERES'), ('401ARMORDIF', 'ARMOR DISTRI DIFFERES'), ('401HORSP0', 'HORS PRESSE')]
KEYS = ['Payable', 'Ventes', 'Commissions', 'Nouveaux différés', 'Différés échus', 'Hors presse']

def money(value):
    return Decimal(str(value).replace('\u202f', '').replace('\xa0', '').replace(' ', '').replace(',', '.')).quantize(Decimal('.01'))

def amounts(line):
    line = re.sub(r'\d{2}/\d{2}/\d{4}', '', line)
    return [money(v) for v in re.findall(r'-?(?:\d{1,3}(?: \d{3})+|\d+),\d{2}', line.replace('\xa0', ' ').replace('\u202f', ' '))]

def parse_pdf(data):
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        pages = [p.extract_text() or '' for p in pdf.pages]
    text = '\n'.join(pages)
    headers = re.findall(r'Relevé de presse du (\d{2}/\d{2}/\d{4}) (.+?) \(R(\d{4}-\d+)\)', text)
    if not headers:
        raise ValueError('Relevé de presse non reconnu. PDF texte Armor Distripresse requis (pas de scan).')
    if len({(d, r) for d, _, r in headers}) != 1:
        raise ValueError('Plusieurs relevés dans le PDF : fournir un PDF par relevé.')
    date, _, ref = headers[0]
    values = dict.fromkeys(KEYS, Decimal('0.00'))
    details = []
    for page in pages:
        h = re.search(r'Relevé de presse du .*? (FRANCE MESSAGERIE|MLP|Titres locaux) \(R', page)
        if 'Relevé de presse du' not in page:
            continue
        if not h:
            raise ValueError('Catégorie de presse non reconnue : contrôle manuel nécessaire.')
        lines = page.splitlines()
        totals = [amounts(l) for l in lines if re.match(r'^TOTAL\s+-?\d', l)]
        if len(totals) != 1 or len(totals[0]) != 8:
            raise ValueError('Total de presse ambigu ou incomplet.')
        v = totals[0]
        if v[5] - v[6] != v[7]:
            raise ValueError('Ventes moins commissions différent du net.')
        dif = [amounts(l) for l in lines if l.startswith('TOTAL DIFFERES')]
        if len(dif) > 1 or any(len(x) != 8 for x in dif):
            raise ValueError('Total différés ambigu.')
        deferred = -dif[0][-1] if dif else Decimal('0')
        comptant = [amounts(l)[-1] for l in lines if l.startswith('TOTAL PRESSE') and amounts(l)]
        if len(comptant) != 1 or v[7] - deferred != comptant[0]:
            raise ValueError('Contrôle du comptant impossible.')
        values['Ventes'] += v[5]
        values['Commissions'] += v[6]
        values['Nouveaux différés'] += deferred
        details.append({'Catégorie': h[1], 'Ventes': str(v[5]), 'Commissions': str(v[6]), 'Différés nets': str(deferred)})
    account_pages = [p for p in pages if 'Relevé de compte au' in p]
    if len(account_pages) != 1:
        raise ValueError('Une seule page récapitulative de compte est attendue.')
    lines = account_pages[0].splitlines()
    payable = [amounts(l)[-1] for l in lines if ('MONTANT PAYABLE LE' in l or 'MONTANT CREDITEUR REPORTE' in l) and amounts(l)]
    if len(payable) != 1:
        raise ValueError('Montant payable introuvable ou ambigu.')
    values['Payable'] = payable[0]
    extras = []
    for l in lines:
        if re.match(r'^\d{2}/\d{2}/\d{4}\s', l):
            if 'DIFFERES' in l:
                values['Différés échus'] += amounts(l)[-1]
            elif 'HORS PRESSE' in l:
                values['Hors presse'] += amounts(l)[-1]
            elif 'Montant presse comptant' not in l:
                extras.append({'Libellé': l, 'Montant': amounts(l)[-1], 'Compte': ''})
    if balance(values) + sum(x['Montant'] for x in extras):
        raise ValueError('Le relevé ne se rapproche pas au centime : vérifier les autres opérations.')
    return {'date': datetime.strptime(date, '%d/%m/%Y').date(), 'ref': ref, 'values': values, 'details': details, 'extras': extras}

def balance(v):
    return v['Ventes'] - v['Commissions'] - v['Nouveaux différés'] + v['Différés échus'] + v['Hors presse'] - v['Payable']

def entries(date, ref, number, values, accounts, extras=None):
    extras = extras or []
    if balance(values) + sum(x['Montant'] for x in extras):
        raise ValueError('Écriture déséquilibrée.')
    if not re.fullmatch(r'[A-Za-z0-9_-]+', ref):
        raise ValueError('Référence : lettres, chiffres, tirets et underscores uniquement.')
    rows = []
    for key, (account, label), direction in zip(KEYS, accounts, [-1, 1, -1, -1, 1, 1]):
        if not re.fullmatch(r'[A-Za-z0-9]+', account):
            raise ValueError('Compte non alphanumérique : ' + account)
        signed = values[key] * direction
        row = dict.fromkeys(FIELDS, '')
        row.update(JournalCode='PR', JournalLib='PRESSE', EcritureNum=str(number), EcritureDate=date.strftime('%Y%m%d'), CompteNum=account, CompteLib=label, PieceRef=ref, PieceDate=date.strftime('%Y%m%d'), EcritureLib='ARMOR ' + ref + ' - ' + label, Debit=format(max(signed, 0), '.2f').replace('.', ','), Credit=format(max(-signed, 0), '.2f').replace('.', ','))
        rows.append(row)
    for item in extras:
        rows.append(make_row('PR', date, ref, number, item['Compte'], item['Libellé'], item['Montant']))
    return rows

def make_row(journal, date, ref, number, account, label, signed):
    if not re.fullmatch(r'[A-Za-z0-9]+', account):
        raise ValueError('Compte à renseigner (lettres et chiffres) : ' + label)
    if not re.fullmatch(r'[A-Za-z0-9_-]+', ref):
        raise ValueError('Référence de pièce invalide.')
    row = dict.fromkeys(FIELDS, '')
    row.update(JournalCode=journal, JournalLib='ACHATS' if journal == 'HA' else 'PRESSE', EcritureNum=str(number), EcritureDate=date.strftime('%Y%m%d'), CompteNum=account, CompteLib=label, PieceRef=ref, PieceDate=date.strftime('%Y%m%d'), EcritureLib=(ref+' - '+label), Debit=format(max(signed, 0), '.2f').replace('.', ','), Credit=format(max(-signed, 0), '.2f').replace('.', ','))
    return row

def parse_invoice(data):
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        text = '\n'.join(p.extract_text() or '' for p in pdf.pages)
    headers = re.findall(r'(Facture|Avoir) TX (\d+) du (\d{2}/\d{2}/\d{4})', text)
    if len(set(headers)) != 1:
        raise ValueError('Une facture ou un avoir TX complet est attendu.')
    kind, num, day = headers[0]
    tax = {}
    for l in text.splitlines():
        m = re.match(r'^(T\d+)\s+(\d+,\d+)%\s+(.+)', l)
        if m:
            nums = amounts(m[3])
            if len(nums) < 2:
                raise ValueError('Récapitulatif TVA incomplet.')
            code, rate = m[1], str(money(m[2]))
            if code in tax:
                raise ValueError('Récapitulatif TVA répété.')
            tax[code] = (rate, nums[0], nums[1])
    items = []
    for l in text.splitlines():
        if not re.match(r'^\d{2}/\d{2}/\d{4}\s', l):
            continue
        m = re.search(r'\s(T\d+)\s+(.+)', l)
        if not m or m[1] not in tax:
            raise ValueError('Ligne article / taux non reconnu : '+l)
        nums = amounts(m[2])
        if len(nums) != 3 or nums[0]+nums[1] != nums[2]:
            raise ValueError('Ligne article non rapprochée : '+l)
        label = l[:m.start()]
        nature = 'Emballages' if re.search(r'consign|emball', label, re.I) else 'Marchandises'
        items.append({'Désignation': label, 'Nature': nature, 'Taux': tax[m[1]][0], 'HT': nums[0], 'TVA': nums[1], 'TTC': nums[2], 'Code': m[1]})
    def total(label):
        matches = [amounts(l)[-1] for l in text.splitlines() if l.startswith(label) and amounts(l)]
        if len(matches) != 1:
            raise ValueError('Total absent ou ambigu : '+label)
        return matches[0]
    ht, ttc = total('TOTAL HT'), total('TOTAL TTC')
    if not items or sum(x['HT'] for x in items) != ht or sum(x['TTC'] for x in items) != ttc:
        raise ValueError('Les articles ne correspondent pas aux totaux de la facture.')
    for code, (rate, base, vat) in tax.items():
        if sum(x['HT'] for x in items if x['Code']==code) != base or sum(x['TVA'] for x in items if x['Code']==code) != vat:
            raise ValueError('Écart avec le récapitulatif TVA : '+code)
    return {'date': datetime.strptime(day, '%d/%m/%Y').date(), 'ref': ('ATX-' if kind=='Avoir' else 'FTX-')+num, 'kind':kind, 'items':items, 'ht':ht, 'ttc':ttc, 'journal':'HA'}

def invoice_entries(parsed, number, packaging, purchases, vat_accounts, supplier):
    sign = -1 if parsed['kind']=='Avoir' else 1
    groups = {}
    for item in parsed['items']:
        rate = item['Taux']
        acc = packaging if item['Nature']=='Emballages' else purchases[rate]
        for account, label, value in [(acc, item['Nature']+' TVA '+rate+' %', item['HT']), (vat_accounts[rate], 'TVA déductible '+rate+' %', item['TVA'])]:
            groups[(account,label)] = groups.get((account,label), Decimal(0)) + value * sign
    rows = [make_row('HA', parsed['date'], parsed['ref'], number, acc, label, value) for (acc,label),value in groups.items() if value]
    rows.append(make_row('HA', parsed['date'], parsed['ref'], number, supplier, 'HORS PRESSE', -parsed['ttc']*sign))
    if sum(money(r['Debit'])-money(r['Credit']) for r in rows):
        raise ValueError('Écriture HA déséquilibrée.')
    return rows

def fec_bytes(rows):
    out = io.StringIO(newline='')
    w = csv.DictWriter(out, fieldnames=FIELDS, delimiter='\t', lineterminator='\r\n')
    w.writeheader()
    w.writerows(rows)
    return out.getvalue().encode('utf-8-sig')

def zip_bytes(files):
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, data)
    return out.getvalue()
