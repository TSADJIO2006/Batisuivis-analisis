from flask import abort, Flask, render_template, request, redirect, url_for, flash, session, g
import sqlite3
from pathlib import Path
from datetime import datetime, date
import pandas as pd
import os
import sys
import statistics
import uuid
from werkzeug.utils import secure_filename
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "batisuivi.db"
DATA_DIR = BASE_DIR / "data"

app = Flask(__name__)
app.secret_key = os.environ.get("BATISUIVI_SECRET_KEY") or os.urandom(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax", MAX_CONTENT_LENGTH=8 * 1024 * 1024)
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_PHOTO_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            full_name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'maitre_ouvrage' CHECK(role IN ('admin','collecteur','maitre_ouvrage')),
            profile_photo TEXT DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS site (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            location TEXT NOT NULL,
            manager TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            budget REAL NOT NULL CHECK (budget >= 0)
        );
        CREATE TABLE IF NOT EXISTS progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            site_id INTEGER NOT NULL,
            work_date TEXT NOT NULL,
            activity TEXT NOT NULL,
            planned_qty REAL NOT NULL CHECK (planned_qty >= 0),
            actual_qty REAL NOT NULL CHECK (actual_qty >= 0),
            unit TEXT NOT NULL,
            workers INTEGER NOT NULL CHECK (workers >= 0),
            hours REAL NOT NULL CHECK (hours >= 0),
            notes TEXT DEFAULT '',
            FOREIGN KEY(site_id) REFERENCES site(id)
        );
        CREATE TABLE IF NOT EXISTS materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            site_id INTEGER NOT NULL,
            record_date TEXT NOT NULL,
            material TEXT NOT NULL,
            opening_stock REAL NOT NULL CHECK (opening_stock >= 0),
            received_qty REAL NOT NULL CHECK (received_qty >= 0),
            used_qty REAL NOT NULL CHECK (used_qty >= 0),
            unit TEXT NOT NULL,
            unit_price REAL NOT NULL CHECK (unit_price >= 0),
            FOREIGN KEY(site_id) REFERENCES site(id)
        );
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            site_id INTEGER NOT NULL,
            expense_date TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT NOT NULL,
            amount REAL NOT NULL CHECK (amount >= 0),
            FOREIGN KEY(site_id) REFERENCES site(id)
        );
        CREATE TABLE IF NOT EXISTS incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            site_id INTEGER NOT NULL,
            incident_date TEXT NOT NULL,
            category TEXT NOT NULL,
            hours_lost REAL NOT NULL CHECK (hours_lost >= 0),
            description TEXT NOT NULL,
            FOREIGN KEY(site_id) REFERENCES site(id)
        );
        CREATE TABLE IF NOT EXISTS planning (
            id INTEGER PRIMARY KEY AUTOINCREMENT, site_id INTEGER NOT NULL,
            title TEXT NOT NULL, start_date TEXT NOT NULL, end_date TEXT NOT NULL,
            responsible TEXT DEFAULT '', status TEXT NOT NULL DEFAULT 'À faire', notes TEXT DEFAULT '',
            validated INTEGER NOT NULL DEFAULT 0, validated_by TEXT DEFAULT '', validated_at TEXT DEFAULT '',
            FOREIGN KEY(site_id) REFERENCES site(id)
        );
        CREATE TABLE IF NOT EXISTS staff (
            id INTEGER PRIMARY KEY AUTOINCREMENT, site_id INTEGER NOT NULL,
            full_name TEXT NOT NULL, job_title TEXT NOT NULL, phone TEXT DEFAULT '',
            monthly_salary REAL NOT NULL CHECK(monthly_salary >= 0), active INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY(site_id) REFERENCES site(id)
        );
        CREATE TABLE IF NOT EXISTS payroll (
            id INTEGER PRIMARY KEY AUTOINCREMENT, staff_id INTEGER NOT NULL,
            site_id INTEGER NOT NULL, payroll_month TEXT NOT NULL, amount REAL NOT NULL,
            expense_id INTEGER, UNIQUE(staff_id, payroll_month),
            FOREIGN KEY(staff_id) REFERENCES staff(id), FOREIGN KEY(site_id) REFERENCES site(id),
            FOREIGN KEY(expense_id) REFERENCES expenses(id)
        );
        CREATE TABLE IF NOT EXISTS site_photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, site_id INTEGER NOT NULL,
            photo_path TEXT NOT NULL, caption TEXT DEFAULT '', photo_date TEXT NOT NULL,
            uploaded_by TEXT DEFAULT '', FOREIGN KEY(site_id) REFERENCES site(id)
        );
        CREATE TABLE IF NOT EXISTS quotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT, site_id INTEGER NOT NULL,
            quote_date TEXT NOT NULL, designation TEXT NOT NULL,
            quantity REAL NOT NULL CHECK(quantity >= 0), unit TEXT NOT NULL,
            unit_price REAL NOT NULL CHECK(unit_price >= 0), notes TEXT DEFAULT '',
            FOREIGN KEY(site_id) REFERENCES site(id)
        );
        """)
        # Migration douce des bases créées par les versions précédentes.
        user_cols = {r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
        if "profile_photo" not in user_cols:
            conn.execute("ALTER TABLE users ADD COLUMN profile_photo TEXT DEFAULT ''")
        planning_cols = {r[1] for r in conn.execute("PRAGMA table_info(planning)").fetchall()}
        for col, definition in [("validated", "INTEGER NOT NULL DEFAULT 0"), ("validated_by", "TEXT DEFAULT ''"), ("validated_at", "TEXT DEFAULT ''")]:
            if col not in planning_cols:
                conn.execute(f"ALTER TABLE planning ADD COLUMN {col} {definition}")
        # Migration rétrocompatible : chaque dépense peut être rattachée à une phase.
        expense_cols = {r[1] for r in conn.execute("PRAGMA table_info(expenses)").fetchall()}
        if "activity" not in expense_cols:
            conn.execute("ALTER TABLE expenses ADD COLUMN activity TEXT NOT NULL DEFAULT ''")


def seed_demo_data():
    """Load coherent synthetic data once, only if the database is empty."""
    with get_db() as conn:
        existing = conn.execute("SELECT COUNT(*) FROM site").fetchone()[0]
        if existing:
            seed_additional_demo_sites(conn)
            # Dates standardisées pour les trois chantiers de démonstration uniquement.
            demo_names = [
                "Construction d'un bâtiment R+2 (démonstration)",
                "Construction d'une route en béton bitumineux",
                "Construction d'un bâtiment scolaire R+1",
            ]
            conn.executemany("UPDATE site SET start_date='2026-09-01', end_date='2026-11-30' WHERE name=?", [(n,) for n in demo_names])
        else:
            cur = conn.execute(
            """INSERT INTO site(name, location, manager, start_date, end_date, budget)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ("Construction d'un bâtiment R+2 (démonstration)", "Yaoundé, Cameroun",
             "Responsable de démonstration", "2026-09-01", "2026-11-30", 60000000)
        )
            site_id = cur.lastrowid

            progress_rows = [
                ("2026-09-01", "Fouilles", 12, 10, "m³", 5, 7, "Sol plus compact que prévu"),
                ("2026-09-02", "Fouilles", 10, 10, "m³", 5, 7, ""),
                ("2026-09-03", "Béton de propreté", 8, 6, "m³", 6, 6, "Livraison tardive"),
                ("2026-09-04", "Béton de propreté", 6, 6, "m³", 6, 6, ""),
                ("2026-09-05", "Ferraillage des fondations", 350, 300, "kg", 4, 7, "Manque de barres de diamètre prévu"),
                ("2026-09-07", "Ferraillage des fondations", 250, 260, "kg", 5, 7, ""),
                ("2026-09-08", "Coffrage des fondations", 40, 35, "m²", 4, 6, ""),
                ("2026-09-09", "Coffrage des fondations", 30, 30, "m²", 4, 6, ""),
                ("2026-09-10", "Bétonnage des fondations", 12, 10, "m³", 7, 8, "Pluie en fin de journée"),
                ("2026-09-11", "Bétonnage des fondations", 8, 8, "m³", 7, 8, ""),
                ("2026-09-12", "Maçonnerie du soubassement", 24, 20, "m²", 6, 7, ""),
                ("2026-09-14", "Maçonnerie du soubassement", 20, 22, "m²", 6, 7, ""),
                ("2026-09-15", "Remblai", 18, 15, "m³", 4, 6, "Compactage supplémentaire"),
                ("2026-09-16", "Remblai", 12, 12, "m³", 4, 6, ""),
                ("2026-09-17", "Dallage", 35, 30, "m²", 8, 8, "Attente de béton"),
                ("2026-09-18", "Dallage", 25, 26, "m²", 8, 8, ""),
                ("2026-09-19", "Élévation des murs RDC", 28, 24, "m²", 7, 7, ""),
                ("2026-09-21", "Élévation des murs RDC", 30, 31, "m²", 7, 7, ""),
                ("2026-09-22", "Poteaux RDC", 6, 5, "unité", 5, 8, "Contrôle du coffrage"),
                ("2026-09-23", "Poteaux RDC", 4, 4, "unité", 5, 8, ""),
            ]
            # Relevés synthétiques des phases suivantes : elles figurent dans le dénominateur
            # d'avancement, même si elles ne sont pas encore commencées. Cela évite un faux 90 %.
            progress_rows.extend([
                ("2026-10-01", "Élévation des murs RDC", 120, 34, "m²", 8, 8, "Démarrage des murs après dallage"),
                ("2026-10-04", "Poteaux RDC", 12, 5, "unité", 6, 8, "Ferraillage et coffrage partiels"),
                ("2026-10-08", "Poutres et dalle du RDC", 90, 0, "m²", 0, 0, "Phase planifiée, non démarrée"),
                ("2026-10-15", "Élévation des murs étage", 180, 0, "m²", 0, 0, "Phase planifiée, non démarrée"),
                ("2026-10-25", "Escalier et dalle étage", 75, 0, "m²", 0, 0, "Phase planifiée, non démarrée"),
                ("2026-11-05", "Charpente et couverture", 160, 0, "m²", 0, 0, "Phase planifiée, non démarrée"),
                ("2026-11-15", "Plomberie et électricité", 1, 0, "lot", 0, 0, "Phase planifiée, non démarrée"),
                ("2026-11-25", "Enduits, revêtements et peinture", 1, 0, "lot", 0, 0, "Phase planifiée, non démarrée"),
                ("2026-12-05", "Menuiseries, contrôles et réception", 1, 0, "lot", 0, 0, "Phase planifiée, non démarrée"),
            ])
            conn.executemany(
                """INSERT INTO progress(site_id, work_date, activity, planned_qty, actual_qty,
                   unit, workers, hours, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [(site_id, *r) for r in progress_rows]
            )

            material_rows = [
                ("2026-09-01", "Ciment", 0, 100, 18, "sac", 5000),
                ("2026-09-03", "Ciment", 82, 50, 25, "sac", 5000),
                ("2026-09-07", "Ciment", 107, 40, 30, "sac", 5100),
                ("2026-09-11", "Ciment", 117, 30, 28, "sac", 5100),
                ("2026-09-15", "Ciment", 119, 25, 20, "sac", 5100),
                ("2026-09-19", "Ciment", 124, 30, 22, "sac", 5100),
                ("2026-09-01", "Sable", 0, 12, 3, "m³", 18000),
                ("2026-09-05", "Sable", 9, 8, 4, "m³", 18000),
                ("2026-09-10", "Sable", 13, 5, 5, "m³", 19000),
                ("2026-09-15", "Sable", 13, 6, 4, "m³", 19000),
                ("2026-09-20", "Sable", 15, 4, 3, "m³", 19000),
                ("2026-09-02", "Gravier", 0, 10, 2, "m³", 22000),
                ("2026-09-08", "Gravier", 8, 6, 3, "m³", 22000),
                ("2026-09-12", "Gravier", 11, 5, 4, "m³", 23000),
                ("2026-09-18", "Gravier", 12, 6, 5, "m³", 23000),
                ("2026-09-22", "Gravier", 13, 4, 2, "m³", 23000),
                ("2026-09-04", "Fer à béton HA10", 0, 450, 120, "kg", 850),
                ("2026-09-09", "Fer à béton HA10", 330, 250, 160, "kg", 850),
                ("2026-09-14", "Fer à béton HA10", 420, 200, 180, "kg", 875),
                ("2026-09-20", "Fer à béton HA10", 440, 150, 140, "kg", 875),
            ]
            conn.executemany(
                """INSERT INTO materials(site_id, record_date, material, opening_stock,
                   received_qty, used_qty, unit, unit_price) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                [(site_id, *r) for r in material_rows]
            )

            expense_rows = [
                ("2026-09-01", "Matériaux", "Ciment et livraison", 500000),
                ("2026-09-02", "Main-d'œuvre", "Équipe de terrassement", 125000),
                ("2026-09-03", "Transport", "Transport du sable", 65000),
                ("2026-09-04", "Matériaux", "Sable et gravier", 210000),
                ("2026-09-05", "Main-d'œuvre", "Ferraillage des fondations", 150000),
                ("2026-09-07", "Matériaux", "Acier HA10", 382500),
                ("2026-09-08", "Matériel", "Location petit matériel", 80000),
                ("2026-09-10", "Main-d'œuvre", "Bétonnage", 180000),
                ("2026-09-11", "Matériaux", "Ciment", 153000),
                ("2026-09-12", "Transport", "Évacuation déblais", 95000),
                ("2026-09-14", "Main-d'œuvre", "Maçonnerie soubassement", 160000),
                ("2026-09-15", "Matériaux", "Ciment et sable", 220000),
                ("2026-09-17", "Matériel", "Location compacteur", 110000),
                ("2026-09-18", "Main-d'œuvre", "Équipe dallage", 190000),
                ("2026-09-20", "Matériaux", "Acier et ciment", 340000),
                ("2026-09-22", "Main-d'œuvre", "Élévation RDC", 175000),
            ]
            expense_rows.extend([
                ("2026-09-23", "Matériaux", "Achat complémentaire ciment et acier", 1850000),
                ("2026-09-25", "Main-d'œuvre", "Équipe maçonnerie et poteaux", 720000),
                ("2026-09-28", "Matériel", "Location échafaudage et coffrage", 480000),
                ("2026-10-02", "Matériaux", "Sable, gravier et ciment", 1250000),
                ("2026-10-05", "Transport", "Livraison matériaux sur chantier", 240000),
                ("2026-10-10", "Main-d'œuvre", "Équipe ferraillage et maçonnerie", 680000),
            ])
            conn.executemany(
                """INSERT INTO expenses(site_id, expense_date, category, description, amount)
                   VALUES (?, ?, ?, ?, ?)""",
                [(site_id, *r) for r in expense_rows]
            )

            incident_rows = [
                ("2026-09-03", "Livraison tardive", 3, "Le camion de ciment est arrivé après l'heure prévue."),
                ("2026-09-05", "Manque de matériaux", 2, "Diamètres d'acier prévus non disponibles immédiatement."),
                ("2026-09-10", "Météo", 2.5, "Pluie ayant interrompu le bétonnage."),
                ("2026-09-15", "Problème technique", 1.5, "Temps supplémentaire pour le compactage du remblai."),
                ("2026-09-17", "Approvisionnement", 2, "Attente de la livraison de béton."),
            ]
            conn.executemany(
                """INSERT INTO incidents(site_id, incident_date, category, hours_lost, description)
                   VALUES (?, ?, ?, ?, ?)""",
                [(site_id, *r) for r in incident_rows]
            )
            seed_additional_demo_sites(conn)
    seed_demo_quotes_and_staff()
    ensure_demo_coherence_for_existing_sites()


