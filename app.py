import copy
import io
import zipfile
from datetime import date
import pandas as pd
import streamlit as st
import pypdfium2 as pdfium
from converter import DEFAULTS
from workspace import (COLS, BUY, new_doc, set_rows, edited_rows, process, template,
                       check, export_bundle, save_project, load_project)

st.set_page_config(page_title='Armor → Pennylane',page_icon='📰',layout='wide')
if 'docs' not in st.session_state:st.session_state.docs={}
if 'settings' not in st.session_state:
    st.session_state.settings={'accounts':DEFAULTS,'packaging':'6022','purchases':BUY,'vat':{r:'44566' for r in BUY}}
if 'epoch' not in st.session_state:st.session_state.epoch=0
if 'bases' not in st.session_state:st.session_state.bases={}
docs=st.session_state.docs

def edit_callback(doc_id,widget):
    d=st.session_state.docs[doc_id]
    d['rows']=edited_rows(st.session_state.bases[widget],st.session_state[widget])
    d['validated']=False

def meta_callback(doc_id,field,widget):
    d=st.session_state.docs[doc_id];v=st.session_state[widget]
    d[field]=v.isoformat() if field=='date' else v
    if field!='selected':d['validated']=False

def propose(doc,force=False,auto=True):
    candidate=copy.deepcopy(doc)
    try:
        process(candidate,st.session_state.settings,force_ocr=force,auto_ocr=auto)
        if doc['rows']:
            st.session_state['proposal_'+doc['id']]=candidate
            doc['message']='Nouvelle proposition prête. Cliquez sur « Appliquer la proposition » pour remplacer votre saisie.'
        else:
            doc.update(candidate)
    except Exception as exc:
        doc['ocr_text']=candidate['ocr_text']
        doc['message']='Lecture non reconnue : '+str(exc)+'. Saisie manuelle disponible.'

st.title('Armor Distripresse → Pennylane')
st.caption('Saisie, OCR et traitements séparés du téléchargement. Un dossier client par projet.')
with st.sidebar:
    st.subheader('Téléchargement')
    export_slot=st.empty()
    start=st.number_input('Premier numéro d’écriture',min_value=1,value=9086,step=1)
    only_validated=st.checkbox('Exporter uniquement les pièces validées',value=False)
    st.caption('Par défaut : toutes les pièces sélectionnées dont l’écriture est complète et équilibrée. Aucun traitement ni OCR au téléchargement.')
    st.divider()
    st.subheader('Comptes proposés')
    settings=copy.deepcopy(st.session_state.settings)
    epoch=st.session_state.epoch
    with st.expander('Presse et fournisseurs'):
        configs=[]
        for i in [0,1,2,3,5]:
            a,l=settings['accounts'][i]
            configs.append((st.text_input(l,a,key=f'config{epoch}-{i}').strip(),l))
        settings['accounts']=configs[:4]+[configs[3],configs[4]]
    settings['packaging']=st.text_input('Consignes / emballages',settings['packaging'],key=f'pack{epoch}')
    with st.expander('Achats et TVA par taux'):
        for r in BUY:
            settings['purchases'][r]=st.text_input('Achats '+r+' %',settings['purchases'][r],key=f'buy{epoch}-{r}')
            settings['vat'][r]=st.text_input('TVA '+r+' %',settings['vat'][r],key=f'vat{epoch}-{r}')
    st.session_state.settings=settings
    st.caption('Ces paramètres s’appliquent aux prochaines propositions, sans modifier les écritures déjà saisies.')

