from app.constants import INITIAL_USERS
import os
import pandas as pd
from datetime import date, timedelta
from flask import current_app as app

basedir = os.path.abspath(os.path.dirname(__file__))
from werkzeug.security import generate_password_hash

from app.database import db
from app.models.models import Flock, Standard, UIElement, User, House, GlobalStandard, SamplingEvent, Vaccine
from app.utils import safe_commit

def init_ui_elements(commit=True):
    default_elements = [
        # Navbar Main
        {'key': 'nav_dashboard', 'label': 'Dashboard', 'section': 'navbar_main', 'order': 1},
        {'key': 'nav_daily_entry', 'label': 'Daily Entry', 'section': 'navbar_main', 'order': 2},
        {'key': 'nav_health_log', 'label': 'Health Log', 'section': 'navbar_main', 'order': 3},
        {'key': 'nav_inventory', 'label': 'Inventory', 'section': 'navbar_main', 'order': 4},

        # Navbar Health Dropdown
        {'key': 'nav_health_vaccine', 'label': 'Vaccine', 'section': 'navbar_health', 'order': 1},
        {'key': 'nav_health_sampling', 'label': 'Sampling', 'section': 'navbar_health', 'order': 2},
        {'key': 'nav_health_medication', 'label': 'Medication', 'section': 'navbar_health', 'order': 3},
        {'key': 'nav_health_notes', 'label': 'Post Mortem', 'section': 'navbar_health', 'order': 4},
        {'key': 'nav_weight_grading', 'label': 'Bodyweight', 'section': 'navbar_health', 'order': 5},

        # Flock Card (Dashboard)
        {'key': 'card_details', 'label': 'See Details', 'section': 'flock_card', 'order': 1},
        {'key': 'card_start_prod', 'label': 'Start Prod', 'section': 'flock_card', 'order': 2},

        # Flock Detail (Overview Footer)
        {'key': 'detail_kpi', 'label': 'KPI Dashboard', 'section': 'flock_detail', 'order': 1},
        {'key': 'detail_custom', 'label': 'Custom Dashboard', 'section': 'flock_detail', 'order': 2},
        {'key': 'detail_charts', 'label': 'Advanced Charts', 'section': 'flock_detail', 'order': 3},
        {'key': 'detail_hatch', 'label': 'Hatchability', 'section': 'flock_detail', 'order': 4},
        {'key': 'detail_health', 'label': 'Health Log', 'section': 'flock_detail', 'order': 5},
    ]

    # Bulk fetch existing elements to avoid N+1 queries
    existing_elements = {e.key: e for e in UIElement.query.all()}

    for elem in default_elements:
        if elem['key'] not in existing_elements:
            new_elem = UIElement(
                key=elem['key'],
                label=elem['label'],
                section=elem['section'],
                order_index=elem['order']
            )
            db.session.add(new_elem)
        else:
            # Update existing element properties if they differ
            existing = existing_elements[elem['key']]
            if existing.label != elem['label'] or existing.section != elem['section'] or existing.order_index != elem['order']:
                existing.label = elem['label']
                existing.section = elem['section']
                existing.order_index = elem['order']

    if commit:
        safe_commit()
    else:
        db.session.flush()

def initialize_sampling_schedule(flock_id, commit=True):
    # Updated Schedule based on user input
    schedule = {
        1: 'Serology & Salmonella',
        4: 'Salmonella',
        8: 'Serology',
        16: 'Salmonella',
        18: 'Serology',
        24: 'Serology',
        28: 'Salmonella',
        30: 'Serology',
        38: 'Serology',
        40: 'Salmonella',
        50: 'Serology',
        52: 'Salmonella',
        58: 'Serology',
        64: 'Salmonella',
        70: 'Serology',
        76: 'Salmonella',
        90: 'Salmonella'
    }

    # Check if already initialized to avoid duplicates
    existing = SamplingEvent.query.filter_by(flock_id=flock_id).first()
    if existing:
        return

    flock = Flock.query.get(flock_id)
    if not flock: return

    for week, test in schedule.items():
        days_offset = ((week - 1) * 7) + 1
        scheduled_date = flock.intake_date + timedelta(days=days_offset)

        event = SamplingEvent(
            flock_id=flock_id,
            age_week=week,
            test_type=test,
            status='Pending',
            scheduled_date=scheduled_date
        )
        db.session.add(event)

    if commit:
        safe_commit()
    else:
        db.session.flush()