def ensure_demo_coherence_for_existing_sites():
    """Complète sans doublons les anciens jeux de démonstration déjà présents dans SQLite."""
    future = {
        "Construction d'un bâtiment R+2 (démonstration)": [
            ("2026-10-01", "Élévation des murs RDC", 120, 34, "m²", 8, 8, "Démarrage des murs après dallage"),
            ("2026-10-08", "Poutres et dalle du RDC", 90, 0, "m²", 0, 0, "Phase planifiée, non démarrée"),
            ("2026-10-15", "Élévation des murs étage", 180, 0, "m²", 0, 0, "Phase planifiée, non démarrée"),
            ("2026-10-25", "Escalier et dalle étage", 75, 0, "m²", 0, 0, "Phase planifiée, non démarrée"),
            ("2026-11-05", "Charpente et couverture", 160, 0, "m²", 0, 0, "Phase planifiée, non démarrée"),
            ("2026-11-15", "Plomberie et électricité", 1, 0, "lot", 0, 0, "Phase planifiée, non démarrée"),
            ("2026-11-25", "Enduits, revêtements et peinture", 1, 0, "lot", 0, 0, "Phase planifiée, non démarrée"),
            ("2026-12-05", "Menuiseries, contrôles et réception", 1, 0, "lot", 0, 0, "Phase planifiée, non démarrée"),
        ],
        "Construction d'une route en béton bitumineux": [
            ("2026-10-01", "Enrobé bitumineux", 3500, 0, "m²", 0, 0, "Phase planifiée"),
            ("2026-10-15", "Signalisation horizontale et verticale", 1, 0, "lot", 0, 0, "Phase planifiée"),
            ("2026-11-01", "Accotements et finitions", 1, 0, "lot", 0, 0, "Phase planifiée"),
            ("2027-01-15", "Contrôle qualité et réception", 1, 0, "lot", 0, 0, "Phase planifiée"),
        ],
        "Construction d'un bâtiment scolaire R+1": [
            ("2026-10-01", "Élévation des murs RDC", 150, 0, "m²", 0, 0, "Phase planifiée"),
            ("2026-10-15", "Poutres et dalle", 180, 0, "m²", 0, 0, "Phase planifiée"),
            ("2026-11-01", "Charpente et couverture", 260, 0, "m²", 0, 0, "Phase planifiée"),
            ("2026-11-15", "Plomberie et électricité", 1, 0, "lot", 0, 0, "Phase planifiée"),
            ("2026-12-01", "Enduits, peinture et revêtements", 1, 0, "lot", 0, 0, "Phase planifiée"),
            ("2027-01-20", "Contrôle qualité et réception", 1, 0, "lot", 0, 0, "Phase planifiée"),
        ]
    }
    extra_costs = {
        "Construction d'un bâtiment R+2 (démonstration)": [
            ("2026-09-23", "Matériaux", "Achat complémentaire ciment et acier", 1850000),
            ("2026-09-25", "Main-d'œuvre", "Équipe maçonnerie et poteaux", 720000),
            ("2026-09-28", "Matériel", "Location échafaudage et coffrage", 480000),
            ("2026-10-02", "Matériaux", "Sable, gravier et ciment", 1250000),
            ("2026-10-05", "Transport", "Livraison matériaux sur chantier", 240000),
            ("2026-10-10", "Main-d'œuvre", "Équipe ferraillage et maçonnerie", 680000),
            ("2026-10-12", "Matériaux", "Acompte matériaux pour élévation RDC", 3200000),
            ("2026-10-16", "Main-d'œuvre", "Paie équipe chantier et coffreurs", 1450000),
            ("2026-10-20", "Matériel", "Location bétonnière et échafaudage", 950000),
        ],
        "Construction d'une route en béton bitumineux": [
            ("2026-09-24", "Matériaux", "Approvisionnement complémentaire en grave", 2350000),
            ("2026-09-26", "Main-d'œuvre", "Équipe de compactage et caniveaux", 850000),
            ("2026-10-01", "Matériel", "Location d'engins et entretien", 1250000),
            ("2026-10-05", "Transport", "Transport de matériaux", 620000),
            ("2026-10-08", "Matériaux", "Grave et granulats pour couche de base", 4200000),
            ("2026-10-12", "Main-d'œuvre", "Équipe terrassement et assainissement", 1850000),
            ("2026-10-18", "Matériel", "Carburant et maintenance des engins", 1250000),
        ],
        "Construction d'un bâtiment scolaire R+1": [
            ("2026-09-28", "Matériaux", "Acier, ciment et agrégats", 1450000),
            ("2026-10-02", "Main-d'œuvre", "Équipe fondations et maçonnerie", 460000),
            ("2026-10-06", "Matériel", "Location coffrage et bétonnière", 320000),
            ("2026-10-10", "Matériaux", "Achat complémentaire ciment et acier", 2850000),
            ("2026-10-15", "Main-d'œuvre", "Équipe maçonnerie et ferraillage", 1250000),
            ("2026-10-20", "Matériel", "Location coffrage et étaiement", 680000),
        ]
    }
    with get_db() as conn:
        sites = conn.execute("SELECT id,name FROM site").fetchall()
        for site in sites:
            for row in future.get(site["name"], []):
                if not conn.execute("SELECT 1 FROM progress WHERE site_id=? AND activity=?", (site["id"], row[1])).fetchone():
                    conn.execute("INSERT INTO progress(site_id,work_date,activity,planned_qty,actual_qty,unit,workers,hours,notes) VALUES (?,?,?,?,?,?,?,?,?)", (site["id"], *row))
            for row in extra_costs.get(site["name"], []):
                if not conn.execute("SELECT 1 FROM expenses WHERE site_id=? AND description=?", (site["id"], row[2])).fetchone():
                    conn.execute("INSERT INTO expenses(site_id,expense_date,category,description,amount) VALUES (?,?,?,?,?)", (site["id"], *row))