pieces_tab, treatment_tab, backup_tab=st.tabs(['Pièces et saisie','Ajout et traitements','Sauvegarde / reprise'])
with treatment_tab:
    uploads=st.file_uploader('Ajouter des PDF ou un ZIP Pennylane',type=['pdf','zip'],accept_multiple_files=True)
    if st.button('Ajouter à la liste',disabled=not uploads):
        added=0;duplicates=0;ignored=[]
        try:
            staged=[]
            for upload in uploads:
                if upload.name.lower().endswith('.pdf'):staged.append((upload.name,upload.getvalue()))
                else:
                    with zipfile.ZipFile(io.BytesIO(upload.getvalue())) as z:
                        infos=[i for i in z.infolist() if not i.is_dir()]
                        if len(infos)>1000 or sum(i.file_size for i in infos)>500_000_000:raise ValueError('ZIP limité à 1 000 fichiers et 500 Mo décompressés')
                        for info in infos:
                            if info.filename.lower().endswith('.pdf'):staged.append((info.filename,z.read(info)))
                            else:ignored.append(info.filename)
            for name,data in staged:
                d=new_doc(name,data)
                if d['id'] in docs:duplicates+=1
                else:docs[d['id']]=d;added+=1
            st.session_state.notice=f'{added} pièce(s) ajoutée(s), {duplicates} doublon(s) ignoré(s). '+('Non-PDF ignorés : '+', '.join(ignored) if ignored else '')
            st.rerun()
        except Exception as exc:st.error(str(exc))
    st.divider()
    auto=st.checkbox('Utiliser l’OCR automatiquement si le PDF n’a pas de texte',value=True)
    pending=[d for d in docs.values() if not d['rows']]
    if st.button(f'Lire les {len(pending)} pièces sans écriture',disabled=not pending):
        progress=st.progress(0)
        for i,d in enumerate(pending):
            with st.spinner('Lecture : '+d['name']):propose(d,auto=auto)
            progress.progress((i+1)/len(pending))
        st.rerun()
    st.caption('La lecture de lot ne touche jamais aux écritures existantes. Dans une pièce, une nouvelle lecture ou un OCR produit une proposition distincte avant remplacement.')

with backup_tab:
    st.info('La session conserve vos corrections tant qu’elle reste active. Téléchargez une sauvegarde pour reprendre après fermeture ou expiration : elle contient aussi les PDF et les paramètres.')
    backup_slot=st.empty()
    restore=st.file_uploader('Recharger une sauvegarde de projet',type=['zip'],key='restore')
    replace=st.checkbox('Remplacer le projet actuellement ouvert par cette sauvegarde')
    if st.button('Restaurer le projet',disabled=not restore or not replace):
        try:
            restored,settings=load_project(restore.getvalue())
            st.session_state.docs=restored;st.session_state.settings=settings
            st.session_state.epoch+=1;st.session_state.bases={}
            st.rerun()
        except Exception as exc:st.error('Restauration impossible : '+str(exc))