def initialize_users():
    # Helper to seed users if table is empty or missing specific users
    for u_data in INITIAL_USERS:
        user = User.query.filter_by(username=u_data['username']).first()
        if not user:
            user = User(
                username=u_data['username'],
                dept=u_data['dept'],
                role=u_data['role']
            )
            user.set_password(u_data['password'])
            db.session.add(user)
    safe_commit()

def initialize_vaccine_schedule(flock_id, commit=True):
    flock = Flock.query.get(flock_id)
    if not flock: return

    schedule_data = [
        ('D1', 'TRIVALENT VAXXITEK', 'S/C'),
        ('D1', 'PREVEXXION', 'S/C'),
        ('D1', 'COCCIVAC', 'SPRAY'),
        ('D1', 'MA5 CLONE 30', 'SPRAY'),
        ('D1', 'IBIRD', 'SPRAY'),
        ('D8', 'REO S1133', 'S/C'),
        ('D8', 'MA5 CLONE 30', 'EYE DROP'),
        ('D14', 'NEW LS MASS (RHONE MA)', 'EYE DROP'),
        ('D21', 'MA5 CLONE 30', 'EYE DROP'),
        ('D21', 'VECTORMUNE FP-MG', 'W/W'),
        ('D28', 'ND STANDARD (0.2ml)', 'EYE DROP'),
        ('W6', 'FC OIL (0.2ml)', 'I/M'),
        ('W7', 'ANIVAC H9N2', 'I/M'),
        ('W7', 'NOBILIS IB 4/91 + MA5 CLONE 30', 'EYE DROP'),
        ('W8', 'ND STANDARD (0.4ml)', 'I/M'),
        ('W9', 'LT IVAX', 'EYE DROP'),
        ('W9', 'ANIVAC FADV', 'I/M'),
        ('W10', 'CEVA CIRCOMUNE', 'W/W'),
        ('W10', 'POXIMUNE AE', 'W/W'),
        ('W12', 'REO S1133', 'S/C'),
        ('W12', 'MS VAC', 'I/M'),
        ('W12', 'NEMOVAC', 'D/W'),
        ('W13', 'CORYZA GEL 3', 'I/M'),
        ('W13', 'GALLIVAC LASOTA IB MASS', 'EYE DROP'),
        ('W14', 'GALLIMUNE 407', 'I/M'),
        ('W14', 'ANIVAC H9N2', 'I/M'),
        ('W16', 'GALLIVAC LASOTA IB MASS', 'D/W'),
        ('W17', 'NOBILIS IB 4/91 + MA5 CLONE 30', 'EYE DROP'),
        ('W17', 'FC OIL', 'I/M'),
        ('W18', 'NOBILIS REO+IB+G+ND', 'I/M'),
        ('W18', 'CORYZA OIL 3', 'I/M'),
        ('W19', 'ANIVAC FADV', 'I/M'),
        ('W19', 'MG BAC', 'I/M'),
        ('W20', 'NEW LS MASS (RHONE MA)', 'D/W'),
        ('W21', 'MS VAC', 'I/M'),
        ('W22', 'NEW LS MASS (RHONE MA)', 'D/W'),
        ('W23', 'ANIVAC H9N2', 'I/M'),
        ('W28', 'GALLIVAC LASOTA IB MASS', 'D/W'),
        ('W32', 'CEVAC NBL', 'D/W'),
        ('W32', 'IBIRD', 'D/W'),
        ('W36', 'NEW LS MASS (RHONE MA)', 'D/W'),
        ('W40', 'GALLIVAC LASOTA IB MASS', 'D/W'),
        ('W44', 'CEVAC NBL', 'D/W'),
        ('W44', 'IBIRD', 'D/W'),
        ('W48', 'NEW LS MASS (RHONE MA)', 'D/W'),
        ('W52', 'GALLIVAC LASOTA IB MASS', 'D/W'),
        ('W56', 'CEVAC NBL', 'D/W'),
        ('W56', 'IBIRD', 'D/W'),
    ]

    for age_code, vaccine, route in schedule_data:
        offset = 0
        if age_code.startswith('D'):
            try:
                days = int(age_code[1:])
                offset = days
            except: pass
        elif age_code.startswith('W'):
            try:
                weeks = int(age_code[1:])
                offset = (weeks - 1) * 7 + 1
            except: pass

        est_date = flock.intake_date + timedelta(days=offset)

        v = Vaccine(
            flock_id=flock_id,
            age_code=age_code,
            vaccine_name=vaccine,
            route=route,
            est_date=est_date
        )
        db.session.add(v)

    if commit:
        safe_commit()
    else:
        db.session.flush()