def seed_demo_quotes_and_staff():
    """Ajoute un devis estimatif et une équipe de démonstration à chaque chantier, une seule fois."""
    quote_templates = {
        "Construction d'un bâtiment R+2 (démonstration)": [
            ("2026-09-01", "Installation et études", 1, "lot", 2500000),
            ("2026-09-01", "Terrassement et fondations", 1, "lot", 8500000),
            ("2026-09-01", "Structure béton armé et maçonnerie", 1, "lot", 22000000),
            ("2026-09-01", "Charpente et couverture", 1, "lot", 6500000),
            ("2026-09-01", "Plomberie et électricité", 1, "lot", 5500000),
            ("2026-09-01", "Enduits, revêtements, menuiseries et peinture", 1, "lot", 10500000),
            ("2026-09-01", "Contrôles, nettoyage et réception", 1, "lot", 2500000),
        ],
        "Construction d'une route en béton bitumineux": [
            ("2026-09-05", "Installation et études", 1, "lot", 4500000),
            ("2026-09-05", "Terrassement et couche de forme", 1, "lot", 16000000),
            ("2026-09-05", "Fondation et couche de base", 1, "lot", 19000000),
            ("2026-09-05", "Revêtement bitumineux", 1, "lot", 26000000),
            ("2026-09-05", "Caniveaux et assainissement", 1, "lot", 10500000),
            ("2026-09-05", "Signalisation et réception", 1, "lot", 6500000),
        ],
        "Construction d'un bâtiment scolaire R+1": [
            ("2026-09-10", "Études et installation", 1, "lot", 2500000),
            ("2026-09-10", "Fondations et soubassement", 1, "lot", 8500000),
            ("2026-09-10", "Structure et maçonnerie", 1, "lot", 17000000),
            ("2026-09-10", "Charpente et couverture", 1, "lot", 5500000),
            ("2026-09-10", "Plomberie et électricité", 1, "lot", 4500000),
            ("2026-09-10", "Finitions et réception", 1, "lot", 9000000),
        ],
    }
    with get_db() as conn:
        for site in conn.execute("SELECT id,name,manager FROM site").fetchall():
            if conn.execute("SELECT COUNT(*) FROM quotes WHERE site_id=?", (site["id"],)).fetchone()[0] == 0:
                rows = quote_templates.get(site["name"], [(date.today().isoformat(), "Travaux prévisionnels à détailler", 1, "lot", float(conn.execute("SELECT budget FROM site WHERE id=?", (site["id"],)).fetchone()[0]))])
                conn.executemany("INSERT INTO quotes(site_id,quote_date,designation,quantity,unit,unit_price,notes) VALUES (?,?,?,?,?,?,?)",
                                 [(site["id"], *r, "Devis synthétique de démonstration — à adapter au projet") for r in rows])
            # Équipe de démonstration complète : ajoute seulement les fonctions absentes.
            staff_templates = [
                ("Ingénieur travaux", "Ingénieur de travaux", 500000),
                ("Chef de chantier", "Chef de chantier", 350000),
                ("Technicien génie civil", "Technicien génie civil", 250000),
                ("Topographe", "Topographe / géomètre", 280000),
                ("Responsable HSE", "Responsable sécurité et environnement", 250000),
                ("Chef d'équipe maçonnerie", "Chef d'équipe", 250000),
                ("Maçon qualifié 1", "Maçon", 180000),
                ("Maçon qualifié 2", "Maçon", 180000),
                ("Ferrailleur 1", "Ferrailleur", 175000),
                ("Coffreur 1", "Coffreur-boiseur", 175000),
                ("Électricien", "Électricien bâtiment", 200000),
                ("Plombier", "Plombier sanitaire", 200000),
                ("Manœuvre 1", "Manœuvre", 120000),
                ("Manœuvre 2", "Manœuvre", 120000),
                ("Magasinier", "Magasinier de chantier", 160000),
                ("Conducteur d'engins", "Conducteur d'engins", 240000),
                ("Chauffeur camion", "Chauffeur poids lourd", 200000),
            ]
            existing_titles = {r[0].casefold() for r in conn.execute(
                "SELECT job_title FROM staff WHERE site_id=?", (site["id"],)).fetchall()}
            for full_name, job_title, salary in staff_templates:
                if job_title.casefold() not in existing_titles:
                    conn.execute("INSERT INTO staff(site_id,full_name,job_title,phone,monthly_salary,active) VALUES (?,?,?,?,?,1)",
                                 (site["id"], full_name, job_title, "", salary))
                    existing_titles.add(job_title.casefold())


def seed_additional_demo_sites(conn):
    """Ajoute deux chantiers synthétiques si absents, sans dupliquer les données."""
    projects = [
        {
            "name": "Construction d'une route en béton bitumineux",
            "location": "Douala, Cameroun", "manager": "Ingénieur travaux - Équipe B",
            "start": "2026-09-01", "end": "2026-11-30", "budget": 85000000,
            "progress": [
                ("2026-09-05","Installation de chantier",100,100,"%",8,8,"Base vie installée"),
                ("2026-09-07","Décapage",120,110,"m³",10,8,"Sol humide sur une zone"),
                ("2026-09-09","Terrassement",180,165,"m³",12,8,"Rendement légèrement inférieur"),
                ("2026-09-11","Couche de forme",150,150,"m³",10,8,"Conforme au programme"),
                ("2026-09-13","Compactage",900,850,"m²",9,7,"Contrôle de densité à reprendre"),
                ("2026-09-15","Couche de fondation",140,125,"m³",11,8,"Livraison de grave retardée"),
                ("2026-09-17","Caniveaux",65,60,"m",7,7,"Avancement proche de la cible"),
                ("2026-09-19","Couche de base",120,105,"m³",12,8,"Approvisionnement partiel"),
                ("2026-09-21","Imprégnation",800,760,"m²",8,6,"Conditions météo variables"),
                ("2026-09-23","Préparation enrobé",500,520,"m²",10,7,"Bonne mobilisation des équipes")],
            "expenses": [("2026-09-05","Matériel","Location niveleuse",950000),("2026-09-07","Main-d'œuvre","Équipe terrassement",420000),("2026-09-09","Matériaux","Grave latéritique",1250000),("2026-09-11","Transport","Transport des agrégats",360000),("2026-09-15","Matériaux","Couche de fondation",980000),("2026-09-19","Matériel","Compacteur et rouleau",650000),("2026-09-22","Main-d'œuvre","Équipe caniveaux",510000)],
            "materials": [("2026-09-06","Grave latéritique",0,180,65,"m³",12000),("2026-09-10","Grave latéritique",115,120,80,"m³",12000),("2026-09-15","Ciment",0,90,35,"sac",5000),("2026-09-20","Granulats",0,150,90,"m³",22000)],
            "incidents": [("2026-09-08","Météo",3,"Pluie ayant ralenti le terrassement"),("2026-09-15","Approvisionnement",2,"Livraison partielle des agrégats")]
        },
        {
            "name": "Construction d'un bâtiment scolaire R+1",
            "location": "Bafoussam, Cameroun", "manager": "Conducteur de travaux - Équipe C",
            "start": "2026-09-01", "end": "2026-11-30", "budget": 52000000,
            "progress": [
                ("2026-09-10","Implantation",100,100,"%",4,5,"Axes contrôlés"),
                ("2026-09-12","Fouilles",45,42,"m³",6,7,"Terrain rocheux par endroits"),
                ("2026-09-14","Béton de propreté",12,12,"m³",5,6,"Conforme"),
                ("2026-09-16","Ferraillage fondations",420,390,"kg",5,7,"Quelques barres à compléter"),
                ("2026-09-18","Coffrage fondations",55,50,"m²",5,7,"Équipe en apprentissage"),
                ("2026-09-20","Bétonnage fondations",18,16,"m³",8,8,"Interruption courte"),
                ("2026-09-22","Maçonnerie soubassement",38,40,"m²",6,7,"Rattrapage de l'écart"),
                ("2026-09-24","Remblai",30,28,"m³",5,6,"Compactage en cours"),
                ("2026-09-26","Dallage",70,62,"m²",8,8,"Béton livré en deux rotations"),
                ("2026-09-28","Poteaux RDC",8,8,"unité",5,8,"Contrôle qualité validé")],
            "expenses": [("2026-09-10","Matériaux","Ciment et agrégats",640000),("2026-09-12","Main-d'œuvre","Équipe de fouilles",180000),("2026-09-14","Matériel","Location bétonnière",90000),("2026-09-16","Matériaux","Acier pour fondations",520000),("2026-09-20","Main-d'œuvre","Bétonnage fondations",260000),("2026-09-22","Transport","Évacuation déblais",120000),("2026-09-26","Matériaux","Ciment pour dallage",390000)],
            "materials": [("2026-09-11","Ciment",0,120,32,"sac",5000),("2026-09-15","Fer à béton HA10",0,500,230,"kg",850),("2026-09-20","Sable",0,18,7,"m³",18000),("2026-09-25","Gravier",0,16,8,"m³",22000)],
            "incidents": [("2026-09-12","Sol difficile",2,"Poche rocheuse dans les fouilles"),("2026-09-20","Matériel",1,"Arrêt temporaire de la bétonnière")]
        }
    ]
    for project in projects:
        found = conn.execute("SELECT id FROM site WHERE name=?", (project["name"],)).fetchone()
        if found:
            continue
        cur = conn.execute("INSERT INTO site(name,location,manager,start_date,end_date,budget) VALUES (?,?,?,?,?,?)",
            (project["name"],project["location"],project["manager"],project["start"],project["end"],project["budget"]))
        sid = cur.lastrowid
        # Compléter les activités futures avec des quantités prévues et zéro réalisé.
        # Les indicateurs reflètent donc l'ensemble du cycle de travaux, pas uniquement les tâches déjà relevées.
        future_by_project = {
            "Construction d'une route en béton bitumineux": [
                ("2026-09-25", "Couche de base", 300, 0, "m³", 0, 0, "Quantité restante planifiée"),
                ("2026-10-01", "Enrobé bitumineux", 3500, 0, "m²", 0, 0, "Phase planifiée"),
                ("2026-10-15", "Signalisation horizontale et verticale", 1, 0, "lot", 0, 0, "Phase planifiée"),
                ("2026-11-01", "Accotements et finitions", 1, 0, "lot", 0, 0, "Phase planifiée"),
                ("2027-01-15", "Contrôle qualité et réception", 1, 0, "lot", 0, 0, "Phase planifiée"),
            ],
            "Construction d'un bâtiment scolaire R+1": [
                ("2026-10-01", "Élévation des murs RDC", 150, 0, "m²", 0, 0, "Phase planifiée"),
                ("2026-10-15", "Poutres et dalle", 180, 0, "m²", 0, 0, "Phase planifiée"),
                ("2026-11-01", "Charpente et couverture", 260, 0, "m²", 0, 0, "Phase planifiée"),
                ("2026-11-15", "Plomberie et électricité", 1, 0, "lot", 0, 0, "Phase planifiée"),
                ("2026-12-01", "Enduits, peinture et revêtements", 1, 0, "lot", 0, 0, "Phase planifiée"),
                ("2027-01-20", "Contrôle qualité et réception", 1, 0, "lot", 0, 0, "Phase planifiée"),
            ]
        }
        project_progress = list(project["progress"]) + future_by_project.get(project["name"], [])
        conn.executemany("INSERT INTO progress(site_id,work_date,activity,planned_qty,actual_qty,unit,workers,hours,notes) VALUES (?,?,?,?,?,?,?,?,?)", [(sid,*r) for r in project_progress])
        extra_expenses = {
            "Construction d'une route en béton bitumineux": [
                ("2026-09-24", "Matériaux", "Approvisionnement complémentaire en grave", 2350000),
                ("2026-09-26", "Main-d'œuvre", "Équipe de compactage et caniveaux", 850000),
                ("2026-10-01", "Matériel", "Location d'engins et entretien", 1250000),
                ("2026-10-05", "Transport", "Transport de matériaux", 620000),
            ],
            "Construction d'un bâtiment scolaire R+1": [
                ("2026-09-28", "Matériaux", "Acier, ciment et agrégats", 1450000),
                ("2026-10-02", "Main-d'œuvre", "Équipe fondations et maçonnerie", 460000),
                ("2026-10-06", "Matériel", "Location coffrage et bétonnière", 320000),
            ]
        }
        project_expenses = list(project["expenses"]) + extra_expenses.get(project["name"], [])
        conn.executemany("INSERT INTO expenses(site_id,expense_date,category,description,amount) VALUES (?,?,?,?,?)", [(sid,*r) for r in project_expenses])
        conn.executemany("INSERT INTO materials(site_id,record_date,material,opening_stock,received_qty,used_qty,unit,unit_price) VALUES (?,?,?,?,?,?,?,?)", [(sid,*r) for r in project["materials"]])
        conn.executemany("INSERT INTO incidents(site_id,incident_date,category,hours_lost,description) VALUES (?,?,?,?,?)", [(sid,*r) for r in project["incidents"]])
        conn.executemany("INSERT INTO staff(site_id,full_name,job_title,phone,monthly_salary,active) VALUES (?,?,?,?,?,1)", [
            (sid,"Chef d'équipe", "Chef de chantier", "", 280000), (sid,"Ouvrier qualifié", "Maçon / ouvrier", "", 180000)])