with pieces_tab:
    if 'notice' in st.session_state:st.info(st.session_state.pop('notice'))
    if not docs:st.info('Ajoutez vos documents dans « Ajout et traitements ». Vous pourrez ensuite les lire automatiquement ou saisir directement leurs écritures.')
    search=st.text_input('Rechercher une pièce',placeholder='Nom, référence ou journal')
    for doc_id,d in docs.items():
        if search and search.casefold() not in (d['name']+' '+d['ref']+' '+d['journal']).casefold():continue
        errors,debit,credit=check(d)
        status='Validée' if d['validated'] and not errors else ('Équilibrée · à vérifier' if not errors else ('À saisir' if not d['rows'] else 'À corriger'))
        with st.expander(f"{status} | {d['date']} | {d['journal']} | {d['ref']} | {d['name'].split('/')[-1]}"):
            prefix=f'{st.session_state.epoch}-{doc_id}-{d["revision"]}'
            for field,label in [('selected','Inclure dans l’export')]:
                widget=prefix+field
                st.checkbox(label,value=d[field],key=widget,on_change=meta_callback,args=(doc_id,field,widget))
            left,right=st.columns([1,2])
            with left:
                st.download_button('Ouvrir / télécharger le PDF',d['pdf'],d['name'].split('/')[-1],key='pdf'+prefix,on_click='ignore')
                if st.checkbox('Afficher le PDF à côté',key='show'+prefix):
                    try:
                        pdf=pdfium.PdfDocument(d['pdf'])
                        page_num=st.number_input('Page',min_value=1,max_value=len(pdf),value=1,key='page'+prefix)
                        page=pdf[page_num-1];bitmap=page.render(scale=1.5);im=bitmap.to_pil()
                        st.image(im,width='stretch')
                        im.close();bitmap.close();page.close();pdf.close()
                    except Exception as exc:st.error('Aperçu indisponible : '+str(exc))
            with right:
                a,b,c=st.columns([1,1,2])
                a.date_input('Date',date.fromisoformat(d['date']),key=prefix+'date',on_change=meta_callback,args=(doc_id,'date',prefix+'date'))
                b.text_input('Journal',d['journal'],key=prefix+'journal',on_change=meta_callback,args=(doc_id,'journal',prefix+'journal'))
                c.text_input('Référence',d['ref'],key=prefix+'ref',on_change=meta_callback,args=(doc_id,'ref',prefix+'ref'))
                editor_key='editor'+prefix
                if editor_key not in st.session_state or editor_key not in st.session_state.bases:st.session_state.bases[editor_key]=copy.deepcopy(d['rows'])
                frame=pd.DataFrame(st.session_state.bases[editor_key],columns=COLS).astype(str)
                st.data_editor(frame,num_rows='dynamic',hide_index=True,width='stretch',key=editor_key,on_change=edit_callback,args=(doc_id,editor_key),column_config={'CompteNum':'Compte','CompteLib':'Libellé','Debit':'Débit','Credit':'Crédit'})
                st.caption('Ajoutez une ligne avec + en bas du tableau. Sélectionnez des lignes pour les supprimer. Montants avec virgule ou point. Validez la cellule avec Entrée pour enregistrer la modification.')
                errors,debit,credit=check(d)
                st.write(f'Débit **{debit:.2f} €** · Crédit **{credit:.2f} €** · Écart **{debit-credit:.2f} €**')
                if errors:st.warning(' / '.join(errors))
                if st.button('Valider cette pièce',key='validate'+prefix,disabled=bool(errors)):
                    d['validated']=True;st.rerun()
                st.caption(d['message'])
                with st.expander('Modèles et traitements de cette pièce'):
                    model=st.selectbox('Modèle de saisie',['Écriture libre','Achat avec TVA','Consignes','Presse'],key='model'+prefix)
                    if st.button('Appliquer le modèle (remplace les lignes)',key='template'+prefix):
                        set_rows(d,template(model,settings));d['journal']='PR' if model=='Presse' else 'HA';d['origin']='Manuel';d['message']='Modèle manuel : renseignez les montants.';st.rerun()
                    a,b=st.columns(2)
                    if a.button('Relire le PDF',key='read'+prefix):
                        with st.spinner('Lecture…'):propose(d)
                        st.rerun()
                    if b.button('Lancer l’OCR',key='ocr'+prefix):
                        with st.spinner('OCR en cours, quelques instants par page…'):propose(d,force=True)
                        st.rerun()
                    proposal=st.session_state.get('proposal_'+doc_id)
                    if proposal:
                        st.write('Proposition à appliquer :')
                        st.dataframe(pd.DataFrame(proposal['rows']),hide_index=True)
                        if st.button('Appliquer la proposition (remplace la saisie)',key='apply'+prefix):
                            proposal['revision']=d['revision']+1;proposal['selected']=d['selected'];d.update(proposal)
                            del st.session_state['proposal_'+doc_id];st.rerun()
                    if d['ocr_text']:st.text_area('Texte OCR pour aider la saisie',d['ocr_text'],height=180,key='text'+prefix)

# Assemble downloads only from current stored entries; never invoke parsing or OCR here.
pack,included,excluded=export_bundle(docs,start,only_validated)
with export_slot.container():
    st.download_button('⬇ Télécharger FEC + PJ',pack or b'',file_name='ARMOR_FEC_PJ.zip',mime='application/zip',disabled=pack is None,type='primary',width='stretch',on_click='ignore')
    st.caption(f'{len(included)} pièce(s) exportable(s) / {len(docs)} · {len(excluded)} hors export')
    if excluded:
        with st.expander('Voir les pièces hors export'):
            st.dataframe(pd.DataFrame(excluded),hide_index=True)
    if pack and excluded:st.warning('Export partiel : seules les pièces exportables sont incluses.')
with backup_slot.container():
    st.download_button('Sauvegarder le travail et les PDF',save_project(docs,settings),'PROJET_ARMOR.zip','application/zip',on_click='ignore')