def seed_arbor_acres_standards():
    filepath = os.path.join(basedir, 'Arbor_Acres_Plus_S_Complete_Production_Standards.xlsx')
    if not os.path.exists(filepath):
        return False, "File 'Arbor_Acres_Plus_S_Complete_Production_Standards.xlsx' not found."

    try:
        df = pd.read_excel(filepath)

        # Columns: 'Production Week', 'Age (Days)', 'Age (Weeks)', 'Std Egg Prod %', 'Std Egg Wt (g)', 'Std Hatch %', 'Std Cum Eggs HHA', 'Std Cum Hatching HHA', 'Std Cum Chicks HHA'

        # Filter: Age (Weeks) >= 25
        # Assuming Age (Weeks) is column 'Age (Weeks)'
        if 'Age (Weeks)' not in df.columns:
            return False, "Column 'Age (Weeks)' not found."

        df_filtered = df[df['Age (Weeks)'] >= 25]

        # Pre-fetch all existing standards into a dictionary keyed by week
        existing_standards = {s.week: s for s in Standard.query.all()}

        count = 0
        for index, row in df_filtered.iterrows():
            week = int(row['Age (Weeks)'])
            prod_week = int(row['Production Week']) if pd.notna(row['Production Week']) else None

            std_egg_prod = float(row['Std Egg Prod %']) if pd.notna(row['Std Egg Prod %']) else 0.0
            std_egg_wt = float(row['Std Egg Wt (g)']) if pd.notna(row['Std Egg Wt (g)']) else 0.0
            std_hatch = float(row['Std Hatch %']) if pd.notna(row['Std Hatch %']) else 0.0
            std_cum_eggs_hha = float(row['Std Cum Eggs HHA']) if pd.notna(row['Std Cum Eggs HHA']) else 0.0
            std_cum_hatching_hha = float(row['Std Cum Hatching HHA']) if pd.notna(row['Std Cum Hatching HHA']) else 0.0
            std_cum_chicks_hha = float(row['Std Cum Chicks HHA']) if pd.notna(row['Std Cum Chicks HHA']) else 0.0
            std_hatch_egg_pct = float(row['Std Hatching Egg %']) if 'Std Hatching Egg %' in row and pd.notna(row['Std Hatching Egg %']) else 0.0

            # Find or Create Standard
            s = existing_standards.get(week)
            if not s:
                s = Standard(week=week)
                db.session.add(s)
                existing_standards[week] = s

            # Update Fields
            s.production_week = prod_week
            s.std_egg_prod = std_egg_prod
            s.std_egg_weight = std_egg_wt
            s.std_hatchability = std_hatch
            s.std_cum_eggs_hha = std_cum_eggs_hha
            s.std_cum_hatching_eggs_hha = std_cum_hatching_hha
            s.std_cum_chicks_hha = std_cum_chicks_hha
            s.std_hatching_egg_pct = std_hatch_egg_pct

            count += 1

        safe_commit()
        return True, f"Imported/Updated {count} weeks of Arbor Acres standards."

    except Exception as e:
        import traceback
        traceback.print_exc()
        return False, f"Error importing Arbor Acres standards: {str(e)}"