def login_required(view):
    """Authentification désactivée pour la démonstration pédagogique locale."""
    return view


def admin_required(view):
    """Toutes les fonctions sont accessibles sans compte dans cette version."""
    return view


def collection_required(view):
    """La collecte est accessible directement, sans connexion."""
    return view


@app.before_request
def load_logged_in_user():
    # Profil local par défaut : aucune page de connexion n'est nécessaire.
    init_db()
    with get_db() as conn:
        user = conn.execute("SELECT id, username, full_name, role, profile_photo, created_at FROM users ORDER BY id LIMIT 1").fetchone()
        if user is None:
            conn.execute("INSERT INTO users(username, full_name, password_hash, role) VALUES (?, ?, ?, 'admin')",
                         ('local', 'Utilisateur', generate_password_hash(uuid.uuid4().hex)))
            user = conn.execute("SELECT id, username, full_name, role, profile_photo, created_at FROM users ORDER BY id LIMIT 1").fetchone()
    g.user = dict(user)
    g.user['role'] = 'admin'  # accès complet au prototype local sans gestion des rôles
    session['user_id'] = user['id']
    session['full_name'] = user['full_name']


@app.context_processor
def inject_user():
    return {"current_user": getattr(g, "user", None)}


@app.route("/initialiser-admin", methods=["GET", "POST"])
@app.route("/reinitialiser-admin", methods=["GET", "POST"])
@app.route("/connexion", methods=["GET", "POST"])
@app.route("/deconnexion", methods=["GET", "POST"])
def login_disabled():
    """Redirige les anciennes URL d'authentification vers l'application."""
    return redirect(url_for("index"))


@app.route("/utilisateurs", methods=["GET", "POST"])
@admin_required
def users_page():
    init_db()
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        full_name = request.form.get("full_name", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "maitre_ouvrage")
        if len(username) < 3 or not full_name or len(password) < 10 or role not in ("admin", "collecteur", "maitre_ouvrage"):
            flash("Identifiant : 3 caractères minimum ; mot de passe : 10 caractères minimum ; vérifie le rôle et les autres champs.", "error")
        else:
            try:
                with get_db() as conn:
                    conn.execute("INSERT INTO users(username, full_name, password_hash, role) VALUES (?, ?, ?, ?)",
                                 (username, full_name, generate_password_hash(password), role))
                flash("Compte créé avec succès.", "success")
                return redirect(url_for("users_page"))
            except sqlite3.IntegrityError:
                flash("Ce nom d'utilisateur existe déjà.", "error")
    with get_db() as conn:
        users = conn.execute("SELECT id, username, full_name, role, created_at FROM users ORDER BY id").fetchall()
    return render_template("users.html", users=users, page_title="Gestion des comptes", active_page="users", today=date.today().isoformat())


def dashboard_data(site_id=None):
    with get_db() as conn:
        sites = conn.execute("SELECT * FROM site ORDER BY id DESC").fetchall()
        if not sites:
            return {"sites": [], "site": None, "stats": {}, "progress": [], "expenses_by_category": [],
                    "daily_progress": [], "materials": [], "incidents": [], "recent_progress": []}
        selected_id = site_id or sites[0]["id"]
        site = conn.execute("SELECT * FROM site WHERE id=?", (selected_id,)).fetchone()
        if not site:
            site = sites[0]
            selected_id = site["id"]

        # Le planning est créé/synchronisé avant de calculer les indicateurs :
        # le tableau de bord et l'onglet Planning partagent ainsi la même source.
        ensure_planning_seed(selected_id, conn)
        progress = conn.execute("SELECT * FROM progress WHERE site_id=? ORDER BY work_date DESC, id DESC",
                                (selected_id,)).fetchall()
        planning_tasks = conn.execute("SELECT * FROM planning WHERE site_id=? ORDER BY start_date, id",
                                      (selected_id,)).fetchall()
        expenses = conn.execute("SELECT * FROM expenses WHERE site_id=? ORDER BY expense_date DESC, id DESC",
                                (selected_id,)).fetchall()
        materials = conn.execute("SELECT * FROM materials WHERE site_id=? ORDER BY record_date DESC, id DESC",
                                 (selected_id,)).fetchall()
        incidents = conn.execute("SELECT * FROM incidents WHERE site_id=? ORDER BY incident_date DESC, id DESC",
                                 (selected_id,)).fetchall()

        total_expenses = sum(r["amount"] for r in expenses)
        # Dépenses par phase : les anciennes dépenses sans activité restent visibles sous
        # « Non affectées », sans être attribuées artificiellement à une tâche.
        expenses_by_activity_map = {}
        for expense in expenses:
            phase = (expense["activity"] or "").strip() or "Non affectées"
            expenses_by_activity_map[phase] = expenses_by_activity_map.get(phase, 0.0) + float(expense["amount"] or 0)
        expenses_by_activity = sorted(expenses_by_activity_map.items(), key=lambda item: item[1], reverse=True)
        # Quantités cumulées affichées à titre informatif (les unités ne sont pas additionnées
        # pour calculer le pourcentage global).
        planned = sum(float(r["planned_qty"] or 0) for r in progress)
        actual = sum(float(r["actual_qty"] or 0) for r in progress)

        def norm(value):
            import unicodedata
            value = unicodedata.normalize("NFKD", str(value or "").casefold())
            return "".join(ch for ch in value if not unicodedata.combining(ch)).replace("’", "'").strip()

        # Liens entre les libellés des relevés de suivi et les phases du planning.
        aliases = {
            "fouilles": ("fouille", "excavation"),
            "beton de proprete": ("beton de proprete",),
            "ferraillage des fondations": ("ferraillage des semelles", "ferraillage des fondations"),
            "coffrage des fondations": ("coffrage et controle des fondations", "coffrage des fondations"),
            "betonnage des fondations": ("betonnage des fondations",),
            "maconnerie du soubassement": ("murs de soubassement", "maconnerie du soubassement"),
            "remblai": ("remblai peripherique", "remblai"),
            "dallage": ("dallage du rez-de-chaussee", "dallage"),
            "elevation des murs rdc": ("murs du rez-de-chaussee", "elevation des murs rdc"),
            "poteaux rdc": ("poteaux et murs du rez-de-chaussee", "poteaux rdc"),
            "poutres et dalle du rdc": ("poutres et dalle du rdc",),
            "elevation des murs etage": ("murs de l'etage", "murs de l’etage"),
            "escalier et dalle etage": ("escaliers", "dalles des niveaux"),
        }
        activity_totals = {}
        for r in progress:
            key = norm(r["activity"])
            bucket = activity_totals.setdefault(key, [0.0, 0.0])
            bucket[0] += float(r["planned_qty"] or 0)
            bucket[1] += float(r["actual_qty"] or 0)

        task_rates = []
        for task in planning_tasks:
            title = norm(task["title"])
            matched = []
            for activity_name, totals in activity_totals.items():
                candidates = aliases.get(activity_name, (activity_name,))
                if any(norm(alias) in title or title in norm(alias) for alias in candidates):
                    matched.append(totals)
            if matched:
                task_planned = sum(pair[0] for pair in matched)
                task_actual = sum(pair[1] for pair in matched)
                rate = min(100.0, task_actual / task_planned * 100.0) if task_planned > 0 else 0.0
            elif task["validated"] or task["status"] in ("Réalisé", "Terminé", "Validé"):
                rate = 100.0
            else:
                rate = 0.0
            task_rates.append(rate)
        # Chaque phase du planning compte, y compris celles qui ne sont pas encore commencées.
        # Ajouter/modifier un relevé actualise donc la phase liée et le taux global.
        completion = (sum(task_rates) / len(task_rates)) if task_rates else 0.0
        days_with_data = len({r["work_date"] for r in progress})
        productivity = (actual / sum(r["hours"] for r in progress)) if sum(r["hours"] for r in progress) else 0

        grouped = {}
        daily = {}
        activity_chart = {}
        for r in expenses:
            grouped[r["category"]] = grouped.get(r["category"], 0) + r["amount"]
        for r in progress:
            # Le graphique journalier montre les quantités réellement produites,
            # séparées par activité ET unité pour ne jamais additionner m², m³ et kg.
            activity_name = r["activity"].strip()
            unit_name = r["unit"].strip()
            day_key = (r["work_date"], activity_name, unit_name)
            daily[day_key] = daily.get(day_key, 0.0) + float(r["actual_qty"] or 0)
            key = (activity_name, unit_name)
            bucket = activity_chart.setdefault(key, [0.0, 0.0])
            bucket[0] += float(r["planned_qty"] or 0)
            bucket[1] += float(r["actual_qty"] or 0)
        activity_progress = [(f"{name} ({unit})", min(100.0, done / plan * 100.0) if plan > 0 else 0.0)
                             for (name, unit), (plan, done) in sorted(activity_chart.items())]

        stats = {
            "site_count": len(sites),
            "task_count": len(progress),
            "planned_qty": planned,
            "actual_qty": actual,
            "completion": completion,
            "total_expenses": total_expenses,
            "budget": site["budget"],
            "budget_remaining": site["budget"] - total_expenses,
            "budget_used_pct": (total_expenses / site["budget"] * 100) if site["budget"] else 0,
            "cost_vs_progress_gap": ((total_expenses / site["budget"] * 100) - completion) if site["budget"] else 0,
            "cost_per_progress_point": (total_expenses / completion) if completion > 0 else 0,
            "incident_count": len(incidents),
            "hours_lost": sum(r["hours_lost"] for r in incidents),
            "productivity": productivity,
            "days_with_data": days_with_data,
        }

        return {
            "sites": sites,
            "site": site,
            "stats": stats,
            "progress": progress,
            "expenses": expenses,
            "expenses_by_category": sorted(grouped.items(), key=lambda x: x[1], reverse=True),
            "expenses_by_activity": expenses_by_activity,
            "daily_progress": sorted((f"{day} · {activity} ({unit})", qty) for (day, activity, unit), qty in daily.items()),
            "activity_progress": activity_progress,
            "materials": materials,
            "incidents": incidents,
            "recent_progress": progress[:6],
        }


