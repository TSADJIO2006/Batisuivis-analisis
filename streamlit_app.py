"""BatiSuivi - version Streamlit adaptée de l'application Flask.
Lancez avec : streamlit run streamlit_app.py
La base SQLite batisuivi.db est créée à côté de ce fichier.
"""
from pathlib import Path
from datetime import date, datetime
import sqlite3
import pandas as pd
import streamlit as st

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "batisuivi.db"
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

st.set_page_config(page_title="BatiSuivi | Gestion de chantier", page_icon="🏗️", layout="wide")

# --- Base de données : mêmes tables principales que l'application Flask ---
def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    with get_db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE, full_name TEXT NOT NULL, password_hash TEXT NOT NULL DEFAULT '', role TEXT NOT NULL DEFAULT 'maitre_ouvrage', profile_photo TEXT DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS site (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, location TEXT NOT NULL, manager TEXT NOT NULL, start_date TEXT NOT NULL, end_date TEXT NOT NULL, budget REAL NOT NULL CHECK(budget>=0));
        CREATE TABLE IF NOT EXISTS progress (id INTEGER PRIMARY KEY AUTOINCREMENT, site_id INTEGER NOT NULL, work_date TEXT NOT NULL, activity TEXT NOT NULL, planned_qty REAL NOT NULL CHECK(planned_qty>=0), actual_qty REAL NOT NULL CHECK(actual_qty>=0), unit TEXT NOT NULL, workers INTEGER NOT NULL CHECK(workers>=0), hours REAL NOT NULL CHECK(hours>=0), notes TEXT DEFAULT '', FOREIGN KEY(site_id) REFERENCES site(id));
        CREATE TABLE IF NOT EXISTS materials (id INTEGER PRIMARY KEY AUTOINCREMENT, site_id INTEGER NOT NULL, record_date TEXT NOT NULL, material TEXT NOT NULL, opening_stock REAL NOT NULL CHECK(opening_stock>=0), received_qty REAL NOT NULL CHECK(received_qty>=0), used_qty REAL NOT NULL CHECK(used_qty>=0), unit TEXT NOT NULL, unit_price REAL NOT NULL CHECK(unit_price>=0), FOREIGN KEY(site_id) REFERENCES site(id));
        CREATE TABLE IF NOT EXISTS expenses (id INTEGER PRIMARY KEY AUTOINCREMENT, site_id INTEGER NOT NULL, expense_date TEXT NOT NULL, category TEXT NOT NULL, description TEXT NOT NULL, amount REAL NOT NULL CHECK(amount>=0), activity TEXT NOT NULL DEFAULT '', FOREIGN KEY(site_id) REFERENCES site(id));
        CREATE TABLE IF NOT EXISTS incidents (id INTEGER PRIMARY KEY AUTOINCREMENT, site_id INTEGER NOT NULL, incident_date TEXT NOT NULL, category TEXT NOT NULL, hours_lost REAL NOT NULL CHECK(hours_lost>=0), description TEXT NOT NULL, FOREIGN KEY(site_id) REFERENCES site(id));
        CREATE TABLE IF NOT EXISTS planning (id INTEGER PRIMARY KEY AUTOINCREMENT, site_id INTEGER NOT NULL, title TEXT NOT NULL, start_date TEXT NOT NULL, end_date TEXT NOT NULL, responsible TEXT DEFAULT '', status TEXT NOT NULL DEFAULT 'À faire', notes TEXT DEFAULT '', validated INTEGER NOT NULL DEFAULT 0, validated_by TEXT DEFAULT '', validated_at TEXT DEFAULT '', FOREIGN KEY(site_id) REFERENCES site(id));
        CREATE TABLE IF NOT EXISTS staff (id INTEGER PRIMARY KEY AUTOINCREMENT, site_id INTEGER NOT NULL, full_name TEXT NOT NULL, job_title TEXT NOT NULL, phone TEXT DEFAULT '', monthly_salary REAL NOT NULL CHECK(monthly_salary>=0), active INTEGER NOT NULL DEFAULT 1, FOREIGN KEY(site_id) REFERENCES site(id));
        CREATE TABLE IF NOT EXISTS payroll (id INTEGER PRIMARY KEY AUTOINCREMENT, staff_id INTEGER NOT NULL, site_id INTEGER NOT NULL, payroll_month TEXT NOT NULL, amount REAL NOT NULL, expense_id INTEGER, UNIQUE(staff_id,payroll_month), FOREIGN KEY(staff_id) REFERENCES staff(id), FOREIGN KEY(site_id) REFERENCES site(id), FOREIGN KEY(expense_id) REFERENCES expenses(id));
        CREATE TABLE IF NOT EXISTS site_photos (id INTEGER PRIMARY KEY AUTOINCREMENT, site_id INTEGER NOT NULL, photo_path TEXT NOT NULL, caption TEXT DEFAULT '', photo_date TEXT NOT NULL, uploaded_by TEXT DEFAULT '', FOREIGN KEY(site_id) REFERENCES site(id));
        CREATE TABLE IF NOT EXISTS quotes (id INTEGER PRIMARY KEY AUTOINCREMENT, site_id INTEGER NOT NULL, quote_date TEXT NOT NULL, designation TEXT NOT NULL, quantity REAL NOT NULL CHECK(quantity>=0), unit TEXT NOT NULL, unit_price REAL NOT NULL CHECK(unit_price>=0), notes TEXT DEFAULT '', FOREIGN KEY(site_id) REFERENCES site(id));
        """)
        # Migrations pour une base créée avec une ancienne version Flask.
        for table, col, definition in [('users','profile_photo',"TEXT DEFAULT ''"),('planning','validated','INTEGER NOT NULL DEFAULT 0'),('planning','validated_by',"TEXT DEFAULT ''"),('planning','validated_at',"TEXT DEFAULT ''"),('expenses','activity',"TEXT NOT NULL DEFAULT ''")]:
            cols={r[1] for r in c.execute(f'PRAGMA table_info({table})')}
            if col not in cols: c.execute(f'ALTER TABLE {table} ADD COLUMN {col} {definition}')

def seed_demo():
    with get_db() as c:
        if c.execute('SELECT COUNT(*) FROM site').fetchone()[0]: return
        projects=[("Construction d'un bâtiment R+2 (démonstration)","Yaoundé, Cameroun","Responsable de démonstration","2026-09-01","2026-11-30",60000000),('Construction d’une route en béton bitumineux','Douala, Cameroun','Ingénieur travaux - Équipe B','2026-09-01','2026-11-30',85000000),('Construction d’un bâtiment scolaire R+1','Bafoussam, Cameroun','Ingénieur travaux - Équipe C','2026-09-10','2026-11-30',47000000)]
        c.executemany('INSERT INTO site(name,location,manager,start_date,end_date,budget) VALUES(?,?,?,?,?,?)',projects)
        sites=c.execute('SELECT id,name,budget FROM site').fetchall()
        activities=[('Fouilles',12,10,'m³'),('Béton de propreté',8,6,'m³'),('Ferraillage des fondations',350,300,'kg'),('Coffrage des fondations',40,35,'m²'),('Bétonnage des fondations',12,10,'m³'),('Maçonnerie du soubassement',24,20,'m²'),('Remblai',18,15,'m³'),('Dallage',35,30,'m²'),('Élévation des murs RDC',45,42,'m²'),('Poteaux RDC',12,10,'unité')]
        for si in sites:
            sid=si['id']
            for i,(a,planned,actual,u) in enumerate(activities):
                c.execute('INSERT INTO progress(site_id,work_date,activity,planned_qty,actual_qty,unit,workers,hours,notes) VALUES(?,?,?,?,?,?,?,?,?)',(sid,f'2026-09-{i+1:02d}',a,planned,actual,u,5+i%4,7,'Donnée synthétique de démonstration' if i%3==0 else ''))
            c.executemany('INSERT INTO expenses(site_id,expense_date,category,description,amount,activity) VALUES(?,?,?,?,?,?)',[(sid,'2026-09-15','Matériaux','Achat de matériaux',1250000,''),(sid,'2026-09-18','Main-d’œuvre','Paiement équipe',800000,''),(sid,'2026-09-20','Transport','Transport matériaux',175000,'')])
            c.executemany('INSERT INTO materials(site_id,record_date,material,opening_stock,received_qty,used_qty,unit,unit_price) VALUES(?,?,?,?,?,?,?,?)',[(sid,'2026-09-15','Ciment',30,100,75,'sac',5000),(sid,'2026-09-16','Sable',10,20,12,'m³',18000),(sid,'2026-09-17','Fer à béton HA10',200,500,350,'kg',850)])
            c.executemany('INSERT INTO incidents(site_id,incident_date,category,hours_lost,description) VALUES(?,?,?,?,?)',[(sid,'2026-09-03','Livraison tardive',3,'Livraison arrivée après l’heure prévue'),(sid,'2026-09-12','Météo',2.5,'Pluie pendant les travaux')])
            c.executemany('INSERT INTO quotes(site_id,quote_date,designation,quantity,unit,unit_price,notes) VALUES(?,?,?,?,?,?,?)',[(sid,'2026-09-01',x,1,'lot',amount,'Estimation de démonstration à adapter') for x,amount in [('Installation et études',2500000),('Terrassement et fondations',8500000),('Structure et maçonnerie',22000000),('Finitions et réception',6000000)]])
            c.executemany('INSERT INTO staff(site_id,full_name,job_title,phone,monthly_salary) VALUES(?,?,?,?,?)',[(sid,n,j,'',salary) for n,j,salary in [('Chef de chantier','Chef de chantier',350000),('Technicien génie civil','Technicien',250000),('Maçon qualifié','Maçon',180000)]])
            c.executemany('INSERT INTO planning(site_id,title,start_date,end_date,responsible,status,notes) VALUES(?,?,?,?,?,?,?)',[(sid,a,'2026-09-01','2026-10-15','Chef de chantier','En cours','Phase de démonstration') for a,_,_,_ in activities])

def query_df(sql, params=()):
    with get_db() as c: return pd.read_sql_query(sql,c,params=params)
def execute(sql, params=()):
    with get_db() as c: c.execute(sql,params)
def money(v): return f"{float(v or 0):,.0f}".replace(',', ' ') + ' FCFA'
def site_rows(): return query_df('SELECT * FROM site ORDER BY id DESC')

init_db(); seed_demo()

with st.sidebar:
    st.markdown('# 🏗️ BatiSuivi')
    st.caption('Gestion et suivi des chantiers')
    sites=site_rows()
    if sites.empty:
        st.warning('Créez un chantier pour commencer.')
        selected_id=None
    else:
        opts={f"{r['name']} — {r['location']}":int(r['id']) for _,r in sites.iterrows()}
        selected_label=st.selectbox('Chantier actif',list(opts))
        selected_id=opts[selected_label]
    page=st.radio('Navigation',['Tableau de bord','Chantiers','Devis','Collecte de données','Suivi des travaux','Matériaux','Dépenses','Incidents','Analyses et rapports','Planning','Équipe et paie','Photos du chantier','Profil'])
    st.divider()
    st.caption('Projet pédagogique • Données modifiables')

site = None if selected_id is None else query_df('SELECT * FROM site WHERE id=?',(selected_id,)).iloc[0].to_dict()
def form_site_id(): return int(selected_id) if selected_id else 0
def require_site():
    if not selected_id: st.info('Commencez par créer un chantier dans le menu Chantiers.'); return False
    return True

def show_df(sql, params=()):
    df=query_df(sql,params)
    if df.empty: st.info('Aucune donnée enregistrée pour ce chantier.'); return df
    st.dataframe(df, use_container_width=True, hide_index=True); return df

if page=='Tableau de bord':
    st.title('Tableau de bord')
    st.write('Vue synthétique de l’avancement, des dépenses et des difficultés du chantier sélectionné.')
    if require_site():
        prog=query_df('SELECT * FROM progress WHERE site_id=?',(selected_id,)); exp=query_df('SELECT * FROM expenses WHERE site_id=?',(selected_id,)); inc=query_df('SELECT * FROM incidents WHERE site_id=?',(selected_id,)); mats=query_df('SELECT * FROM materials WHERE site_id=?',(selected_id,))
        planning=query_df('SELECT * FROM planning WHERE site_id=?',(selected_id,))
        spent=float(exp.amount.sum()) if not exp.empty else 0; completion=(float((planning.status.isin(['Réalisé','Terminé','Validé'])).sum())/len(planning)*100 if not planning.empty else 0)
        totalhours=float(prog.hours.sum()) if not prog.empty else 0; qty=float(prog.actual_qty.sum()) if not prog.empty else 0
        a,b,c,d=st.columns(4); a.metric('Budget prévisionnel',money(site['budget'])); b.metric('Dépenses engagées',money(spent)); c.metric('Budget restant',money(site['budget']-spent)); d.metric('Phases réalisées',f'{completion:.1f}%')
        e,f,g,h=st.columns(4); e.metric('Relevés de suivi',len(prog)); f.metric('Quantité réalisée',f'{qty:,.1f}'.replace(',',' ')); g.metric('Incidents',len(inc)); h.metric('Heures perdues',f"{inc.hours_lost.sum() if not inc.empty else 0:.1f} h")
        st.progress(min(max(spent/site['budget'] if site['budget'] else 0,0),1),text='Consommation du budget')
        left,right=st.columns(2)
        with left:
            st.subheader('Dépenses par catégorie')
            if not exp.empty: st.bar_chart(exp.groupby('category',as_index=False).amount.sum().set_index('category'))
            else: st.info('Aucune dépense.')
        with right:
            st.subheader('Quantités réalisées par date')
            if not prog.empty: st.line_chart(prog.groupby('work_date',as_index=True).actual_qty.sum())
            else: st.info('Aucun relevé de suivi.')
        st.subheader('Derniers relevés'); show_df('SELECT work_date AS Date,activity AS Activité,planned_qty AS Prévu,actual_qty AS Réalisé,unit AS Unité,workers AS Ouvriers,hours AS Heures,notes AS Notes FROM progress WHERE site_id=? ORDER BY work_date DESC LIMIT 10',(selected_id,))

elif page=='Chantiers':
    st.title('Gestion des chantiers')
    with st.expander('➕ Créer un chantier',expanded=False):
        with st.form('site_form'):
            name=st.text_input('Nom du chantier'); location=st.text_input('Localisation'); manager=st.text_input('Responsable'); c1,c2=st.columns(2); start=c1.date_input('Date de début',value=date.today()); end=c2.date_input('Date de fin',value=date.today()); budget=st.number_input('Budget prévisionnel (FCFA)',min_value=0.0,step=100000.0)
            if st.form_submit_button('Créer le chantier'):
                if not name.strip() or not location.strip() or not manager.strip() or end<start: st.error('Vérifiez les champs et les dates.')
                else:
                    execute('INSERT INTO site(name,location,manager,start_date,end_date,budget) VALUES(?,?,?,?,?,?)',(name,location,manager,start.isoformat(),end.isoformat(),budget)); st.success('Chantier créé.'); st.rerun()
    st.subheader('Chantiers enregistrés'); show_df('SELECT id AS ID,name AS Chantier,location AS Localisation,manager AS Responsable,start_date AS Début,end_date AS Fin,budget AS Budget_FCFA FROM site ORDER BY id DESC')

elif page=='Devis':
    st.title('Devis estimatif')
    if require_site():
        with st.expander('Ajouter une ligne de devis'):
            with st.form('quote_form'):
                qdate=st.date_input('Date du devis',value=date.today()); designation=st.text_input('Désignation'); quantity=st.number_input('Quantité',min_value=0.0,value=1.0); unit=st.text_input('Unité',value='lot'); unit_price=st.number_input('Prix unitaire (FCFA)',min_value=0.0,step=1000.0); notes=st.text_area('Observations')
                if st.form_submit_button('Ajouter au devis'):
                    if not designation.strip() or not unit.strip(): st.error('La désignation et l’unité sont obligatoires.')
                    else: execute('INSERT INTO quotes(site_id,quote_date,designation,quantity,unit,unit_price,notes) VALUES(?,?,?,?,?,?,?)',(selected_id,qdate.isoformat(),designation,quantity,unit,unit_price,notes)); st.success('Ligne ajoutée.'); st.rerun()
        q=query_df('SELECT id,quote_date AS Date,designation AS Désignation,quantity AS Quantité,unit AS Unité,unit_price AS Prix_unitaire,quantity*unit_price AS Montant,notes AS Notes FROM quotes WHERE site_id=? ORDER BY id',(selected_id,))
        if not q.empty:
            st.metric('Montant total du devis',money(q['Montant'].sum())); st.dataframe(q.drop(columns=['id']),use_container_width=True,hide_index=True); st.download_button('Télécharger le devis (CSV)',q.drop(columns=['id']).to_csv(index=False).encode('utf-8-sig'),'devis_chantier.csv','text/csv')
        else: st.info('Aucune ligne de devis.')

elif page=='Collecte de données':
    st.title('Collecte des données de chantier')
    if require_site():
        tabs=st.tabs(['Avancement','Dépense','Matériaux','Incident','Nouvelle phase'])
        with tabs[0]:
            with st.form('progress_form'):
                d=st.date_input('Date du relevé',value=date.today()); activity=st.text_input('Activité / phase'); c1,c2,c3=st.columns(3); planned=c1.number_input('Quantité prévue',min_value=0.0); actual=c2.number_input('Quantité réalisée',min_value=0.0); unit=c3.selectbox('Unité',['m³','m²','m','kg','unité','lot','%']); c4,c5=st.columns(2); workers=c4.number_input('Nombre d’ouvriers',min_value=0,step=1); hours=c5.number_input('Heures travaillées',min_value=0.0); notes=st.text_area('Observations')
                if st.form_submit_button('Enregistrer le relevé'):
                    if not activity.strip(): st.error('Saisissez une activité.')
                    else: execute('INSERT INTO progress(site_id,work_date,activity,planned_qty,actual_qty,unit,workers,hours,notes) VALUES(?,?,?,?,?,?,?,?,?)',(selected_id,d.isoformat(),activity,planned,actual,unit,int(workers),hours,notes)); st.success('Relevé enregistré.'); st.rerun()
        with tabs[1]:
            with st.form('expense_form'):
                d=st.date_input('Date de dépense',value=date.today(),key='edate'); category=st.selectbox('Catégorie',['Matériaux','Main-d’œuvre','Transport','Matériel','Sous-traitance','Autre']); description=st.text_input('Description'); amount=st.number_input('Montant (FCFA)',min_value=0.0,step=1000.0); activity_exp=st.text_input('Phase associée (facultatif)')
                if st.form_submit_button('Enregistrer la dépense'):
                    if not description.strip(): st.error('Saisissez une description.')
                    else: execute('INSERT INTO expenses(site_id,expense_date,category,description,amount,activity) VALUES(?,?,?,?,?,?)',(selected_id,d.isoformat(),category,description,amount,activity_exp)); st.success('Dépense enregistrée.'); st.rerun()
        with tabs[2]:
            with st.form('material_form'):
                d=st.date_input('Date du mouvement',value=date.today(),key='mdate'); material=st.text_input('Matériau'); c1,c2,c3=st.columns(3); opening=c1.number_input('Stock initial',min_value=0.0); received=c2.number_input('Quantité reçue',min_value=0.0); used=c3.number_input('Quantité utilisée',min_value=0.0); c4,c5=st.columns(2); unit_m=c4.text_input('Unité',value='sac'); price=c5.number_input('Prix unitaire (FCFA)',min_value=0.0,step=100.0)
                if st.form_submit_button('Enregistrer le mouvement'):
                    if not material.strip() or not unit_m.strip(): st.error('Précisez le matériau et l’unité.')
                    else: execute('INSERT INTO materials(site_id,record_date,material,opening_stock,received_qty,used_qty,unit,unit_price) VALUES(?,?,?,?,?,?,?,?)',(selected_id,d.isoformat(),material,opening,received,used,unit_m,price)); st.success('Mouvement enregistré.'); st.rerun()
        with tabs[3]:
            with st.form('incident_form'):
                d=st.date_input('Date de l’incident',value=date.today(),key='idate'); category=st.selectbox('Type d’incident',['Livraison tardive','Manque de matériaux','Météo','Problème technique','Sécurité','Approvisionnement','Autre']); lost=st.number_input('Heures perdues',min_value=0.0,step=0.5); desc=st.text_area('Description')
                if st.form_submit_button('Enregistrer l’incident'):
                    if not desc.strip(): st.error('Décrivez l’incident.')
                    else: execute('INSERT INTO incidents(site_id,incident_date,category,hours_lost,description) VALUES(?,?,?,?,?)',(selected_id,d.isoformat(),category,lost,desc)); st.success('Incident enregistré.'); st.rerun()
        with tabs[4]:
            with st.form('planning_form'):
                title=st.text_input('Nom de la phase'); d1=st.date_input('Début prévu',value=date.today(),key='pstart'); d2=st.date_input('Fin prévue',value=date.today(),key='pend'); responsible=st.text_input('Responsable'); status=st.selectbox('Statut',['À faire','En cours','Réalisé']); notes_p=st.text_area('Notes')
                if st.form_submit_button('Ajouter la phase'):
                    if not title.strip() or d2<d1: st.error('Vérifiez le titre et les dates.')
                    else: execute('INSERT INTO planning(site_id,title,start_date,end_date,responsible,status,notes) VALUES(?,?,?,?,?,?,?)',(selected_id,title,d1.isoformat(),d2.isoformat(),responsible,status,notes_p)); st.success('Phase ajoutée.'); st.rerun()

elif page=='Suivi des travaux':
    st.title('Suivi des travaux')
    if require_site():
        show_df('SELECT work_date AS Date,activity AS Activité,planned_qty AS Prévu,actual_qty AS Réalisé,unit AS Unité,workers AS Ouvriers,hours AS Heures,notes AS Observations FROM progress WHERE site_id=? ORDER BY work_date DESC',(selected_id,))
        df=query_df('SELECT work_date,activity,planned_qty,actual_qty,unit,workers,hours,notes FROM progress WHERE site_id=? ORDER BY work_date DESC',(selected_id,))
        if not df.empty: st.download_button('Exporter le suivi en CSV',df.to_csv(index=False).encode('utf-8-sig'),'avancement_chantier.csv','text/csv')

elif page=='Matériaux':
    st.title('Gestion des matériaux et stocks')
    if require_site():
        df=query_df('SELECT record_date AS Date,material AS Matériau,opening_stock AS Stock_initial,received_qty AS Reçu,used_qty AS Utilisé,(opening_stock+received_qty-used_qty) AS Stock_restant,unit AS Unité,unit_price AS Prix_unitaire FROM materials WHERE site_id=? ORDER BY record_date DESC',(selected_id,))
        if not df.empty: st.dataframe(df,use_container_width=True,hide_index=True)
        else: st.info('Aucun mouvement. Ajoutez-en dans Collecte de données.')

elif page=='Dépenses':
    st.title('Suivi des dépenses')
    if require_site():
        df=query_df('SELECT expense_date AS Date,category AS Catégorie,description AS Description,activity AS Phase,amount AS Montant_FCFA FROM expenses WHERE site_id=? ORDER BY expense_date DESC',(selected_id,))
        if not df.empty: st.metric('Total des dépenses',money(df.Montant_FCFA.sum())); st.dataframe(df,use_container_width=True,hide_index=True); st.bar_chart(df.groupby('Catégorie').Montant_FCFA.sum())
        else: st.info('Aucune dépense.')

elif page=='Incidents':
    st.title('Incidents et retards')
    if require_site():
        df=query_df('SELECT incident_date AS Date,category AS Catégorie,hours_lost AS Heures_perdues,description AS Description FROM incidents WHERE site_id=? ORDER BY incident_date DESC',(selected_id,))
        if not df.empty: st.metric('Heures perdues cumulées',f"{df.Heures_perdues.sum():.1f} h"); st.dataframe(df,use_container_width=True,hide_index=True); st.bar_chart(df.groupby('Catégorie').Heures_perdues.sum())
        else: st.info('Aucun incident enregistré.')

elif page=='Analyses et rapports':
    st.title('Analyses et rapports')
    if require_site():
        prog=query_df('SELECT * FROM progress WHERE site_id=?',(selected_id,)); exp=query_df('SELECT * FROM expenses WHERE site_id=?',(selected_id,)); inc=query_df('SELECT * FROM incidents WHERE site_id=?',(selected_id,)); q=query_df('SELECT quantity*unit_price AS total FROM quotes WHERE site_id=?',(selected_id,)); mats=query_df('SELECT * FROM materials WHERE site_id=?',(selected_id,))
        total_exp=float(exp.amount.sum()) if not exp.empty else 0; planned=float(prog.planned_qty.sum()) if not prog.empty else 0; actual=float(prog.actual_qty.sum()) if not prog.empty else 0; hours=float(prog.hours.sum()) if not prog.empty else 0
        a,b,c=st.columns(3); a.metric('Avancement des quantités*',f'{actual/planned*100:.1f}%' if planned else '—'); b.metric('Productivité moyenne',f'{actual/hours:.2f} unité/h' if hours else '—'); c.metric('Devis estimatif',money(q.total.sum() if not q.empty else 0))
        st.caption('*Les quantités de différentes unités ne sont pas directement comparables ; cet indicateur est indicatif.')
        st.subheader('Dépenses par phase');
        if not exp.empty: st.bar_chart(exp.groupby(exp.activity.replace('', 'Non affectées')).amount.sum())
        st.subheader('Synthèse du chantier')
        report=pd.DataFrame([{'Chantier':site['name'],'Localisation':site['location'],'Responsable':site['manager'],'Budget FCFA':site['budget'],'Dépenses FCFA':total_exp,'Solde FCFA':site['budget']-total_exp,'Nombre de relevés':len(prog),'Nombre d’incidents':len(inc),'Heures perdues':float(inc.hours_lost.sum()) if not inc.empty else 0}])
        st.dataframe(report,use_container_width=True,hide_index=True); st.download_button('Télécharger la synthèse CSV',report.to_csv(index=False).encode('utf-8-sig'),'rapport_chantier.csv','text/csv')

elif page=='Planning':
    st.title('Planning des travaux')
    if require_site():
        with st.expander('Ajouter une tâche au planning'):
            with st.form('plan_add'):
                title=st.text_input('Tâche'); d1=st.date_input('Date de début',value=date.today(),key='pl1'); d2=st.date_input('Date de fin',value=date.today(),key='pl2'); resp=st.text_input('Responsable'); status=st.selectbox('Statut',['À faire','En cours','Réalisé']); notes=st.text_area('Notes',key='plnotes')
                if st.form_submit_button('Ajouter au planning'):
                    if not title.strip() or d2<d1: st.error('Vérifiez la tâche et les dates.')
                    else: execute('INSERT INTO planning(site_id,title,start_date,end_date,responsible,status,notes) VALUES(?,?,?,?,?,?,?)',(selected_id,title,d1.isoformat(),d2.isoformat(),resp,status,notes)); st.success('Tâche ajoutée.'); st.rerun()
        df=query_df('SELECT id,title AS Tâche,start_date AS Début,end_date AS Fin,responsible AS Responsable,status AS Statut,validated AS Validée,notes AS Notes FROM planning WHERE site_id=? ORDER BY start_date',(selected_id,))
        if not df.empty:
            st.dataframe(df.drop(columns=['id']),use_container_width=True,hide_index=True)
            for _,r in df.iterrows():
                with st.expander(f"{r['Tâche']} — {r['Statut']}"):
                    newstatus=st.selectbox('Modifier le statut',['À faire','En cours','Réalisé'],index=['À faire','En cours','Réalisé'].index(r['Statut']) if r['Statut'] in ['À faire','En cours','Réalisé'] else 0,key=f"status{r['id']}")
                    if st.button('Mettre à jour',key=f"update{r['id']}"): execute('UPDATE planning SET status=?,validated=?,validated_by=?,validated_at=? WHERE id=?',(newstatus,1 if newstatus=='Réalisé' else 0,'Utilisateur Streamlit',datetime.now().strftime('%Y-%m-%d %H:%M'),int(r['id']))); st.rerun()
        else: st.info('Aucune tâche au planning.')

elif page=='Équipe et paie':
    st.title('Équipe et paie')
    if require_site():
        with st.expander('Ajouter un membre'):
            with st.form('staff_form'):
                name=st.text_input('Nom complet'); job=st.text_input('Poste'); phone=st.text_input('Téléphone'); salary=st.number_input('Salaire mensuel (FCFA)',min_value=0.0,step=10000.0)
                if st.form_submit_button('Ajouter le membre'):
                    if not name.strip() or not job.strip(): st.error('Nom et poste obligatoires.')
                    else: execute('INSERT INTO staff(site_id,full_name,job_title,phone,monthly_salary) VALUES(?,?,?,?,?)',(selected_id,name,job,phone,salary)); st.success('Membre ajouté.'); st.rerun()
        df=query_df('SELECT id,full_name AS Nom,job_title AS Poste,phone AS Téléphone,monthly_salary AS Salaire_FCFA,active AS Actif FROM staff WHERE site_id=? ORDER BY active DESC,full_name',(selected_id,))
        if not df.empty: st.dataframe(df.drop(columns=['id']),use_container_width=True,hide_index=True)
        with st.expander('Comptabiliser un salaire'):
            staff=query_df('SELECT id,full_name,monthly_salary FROM staff WHERE site_id=? AND active=1',(selected_id,))
            if not staff.empty:
                with st.form('payroll_form'):
                    person=st.selectbox('Employé',staff.to_dict('records'),format_func=lambda x:f"{x['full_name']} — {money(x['monthly_salary'])}"); month=st.text_input('Mois (AAAA-MM)',value=date.today().strftime('%Y-%m'))
                    if st.form_submit_button('Comptabiliser'):
                        try:
                            if len(month)!=7 or month[4]!='-': raise ValueError()
                            with get_db() as c:
                                cur=c.execute('INSERT INTO expenses(site_id,expense_date,category,description,amount) VALUES(?,?,?,?,?)',(selected_id,month+'-01','Main-d’œuvre',f"Salaire {person['full_name']} — {month}",person['monthly_salary']))
                                c.execute('INSERT INTO payroll(staff_id,site_id,payroll_month,amount,expense_id) VALUES(?,?,?,?,?)',(person['id'],selected_id,month,person['monthly_salary'],cur.lastrowid))
                            st.success('Salaire ajouté aux dépenses.'); st.rerun()
                        except sqlite3.IntegrityError: st.error('Ce salaire est déjà comptabilisé pour ce mois.')
                        except ValueError: st.error('Le mois doit respecter le format AAAA-MM.')
            else: st.info('Ajoutez d’abord un membre actif.')

elif page=='Photos du chantier':
    st.title('Journal photo du chantier')
    if require_site():
        with st.form('photo_form'):
            uploaded=st.file_uploader('Choisir une photo (JPG, PNG, WEBP)',type=['jpg','jpeg','png','webp']); caption=st.text_input('Légende'); d=st.date_input('Date de la photo',value=date.today()); submit=st.form_submit_button('Ajouter la photo')
            if submit:
                if not uploaded: st.error('Choisissez une image.')
                else:
                    ext=uploaded.name.rsplit('.',1)[-1].lower(); filename=f"photo_{datetime.now().strftime('%Y%m%d%H%M%S%f')}.{ext}"; path=UPLOAD_DIR/filename; path.write_bytes(uploaded.getvalue()); execute('INSERT INTO site_photos(site_id,photo_path,caption,photo_date,uploaded_by) VALUES(?,?,?,?,?)',(selected_id,str(path.relative_to(BASE_DIR)).replace('\\','/'),caption,d.isoformat(),'Utilisateur Streamlit')); st.success('Photo ajoutée.'); st.rerun()
        photos=query_df('SELECT photo_path,caption,photo_date FROM site_photos WHERE site_id=? ORDER BY photo_date DESC,id DESC',(selected_id,))
        if not photos.empty:
            cols=st.columns(3)
            for i,(_,r) in enumerate(photos.iterrows()):
                path=BASE_DIR/r['photo_path']
                with cols[i%3]:
                    if path.exists(): st.image(str(path),use_container_width=True)
                    st.caption(f"{r['photo_date']} — {r['caption']}")
        else: st.info('Aucune photo pour le moment.')

elif page=='Profil':
    st.title('Profil utilisateur')
    st.write('Paramètres de profil pour cette version locale de démonstration.')
    with st.form('profile_form'):
        name=st.text_input('Nom complet',value=st.session_state.get('profile_name','Utilisateur BatiSuivi')); role=st.selectbox('Fonction',['Étudiant / démonstration','Ingénieur travaux','Chef de chantier','Maître d’ouvrage','Collecteur de données'])
        if st.form_submit_button('Enregistrer le profil'):
            st.session_state['profile_name']=name; st.session_state['profile_role']=role; st.success('Profil enregistré dans cette session.')
    st.info(f"Nom : {st.session_state.get('profile_name','Utilisateur BatiSuivi')}\n\nFonction : {st.session_state.get('profile_role','Étudiant / démonstration')}")

st.sidebar.caption('BatiSuivi • Streamlit')