def seed_standards_from_file():
    filepath = os.path.join(basedir, 'SLH Daily Aviagen.xlsx')
    if not os.path.exists(filepath):
        return False, "File 'SLH Daily Aviagen.xlsx' not found."

    try:
        # Standard BW starts at row 507 (0-indexed 506? No, process_import uses skiprows=507 so row 508 is index 0?)
        # Let's align with process_import logic: skiprows=507 means row 508 is index 0.
        # But previous inspection showed valid data there.

        df = pd.read_excel(filepath, sheet_name='TEMPLATE', header=None, skiprows=507, nrows=70)

        # Columns based on inspection:
        # 0: Week
        # 14: Standard Mortality % (e.g. 0.003 for 0.3%)
        # 32: Std Male BW
        # 33: Std Female BW
        # 19: Egg Prod % (Empty in file but mapped)
        # 27: Egg Weight (Empty)
        # 26: Hatchability (Empty)

        # Pre-fetch existing standards to avoid N+1 queries
        existing_standards = {s.week: s for s in Standard.query.all()}

        count = 0
        for index, row in df.iterrows():
            try:
                week_val = int(row[0])
            except (ValueError, TypeError):
                continue

            std_mort = float(row[14]) * 100 if pd.notna(row[14]) else 0.0 # Convert 0.003 to 0.3 if needed?
            # Wait, inspection showed 0.003. Usually displayed as %. 0.3% is reasonable daily? Or weekly?
            # Header says "STANDARD MORTALITY%". 0.003 is 0.3%.
            # app.py uses float. Let's store as percentage value (0.3).

            std_bw_m = int(row[32]) if pd.notna(row[32]) else 0
            std_bw_f = int(row[33]) if pd.notna(row[33]) else 0

            # Missing Data placeholders
            # Col 19: Egg Prod % (0.83 = 83%)
            std_egg_prod = float(row[19]) * 100 if pd.notna(row[19]) else 0.0

            # Col 27: Egg Weight (g)
            std_egg_weight = float(row[27]) if pd.notna(row[27]) else 0.0

            # Col 26 is H.E% (Hatching Egg %), NOT Hatchability.
            # We do not map it to std_hatchability unless we add std_hatching_egg_pct to Standard model.
            std_hatch = 0.0

            # Check existing
            s = existing_standards.get(week_val)
            if not s:
                s = Standard(week=week_val)
                db.session.add(s)
                existing_standards[week_val] = s

            s.std_mortality_male = std_mort # Using same for both sexes if only one col
            s.std_mortality_female = std_mort
            s.std_bw_male = std_bw_m
            s.std_bw_female = std_bw_f
            s.std_egg_prod = std_egg_prod
            s.std_egg_weight = std_egg_weight
            s.std_hatchability = std_hatch

            count += 1

        safe_commit()
        return True, f"Seeded/Updated {count} weeks of standards."

    except Exception as e:
        return False, f"Error seeding standards: {str(e)}"


INITIAL_USERS = [
    {'name': 'Admin', 'role': 'Admin', 'dept': 'Admin', 'status': 'Active'},
    {'name': 'Management', 'role': 'Management', 'dept': 'Management', 'status': 'Active'},
    {'name': 'Hatchery User', 'role': 'User', 'dept': 'Hatchery', 'status': 'Active'},
    {'name': 'Farm User', 'role': 'User', 'dept': 'Farm', 'status': 'Active'}
]