@app.route("/")
@login_required
def index():
    init_db()
    seed_demo_data()
    site_id = request.args.get("site_id", type=int)
    data = dashboard_data(site_id)
    return render_template("index.html", page_title="Tableau de bord", active_page="dashboard", today=__import__("datetime").date.today().isoformat(), **data)


def post_redirect(default_endpoint="index"):
    """Redirect back to the page where the data-entry form was submitted."""
    # Toutes les opérations d'enregistrement passent par la page Collecte de données.
    endpoint = "collection_page"
    site_id = request.form.get("site_id", type=int)
    return redirect(url_for(endpoint, site_id=site_id) if site_id else url_for(endpoint))


@app.route("/sites/add", methods=["POST"])
@collection_required
def add_site():
    try:
        name = request.form["name"].strip()
        location = request.form["location"].strip()
        manager = request.form["manager"].strip()
        start_date = request.form["start_date"]
        end_date = request.form["end_date"]
        budget = float(request.form["budget"])
        if not all([name, location, manager, start_date, end_date]) or budget < 0 or end_date < start_date:
            raise ValueError()
        with get_db() as conn:
            conn.execute("INSERT INTO site(name, location, manager, start_date, end_date, budget) VALUES (?, ?, ?, ?, ?, ?)",
                         (name, location, manager, start_date, end_date, budget))
        flash("Chantier créé avec succès.", "success")
    except (ValueError, KeyError):
        flash("Vérifie les informations du chantier et le budget.", "error")
    return post_redirect("chantiers_page")


@app.route("/progress/add", methods=["POST"])
@collection_required
def add_progress():
    try:
        values = (
            request.form["site_id"], request.form["work_date"].strip(),
            request.form["activity"].strip(), float(request.form["planned_qty"]),
            float(request.form["actual_qty"]), request.form["unit"].strip(),
            int(request.form["workers"]), float(request.form["hours"]),
            request.form.get("notes", "").strip()
        )
        if not values[2] or not values[5]:
            raise ValueError("L'activité et l'unité sont obligatoires.")
        with get_db() as conn:
            conn.execute("""INSERT INTO progress(site_id, work_date, activity, planned_qty,
                actual_qty, unit, workers, hours, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", values)
            # Synchronisation immédiate : une saisie de collecte met à jour le planning
            # du même chantier avant de rediriger vers la page de collecte.
            ensure_planning_seed(int(values[0]), conn)
        flash("Donnée enregistrée : le planning et le tableau de bord seront recalculés à l'affichage.", "success")
    except (ValueError, KeyError):
        flash("Vérifie les champs : les quantités, heures et effectifs doivent être numériques et positifs.", "error")
    return post_redirect("index")


@app.route("/expenses/add", methods=["POST"])
@collection_required
def add_expense():
    try:
        site_id = int(request.form["site_id"])
        expense_date = request.form["expense_date"]
        category = request.form["category"].strip()
        description = request.form["description"].strip()
        amount = float(request.form["amount"])
        activity = request.form.get("activity", "").strip()
        if not category or not description or amount < 0:
            raise ValueError()
        with get_db() as conn:
            if activity:
                # Empêche d'associer une dépense à une phase d'un autre chantier.
                task = conn.execute("SELECT id FROM planning WHERE site_id=? AND title=? LIMIT 1", (site_id, activity)).fetchone()
                if not task:
                    raise ValueError()
            conn.execute("""INSERT INTO expenses(site_id, expense_date, category, description, amount, activity)
                            VALUES (?, ?, ?, ?, ?, ?)""", (site_id, expense_date, category, description, amount, activity))
        flash("Dépense enregistrée et rattachée à la phase sélectionnée." if activity else "Dépense enregistrée. Pense à la rattacher à une phase pour analyser son coût.", "success")
    except (ValueError, KeyError):
        flash("Vérifie les champs de la dépense.", "error")
    return post_redirect("depenses_page")


@app.route("/materials/add", methods=["POST"])
@collection_required
def add_material():
    try:
        values = (request.form["site_id"], request.form["record_date"],
                  request.form["material"].strip(), float(request.form["opening_stock"]),
                  float(request.form["received_qty"]), float(request.form["used_qty"]),
                  request.form["unit"].strip(), float(request.form["unit_price"]))
        if not values[2] or not values[6] or min(values[3], values[4], values[5], values[7]) < 0:
            raise ValueError()
        with get_db() as conn:
            conn.execute("""INSERT INTO materials(site_id, record_date, material, opening_stock,
                received_qty, used_qty, unit, unit_price) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", values)
        flash("Mouvement de matériau enregistré.", "success")
    except (ValueError, KeyError):
        flash("Vérifie les quantités et le prix unitaire.", "error")
    return post_redirect("materiaux_page")


@app.route("/incidents/add", methods=["POST"])
@collection_required
def add_incident():
    try:
        values = (request.form["site_id"], request.form["incident_date"],
                  request.form["category"].strip(), float(request.form["hours_lost"]),
                  request.form["description"].strip())
        if not values[2] or not values[4] or values[3] < 0:
            raise ValueError()
        with get_db() as conn:
            conn.execute("""INSERT INTO incidents(site_id, incident_date, category, hours_lost, description)
                            VALUES (?, ?, ?, ?, ?)""", values)
        flash("Incident enregistré.", "success")
    except (ValueError, KeyError):
        flash("Vérifie les informations de l'incident.", "error")
    return post_redirect("incidents_page")


@app.route("/export")
@login_required
def export_data():
    site_id = request.args.get("site_id", type=int)
    data = dashboard_data(site_id)
    rows = [{
        "date": r["work_date"], "activite": r["activity"],
        "quantite_prevue": r["planned_qty"], "quantite_realisee": r["actual_qty"],
        "unite": r["unit"], "ouvriers": r["workers"], "heures": r["hours"],
        "productivite_par_heure": round(r["actual_qty"] / r["hours"], 2) if r["hours"] else 0,
        "notes": r["notes"]
    } for r in data["progress"]]
    df = pd.DataFrame(rows)
    csv_text = df.to_csv(index=False)
    from flask import Response
    return Response(
        csv_text,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=avancement_chantier.csv"}
    )



@app.route("/collecte-donnees")
@collection_required
def collection_page():
    init_db(); seed_demo_data()
    data = dashboard_data(request.args.get("site_id", type=int))
    planning_tasks = []
    if data.get("site"):
        with get_db() as conn:
            ensure_planning_seed(data["site"]["id"], conn)
            planning_tasks = conn.execute(
                "SELECT title FROM planning WHERE site_id=? ORDER BY start_date, id",
                (data["site"]["id"],)
            ).fetchall()
    return render_template("collection.html", page_title="Collecte de données",
                           active_page="collection", today=date.today().isoformat(),
                           planning_tasks=planning_tasks, **data)

@app.route("/chantiers")
@login_required
def chantiers_page():
    init_db(); seed_demo_data(); data=dashboard_data(request.args.get("site_id", type=int))
    with get_db() as conn: all_sites=conn.execute("SELECT * FROM site ORDER BY id DESC").fetchall()
    return render_template("chantiers.html", page_title="Chantiers", active_page="chantiers", all_sites=all_sites, today=date.today().isoformat(), **data)

@app.route("/devis")
@login_required
def devis_page():
    init_db(); seed_demo_data(); data=dashboard_data(request.args.get("site_id", type=int))
    with get_db() as conn:
        devis = conn.execute("SELECT * FROM quotes WHERE site_id=? ORDER BY quote_date DESC,id DESC", (data['site']['id'],)).fetchall() if data.get('site') else []
    quote_total = sum(float(row['quantity'])*float(row['unit_price']) for row in devis)
    return render_template('devis.html', page_title='Devis', active_page='devis', today=date.today().isoformat(), devis=devis, quote_total=quote_total, **data)

@app.route("/devis/add", methods=["POST"])
@collection_required
def add_devis():
    try:
        site_id = int(request.form['site_id'])
        quote_date = request.form['quote_date']
        designation = request.form['designation'].strip()
        quantity = float(request.form['quantity'])
        unit = request.form['unit'].strip()
        unit_price = float(request.form['unit_price'])
        notes = request.form.get('notes','').strip()
        if not designation or not unit or quantity < 0 or unit_price < 0:
            raise ValueError()
        with get_db() as conn:
            conn.execute('INSERT INTO quotes(site_id,quote_date,designation,quantity,unit,unit_price,notes) VALUES (?,?,?,?,?,?,?)',
                         (site_id,quote_date,designation,quantity,unit,unit_price,notes))
        flash('Ligne de devis enregistrée pour ce chantier.', 'success')
    except (ValueError, KeyError):
        flash('Vérifie les informations et les montants du devis.', 'error')
    return redirect(url_for('devis_page', site_id=request.form.get('site_id', type=int)))

@app.route("/suivi-travaux")
@login_required
def suivi_page():
    init_db(); seed_demo_data(); data=dashboard_data(request.args.get("site_id", type=int))
    return render_template("suivi_travaux.html", page_title="Suivi des travaux", active_page="suivi", today=date.today().isoformat(), **data)

@app.route("/materiaux")
@login_required
def materiaux_page():
    init_db(); seed_demo_data(); data=dashboard_data(request.args.get("site_id", type=int))
    return render_template("materiaux.html", page_title="Matériaux", active_page="materiaux", today=date.today().isoformat(), **data)

@app.route("/depenses")
@login_required
def depenses_page():
    init_db(); seed_demo_data(); data=dashboard_data(request.args.get("site_id", type=int))
    return render_template("depenses.html", page_title="Dépenses", active_page="depenses", today=date.today().isoformat(), **data)

@app.route("/analyses")
@login_required
def analyses_page():
    init_db(); seed_demo_data()
    scope = request.args.get("scope", "site")
    data = dashboard_data(request.args.get("site_id", type=int))
    def describe(seq):
        return {"n":len(seq),"mean":statistics.mean(seq) if seq else 0,"median":statistics.median(seq) if seq else 0,
                "std":statistics.pstdev(seq) if len(seq)>1 else 0,"min":min(seq) if seq else 0,"max":max(seq) if seq else 0}
    with get_db() as conn:
        all_sites = conn.execute("SELECT * FROM site ORDER BY id").fetchall()
        selected_id = data["site"]["id"] if data.get("site") else 0
        if scope == "global":
            raw_progress = conn.execute("SELECT p.*,s.name AS site_name FROM progress p JOIN site s ON s.id=p.site_id ORDER BY p.work_date,p.id").fetchall()
            raw_costs = conn.execute("SELECT e.category,SUM(e.amount) total FROM expenses e GROUP BY e.category ORDER BY total DESC").fetchall()
            activity_rows = conn.execute("SELECT p.activity, p.unit, COUNT(*) n,SUM(p.planned_qty) planned,SUM(p.actual_qty) actual,SUM(p.hours) hours FROM progress p GROUP BY p.activity,p.unit ORDER BY p.activity").fetchall()
            site_rows = conn.execute("SELECT s.id,s.name,s.budget,COALESCE((SELECT SUM(p.planned_qty) FROM progress p WHERE p.site_id=s.id),0) planned,COALESCE((SELECT SUM(p.actual_qty) FROM progress p WHERE p.site_id=s.id),0) actual,COALESCE((SELECT SUM(e.amount) FROM expenses e WHERE e.site_id=s.id),0) expenses,COALESCE((SELECT SUM(i.hours_lost) FROM incidents i WHERE i.site_id=s.id),0) hours_lost FROM site s ORDER BY s.id").fetchall()
        else:
            raw_progress = conn.execute("SELECT p.*,s.name AS site_name FROM progress p JOIN site s ON s.id=p.site_id WHERE p.site_id=? ORDER BY p.work_date,p.id",(selected_id,)).fetchall()
            raw_costs = conn.execute("SELECT category,SUM(amount) total FROM expenses WHERE site_id=? GROUP BY category ORDER BY total DESC",(selected_id,)).fetchall()
            activity_rows = conn.execute("SELECT activity,unit,COUNT(*) n,SUM(planned_qty) planned,SUM(actual_qty) actual,SUM(hours) hours FROM progress WHERE site_id=? GROUP BY activity,unit ORDER BY activity",(selected_id,)).fetchall()
            site_rows = conn.execute("SELECT s.id,s.name,s.budget,COALESCE((SELECT SUM(p.planned_qty) FROM progress p WHERE p.site_id=s.id),0) planned,COALESCE((SELECT SUM(p.actual_qty) FROM progress p WHERE p.site_id=s.id),0) actual,COALESCE((SELECT SUM(e.amount) FROM expenses e WHERE e.site_id=s.id),0) expenses,COALESCE((SELECT SUM(i.hours_lost) FROM incidents i WHERE i.site_id=s.id),0) hours_lost FROM site s ORDER BY s.id").fetchall()
    values=[float(r["actual_qty"]) for r in raw_progress]
    planned_vals=[float(r["planned_qty"]) for r in raw_progress]
    hourly=[float(r["actual_qty"])/float(r["hours"]) for r in raw_progress if r["hours"]]
    deviations=[float(r["actual_qty"])-float(r["planned_qty"]) for r in raw_progress]
    total_cost=sum(float(r["total"] or 0) for r in raw_costs)
    cost_stats=[{"category":r["category"],"total":float(r["total"] or 0),"pct":((float(r["total"] or 0)/total_cost*100) if total_cost else 0)} for r in raw_costs]
    activity_stats=[{"activity":r["activity"],"unit":r["unit"],"n":r["n"],"planned":float(r["planned"] or 0),"actual":float(r["actual"] or 0),"rate":(float(r["actual"] or 0)/float(r["planned"] or 1)*100),"productivity":(float(r["actual"] or 0)/float(r["hours"] or 1))} for r in activity_rows]
    analysis={"actual":describe(values),"planned":describe(planned_vals),"hourly":describe(hourly),"deviation":describe(deviations),"costs":cost_stats,"activities":activity_stats}
    # Pour la vue globale, les relevés et dépenses de tous les chantiers alimentent les graphes.
    # Moyenne des taux par activité/unité pour comparer les chantiers sans additionner des unités différentes.
    with get_db() as conn:
        site_activity = conn.execute("SELECT site_id,activity,unit,SUM(planned_qty) planned,SUM(actual_qty) actual FROM progress GROUP BY site_id,activity,unit").fetchall()
    rates_by_site={}
    for row in site_activity:
        rates_by_site.setdefault(row["site_id"],[]).append((float(row["actual"] or 0)/float(row["planned"] or 1))*100 if row["planned"] else 0)
    site_comparison=[]
    for r in site_rows:
        rates=rates_by_site.get(r["id"],[])
        site_comparison.append({"name":r["name"],"planned":float(r["planned"] or 0),"actual":float(r["actual"] or 0),"rate":(sum(rates)/len(rates) if rates else 0),"expenses":float(r["expenses"] or 0),"budget":float(r["budget"] or 0),"hours_lost":float(r["hours_lost"] or 0)})
    graph_data={
      "progress":[{"date":r["work_date"],"activity":r["activity"],"planned":float(r["planned_qty"]),"actual":float(r["actual_qty"]),"hours":float(r["hours"]),"unit":r["unit"],"site":r["site_name"]} for r in raw_progress],
      "costs":cost_stats,"budget":float(data["site"]["budget"]) if data.get("site") else 0,
      "siteName":"Analyse globale — tous les chantiers" if scope=="global" else (data["site"]["name"] if data.get("site") else "Aucun chantier"),
      "mode":scope,"siteComparison":site_comparison
    }
    global_summary={"sites":len(all_sites),"planned":sum(float(r["planned"] or 0) for r in site_rows) if scope=="global" else sum(planned_vals),"actual":sum(float(r["actual"] or 0) for r in site_rows) if scope=="global" else sum(values),"expenses":sum(float(r["expenses"] or 0) for r in site_rows) if scope=="global" else total_cost,"budget":sum(float(r["budget"] or 0) for r in site_rows) if scope=="global" else (float(data["site"]["budget"]) if data.get("site") else 0),"hours_lost":sum(float(r["hours_lost"] or 0) for r in site_rows) if scope=="global" else float(data.get("stats",{}).get("hours_lost",0))}
    global_summary["rate"]=(sum(x["rate"] for x in site_comparison)/len(site_comparison)) if scope=="global" and site_comparison else ((sum(values)/sum(planned_vals)*100) if sum(planned_vals) else 0)
    return render_template("analyses.html",page_title="Analyse statistique",active_page="analyses",today=date.today().isoformat(),analysis=analysis,graph_data=graph_data,scope=scope,all_sites=all_sites,site_rows=site_rows,global_summary=global_summary,**data)

@app.route("/incidents")
@login_required
def incidents_page():
    init_db(); seed_demo_data(); data=dashboard_data(request.args.get("site_id", type=int))
    return render_template("incidents.html", page_title="Incidents", active_page="incidents", today=date.today().isoformat(), **data)

@app.route("/rapports")
@login_required
def rapports_page():
    init_db(); seed_demo_data(); data=dashboard_data(request.args.get("site_id", type=int))
    return render_template("rapports.html", page_title="Rapports", active_page="rapports", today=date.today().isoformat(), **data)

@app.route("/rapports/texte")
@login_required
def report_text():
    data=dashboard_data(request.args.get("site_id", type=int)); site=data.get("site"); stats=data.get("stats", {})
    if not site: return "Aucun chantier disponible", 404
    content=(f"RAPPORT DE SUIVI DE CHANTIER\n{site['name']}\nLieu : {site['location']}\nResponsable : {site['manager']}\nPériode : {site['start_date']} au {site['end_date']}\n\n"
      f"SYNTHÈSE\nBudget : {stats['budget']:,.0f} FCFA\nDépenses enregistrées : {stats['total_expenses']:,.0f} FCFA\nBudget restant : {stats['budget_remaining']:,.0f} FCFA\nUtilisation du budget : {stats['budget_used_pct']:.1f}%\n"
      f"Avancement observé (indicateur brut) : {stats['completion']:.1f}%\nQuantités prévues cumulées : {stats['planned_qty']:.2f}\nQuantités réalisées cumulées : {stats['actual_qty']:.2f}\nProductivité brute : {stats['productivity']:.2f} unités/heures\n"
      f"Nombre de relevés : {stats['task_count']}\nIncidents : {stats['incident_count']}\nHeures perdues : {stats['hours_lost']:.1f} h\n\nDÉTAIL DES DÉPENSES\n"+
      "\n".join(f"- {e['expense_date']} | {e['category']} | {e['description']} : {e['amount']:,.0f} FCFA" for e in data['expenses'])+
      "\n\nAVANCEMENT\n"+"\n".join(f"- {r['work_date']} | {r['activity']} : prévu {r['planned_qty']} {r['unit']}, réalisé {r['actual_qty']} {r['unit']}, équipe {r['workers']}, {r['hours']} h" for r in data['progress'])+
      "\n\nNote : rapport généré automatiquement à partir des données saisies. Les données initiales de démonstration sont synthétiques.\n")
    from flask import Response
    return Response(content, mimetype="text/plain; charset=utf-8", headers={"Content-Disposition":"attachment; filename=rapport_chantier.txt"})

@app.route("/rapports/pdf")
@login_required
def report_pdf():
    from io import BytesIO
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib import colors
    from xml.sax.saxutils import escape
    data=dashboard_data(request.args.get("site_id", type=int)); site=data.get("site"); stats=data.get("stats", {})
    if not site: return "Aucun chantier disponible", 404
    buffer=BytesIO(); doc=SimpleDocTemplate(buffer,pagesize=A4,rightMargin=38,leftMargin=38,topMargin=38,bottomMargin=38); styles=getSampleStyleSheet(); story=[]
    story += [Paragraph("Rapport de suivi de chantier",styles['Title']),Paragraph(escape(site['name']),styles['Heading2']),Paragraph(f"Lieu : {escape(site['location'])} | Responsable : {escape(site['manager'])}",styles['Normal']),Spacer(1,12),Paragraph("Synthèse des indicateurs",styles['Heading2'])]
    rows=[["Indicateur","Valeur"],["Budget",f"{stats['budget']:,.0f} FCFA"],["Dépenses",f"{stats['total_expenses']:,.0f} FCFA"],["Budget restant",f"{stats['budget_remaining']:,.0f} FCFA"],["Budget utilisé",f"{stats['budget_used_pct']:.1f}%"],["Avancement observé (brut)",f"{stats['completion']:.1f}%"],["Relevés d'avancement",str(stats['task_count'])],["Incidents / heures perdues",f"{stats['incident_count']} / {stats['hours_lost']:.1f} h"]]
    table=Table(rows,colWidths=[245,230],repeatRows=1); table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#17365d')),('TEXTCOLOR',(0,0),(-1,0),colors.white),('GRID',(0,0),(-1,-1),.4,colors.grey),('PADDING',(0,0),(-1,-1),7)])); story += [table,Spacer(1,14),Paragraph("Dépenses détaillées",styles['Heading2'])]
    exp_rows=[["Date","Catégorie","Description","Montant FCFA"]]+[[e['expense_date'],e['category'],Paragraph(escape(e['description']),styles['BodyText']),f"{e['amount']:,.0f}"] for e in data['expenses']]
    t2=Table(exp_rows,colWidths=[65,90,250,85],repeatRows=1); t2.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#dce6f1')),('GRID',(0,0),(-1,-1),.3,colors.grey),('PADDING',(0,0),(-1,-1),5)])); story += [t2,Spacer(1,14),Paragraph("Avancement des travaux",styles['Heading2'])]
    prog_rows=[["Date","Activité","Prévu","Réalisé","Unité"]]+[[r['work_date'],Paragraph(escape(r['activity']),styles['BodyText']),f"{r['planned_qty']:g}",f"{r['actual_qty']:g}",r['unit']] for r in data['progress']]
    t3=Table(prog_rows,colWidths=[75,190,65,65,65],repeatRows=1); t3.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#dce6f1')),('GRID',(0,0),(-1,-1),.3,colors.grey),('PADDING',(0,0),(-1,-1),5)])); story += [t3,Spacer(1,10),Paragraph("Rapport généré automatiquement. Les données de démonstration sont synthétiques.",styles['Italic'])]
    doc.build(story); buffer.seek(0)
    from flask import send_file
    return send_file(buffer,mimetype='application/pdf',as_attachment=True,download_name='rapport_chantier.pdf')

def ensure_planning_seed(site_id, conn):
    """Prépare un planning complet propre à chaque chantier sans dupliquer les tâches."""
    existing = {r[0] for r in conn.execute("SELECT title FROM planning WHERE site_id=?", (site_id,)).fetchall()}
    site = conn.execute("SELECT start_date,end_date,manager FROM site WHERE id=?", (site_id,)).fetchone()
    if not site:
        return
    try:
        base = date.fromisoformat(site["start_date"])
    except (TypeError, ValueError):
        base = date.today()
    try:
        finish = date.fromisoformat(site["end_date"])
    except (TypeError, ValueError):
        finish = base + __import__('datetime').timedelta(days=120)
    duration = max(30, (finish-base).days)
    site_name_row = conn.execute("SELECT name FROM site WHERE id=?", (site_id,)).fetchone()
    site_name = site_name_row["name"] if site_name_row else ""
    if "route" in site_name.casefold():
        phase_names = [
            "Études d'exécution, implantation et plan de circulation",
            "Installation, signalisation temporaire et sécurisation",
            "Débroussaillage, nettoyage et décapage de l'emprise",
            "Terrassements et mise en forme de la plateforme",
            "Réalisation des ouvrages d'assainissement et caniveaux",
            "Mise en œuvre de la couche de forme",
            "Compactage et essais de portance de la plateforme",
            "Mise en œuvre de la couche de fondation",
            "Mise en œuvre de la couche de base",
            "Imprégnation et préparation avant revêtement",
            "Fabrication et pose de l'enrobé bitumineux",
            "Réalisation des accotements et raccordements",
            "Signalisation horizontale et verticale",
            "Contrôles qualité, essais et correction des défauts",
            "Nettoyage, réception provisoire et remise de la route",
        ]
    else:
        phase_names = [
            "Études, plans d'exécution et autorisations",
            "Installation de chantier, clôture et panneau de chantier",
            "Implantation topographique et nivellement",
            "Décapage et terrassement général",
            "Fouilles en rigoles et excavation des fondations",
            "Évacuation des déblais et réglage du fond de fouille",
            "Béton de propreté",
            "Ferraillage des semelles et attentes",
            "Coffrage et contrôle des fondations",
            "Bétonnage des fondations et cure",
            "Élévation des murs de soubassement et étanchéité",
            "Remblai périphérique et compactage",
            "Réseaux enterrés et réservations techniques",
            "Hérisson, film polyane et dallage du rez-de-chaussée",
            "Élévation des poteaux et murs du rez-de-chaussée",
            "Coffrage et ferraillage des poutres et dalle du RDC",
            "Bétonnage de la dalle du RDC et cure",
            "Élévation des murs de l'étage / étage supérieur",
            "Escaliers, poteaux, poutres et dalles des niveaux",
            "Charpente, couverture et étanchéité",
            "Pose des réseaux de plomberie et évacuations",
            "Installation électrique, gaines et tableaux",
            "Enduits intérieurs et extérieurs",
            "Chapes et revêtements de sols et murs",
            "Pose des portes, fenêtres et menuiseries",
            "Peinture, plafonds et finitions",
            "Équipements sanitaires et appareillages électriques",
            "Aménagements extérieurs et évacuation des eaux",
            "Essais techniques, contrôle qualité et levée des réserves",
            "Nettoyage final, réception provisoire et remise des clés",
        ]
    # Répartit toutes les activités sur la durée réelle du chantier, sans dépasser la date de fin.
    phase_count = len(phase_names)
    phases = []
    for i, title in enumerate(phase_names):
        a = i / phase_count
        b = min(1.0, (i + 1.25) / phase_count)
        phases.append((title, a, b))
    progress_rows = conn.execute("SELECT activity,MIN(work_date) first_day,MAX(work_date) last_day,SUM(planned_qty) planned,SUM(actual_qty) actual FROM progress WHERE site_id=? GROUP BY activity", (site_id,)).fetchall()
    progress_by_name = {r["activity"].strip().casefold(): r for r in progress_rows}
    for title, a, b in phases:
        if title in existing:
            continue
        begin = base + __import__('datetime').timedelta(days=round(duration*a))
        end = base + __import__('datetime').timedelta(days=max(round(duration*a), round(duration*b)))
        if end > finish: end = finish
        status, notes = "À faire", "Étape prévisionnelle : dates indicatives à confirmer selon le chantier."
        match = progress_by_name.get(title.casefold())
        if match:
            planned = float(match["planned"] or 0); actual = float(match["actual"] or 0)
            if planned > 0 and actual >= planned:
                status, notes = "Réalisé", "Avancement constaté dans les données de suivi."
            elif actual > 0:
                status, notes = "En cours", "Avancement constaté dans les données de suivi."
        conn.execute("INSERT INTO planning(site_id,title,start_date,end_date,responsible,status,notes,validated) VALUES (?,?,?,?,?,?,?,?)",
                     (site_id,title,begin.isoformat(),end.isoformat(),site["manager"] or "À désigner",status,notes,1 if status=="Réalisé" else 0))
    # Synchroniser le planning avec les relevés même lorsque les intitulés diffèrent.
    # Une activité suivie peut correspondre à une phase au libellé plus détaillé.
    aliases = {
        "fouilles": ("fouille", "excavation"),
        "béton de propreté": ("béton de propreté",),
        "ferraillage des fondations": ("ferraillage des semelles", "ferraillage des fondations"),
        "coffrage des fondations": ("coffrage et contrôle des fondations", "coffrage des fondations"),
        "bétonnage des fondations": ("bétonnage des fondations",),
        "maçonnerie du soubassement": ("murs de soubassement", "maçonnerie du soubassement"),
        "remblai": ("remblai périphérique", "remblai"),
        "dallage": ("dallage du rez-de-chaussée", "dallage"),
        "élévation des murs rdc": ("murs du rez-de-chaussée", "élévation des murs rdc"),
        "poteaux rdc": ("poteaux et murs du rez-de-chaussée", "poteaux rdc"),
        "poutres et dalle du rdc": ("poutres et dalle du rdc",),
        "élévation des murs étage": ("murs de l'étage", "murs de l’étage"),
        "escalier et dalle étage": ("escaliers", "dalles des niveaux"),
    }
    tasks = conn.execute("SELECT id,title,status,validated FROM planning WHERE site_id=?", (site_id,)).fetchall()
    for task in tasks:
        title = task["title"].strip().casefold()
        matched = []
        for activity_key, row in progress_by_name.items():
            candidates = aliases.get(activity_key, (activity_key,))
            if any(alias.casefold() in title for alias in candidates) or any(title in alias.casefold() for alias in candidates):
                matched.append(row)
        if not matched:
            continue
        planned = sum(float(row["planned"] or 0) for row in matched)
        actual = sum(float(row["actual"] or 0) for row in matched)
        # Ne pas confondre les unités différentes pour une même phase; les alias
        # sont limités aux activités de la phase et le statut se base sur le total observé.
        if planned > 0 and actual >= planned:
            conn.execute("UPDATE planning SET status='Réalisé',validated=1,notes='Statut synchronisé avec les quantités de suivi.' WHERE id=?", (task["id"],))
        elif actual > 0:
            conn.execute("UPDATE planning SET status='En cours',validated=0,notes='Avancement partiel constaté dans les relevés de suivi.' WHERE id=?", (task["id"],))
        elif (task["status"] in ('En cours','Réalisé','Terminé') and
              (not task["validated"] or 'quantités de suivi' in str(task["notes"] or '').casefold())):
            conn.execute("UPDATE planning SET status='À faire',validated=0,notes='Aucun avancement enregistré dans les relevés.' WHERE id=?", (task["id"],))


@app.route("/planning", methods=["GET"])
@login_required
def planning_page():
    init_db(); seed_demo_data(); data=dashboard_data(request.args.get("site_id", type=int))
    with get_db() as conn:
        if data.get('site'):
            ensure_planning_seed(data['site']['id'], conn)
            if session.get('role') == 'maitre_ouvrage':
                tasks=conn.execute("SELECT * FROM planning WHERE site_id=? AND validated=1 ORDER BY start_date,id", (data['site']['id'],)).fetchall()
            else:
                tasks=conn.execute("SELECT * FROM planning WHERE site_id=? ORDER BY start_date,id", (data['site']['id'],)).fetchall()
        else: tasks=[]
    completed_tasks=[t for t in tasks if t['status'] in ('Réalisé','Terminé','Validé') or t['validated']]
    pending_tasks=[t for t in tasks if t not in completed_tasks]
    return render_template('planning.html',page_title='Planning',active_page='planning',tasks=tasks,completed_tasks=completed_tasks,pending_tasks=pending_tasks,today=date.today().isoformat(),**data)

@app.route("/planning/add", methods=["POST"])
@collection_required
def add_planning():
    try:
        site_id=int(request.form['site_id']); title=request.form['title'].strip(); start=request.form['start_date']; end=request.form['end_date']; responsible=request.form.get('responsible','').strip(); status=request.form.get('status','À faire'); notes=request.form.get('notes','').strip()
        if not title or not start or not end or end < start: raise ValueError()
        with get_db() as conn: conn.execute("INSERT INTO planning(site_id,title,start_date,end_date,responsible,status,notes,validated) VALUES (?,?,?,?,?,?,?,0)",(site_id,title,start,end,responsible,status,notes))
        flash('Tâche ajoutée au planning. Elle devra être validée par le collecteur avant d’être visible par le consultant.','success')
    except (ValueError,KeyError): flash('Vérifie les informations du planning.','error')
    return redirect(url_for('planning_page', site_id=request.form.get('site_id', type=int)))

@app.route("/planning/<int:task_id>/valider", methods=["POST"])
@collection_required
def validate_planning(task_id):
    with get_db() as conn:
        task=conn.execute("SELECT id FROM planning WHERE id=?",(task_id,)).fetchone()
        if not task:
            flash('Tâche introuvable.','error')
        else:
            conn.execute("UPDATE planning SET validated=1, status='Réalisé', validated_by=?, validated_at=? WHERE id=?",
                         (session.get('full_name') or session.get('username','Collecteur'), datetime.now().strftime('%Y-%m-%d %H:%M'), task_id))
            flash('Tâche validée. Elle est maintenant visible dans l’interface du maître d’ouvrage.','success')
    return redirect(url_for('planning_page', site_id=request.form.get('site_id', type=int)))

@app.route("/equipe", methods=["GET"])
@login_required
def equipe_page():
    init_db(); seed_demo_data(); data=dashboard_data(request.args.get('site_id',type=int))
    with get_db() as conn: staff=conn.execute("SELECT * FROM staff WHERE site_id=? ORDER BY active DESC, full_name",(data['site']['id'],)).fetchall() if data.get('site') else []
    return render_template('equipe.html',page_title='Équipe et personnel',active_page='equipe',staff=staff,today=date.today().isoformat(),**data)

@app.route("/equipe/add", methods=["POST"])
@collection_required
def add_staff():
    try:
        values=(int(request.form['site_id']),request.form['full_name'].strip(),request.form['job_title'].strip(),request.form.get('phone','').strip(),float(request.form['monthly_salary']))
        if not values[1] or not values[2] or values[4]<0: raise ValueError()
        with get_db() as conn: conn.execute("INSERT INTO staff(site_id,full_name,job_title,phone,monthly_salary) VALUES (?,?,?,?,?)",values)
        flash('Membre du personnel ajouté.','success')
    except (ValueError,KeyError): flash('Vérifie le nom, le poste et le salaire.','error')
    return redirect(url_for('equipe_page', site_id=request.form.get('site_id', type=int)))

@app.route("/equipe/paie", methods=["POST"])
@collection_required
def payroll_staff():
    try:
        staff_id=int(request.form['staff_id']); month=request.form['payroll_month']
        if len(month)!=7 or month[4]!='-': raise ValueError()
        with get_db() as conn:
            person=conn.execute("SELECT * FROM staff WHERE id=?",(staff_id,)).fetchone()
            if not person: raise ValueError()
            if conn.execute("SELECT id FROM payroll WHERE staff_id=? AND payroll_month=?",(staff_id,month)).fetchone():
                flash('Le salaire de ce membre a déjà été comptabilisé pour ce mois.','error'); return redirect(url_for('equipe_page', site_id=request.form.get('site_id', type=int)))
            cur=conn.execute("INSERT INTO expenses(site_id,expense_date,category,description,amount) VALUES (?,?,?,?,?)",(person['site_id'],month+'-01','Main-d’œuvre',f"Salaire {person['full_name']} — {month}",person['monthly_salary']))
            conn.execute("INSERT INTO payroll(staff_id,site_id,payroll_month,amount,expense_id) VALUES (?,?,?,?,?)",(staff_id,person['site_id'],month,person['monthly_salary'],cur.lastrowid))
        flash('Salaire comptabilisé dans les dépenses du chantier.','success')
    except (ValueError,KeyError): flash('Impossible de comptabiliser ce salaire.','error')
    return redirect(url_for('equipe_page', site_id=request.form.get('site_id', type=int)))

@app.route("/photos", methods=["GET"])
@login_required
def photos_page():
    init_db(); seed_demo_data(); data=dashboard_data(request.args.get('site_id',type=int))
    with get_db() as conn: photos=conn.execute("SELECT * FROM site_photos WHERE site_id=? ORDER BY photo_date DESC,id DESC",(data['site']['id'],)).fetchall() if data.get('site') else []
    return render_template('photos.html',page_title='Photos du chantier',active_page='photos',photos=photos,today=date.today().isoformat(),**data)

@app.route("/photos/add", methods=["POST"])
@collection_required
def add_photo():
    f=request.files.get('photo'); site_id=request.form.get('site_id',type=int); caption=request.form.get('caption','').strip(); photo_date=request.form.get('photo_date') or date.today().isoformat()
    if not f or not f.filename or '.' not in f.filename:
        flash('Choisis une photo au format JPG, PNG ou WEBP.','error'); return redirect(url_for('photos_page', site_id=request.form.get('site_id', type=int)))
    ext=f.filename.rsplit('.',1)[1].lower()
    if ext not in ALLOWED_PHOTO_EXTENSIONS:
        flash('Format refusé. Utilise JPG, PNG ou WEBP.','error'); return redirect(url_for('photos_page', site_id=request.form.get('site_id', type=int)))
    if not site_id: flash('Sélectionne un chantier.','error'); return redirect(url_for('photos_page', site_id=request.form.get('site_id', type=int)))
    filename=f"{uuid.uuid4().hex}.{ext}"; f.save(UPLOAD_DIR/filename)
    with get_db() as conn: conn.execute("INSERT INTO site_photos(site_id,photo_path,caption,photo_date,uploaded_by) VALUES (?,?,?,?,?)",(site_id,'uploads/'+filename,caption,photo_date,session.get('full_name','')))
    flash('Photo ajoutée au journal du chantier.','success'); return redirect(url_for('photos_page', site_id=request.form.get('site_id', type=int)))

@app.route("/profil", methods=["GET", "POST"])
@login_required
def profil_page():
    init_db(); seed_demo_data()
    if request.method == 'POST':
        full_name=request.form.get('full_name','').strip()
        photo=request.files.get('profile_photo')
        if not full_name:
            flash('Le nom complet est obligatoire.','error')
            return redirect(url_for('profil_page'))
        photo_path=None
        if photo and photo.filename:
            ext=photo.filename.rsplit('.',1)[-1].lower() if '.' in photo.filename else ''
            if ext not in ALLOWED_PHOTO_EXTENSIONS:
                flash('Photo refusée : utilise JPG, PNG ou WEBP.','error'); return redirect(url_for('profil_page'))
            filename=f"profile_{g.user['id']}_{uuid.uuid4().hex}.{ext}"
            photo.save(UPLOAD_DIR/filename); photo_path='uploads/'+filename
        with get_db() as conn:
            if photo_path:
                conn.execute("UPDATE users SET full_name=?, profile_photo=? WHERE id=?",(full_name,photo_path,g.user['id']))
            else:
                conn.execute("UPDATE users SET full_name=? WHERE id=?",(full_name,g.user['id']))
        flash('Profil mis à jour.','success')
        return redirect(url_for('profil_page'))
    data=dashboard_data(request.args.get("site_id", type=int))
    with get_db() as conn:
        user=conn.execute("SELECT id,username,full_name,role,profile_photo,created_at FROM users WHERE id=?",(g.user['id'],)).fetchone()
    return render_template("profil.html", page_title="Profil", active_page="profil", today=date.today().isoformat(), profile_user=user, **data)

if __name__ == "__main__":
    init_db()
    seed_demo_data()
    # Version pédagogique locale : aucune connexion requise.
    app.run(debug=True)
