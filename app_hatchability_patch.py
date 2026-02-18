def process_hatchability_import(file):
    import pandas as pd
    xls = pd.ExcelFile(file)
    # Assume data is in the "Data" sheet or the first sheet if "Data" not found
    sheet_name = "Data" if "Data" in xls.sheet_names else xls.sheet_names[0]

    # Read header first to determine structure
    df = pd.read_excel(xls, sheet_name=sheet_name)

    # Required headers logic from template
    # Template: A=Setting, B=Candling, C=Hatching, D=FlockID, E=EggSet, F=Clear, G=%, H=Rotten, I=%, J=Hatchable, K=%, L=TotalHatched, M=%, N=MaleRatio

    # We will iterate row by row.
    # Check for empty df
    if df.empty:
        return 0, 0

    # Check columns
    # If headers are 'Setting Date', 'Flock ID' etc.

    col_map = {}

    def normalize(s):
        return str(s).strip().lower().replace(' ', '_')

    for i, col in enumerate(df.columns):
        norm = normalize(col)
        if 'setting' in norm and 'date' in norm: col_map['setting_date'] = i
        elif 'candling' in norm and 'date' in norm: col_map['candling_date'] = i
        elif 'hatching' in norm and 'date' in norm: col_map['hatching_date'] = i
        elif 'flock' in norm: col_map['flock_id'] = i
        elif 'egg' in norm and 'set' in norm: col_map['egg_set'] = i
        elif 'clear' in norm and '%' not in norm: col_map['clear_eggs'] = i
        elif 'rotten' in norm and '%' not in norm: col_map['rotten_eggs'] = i
        elif 'hatched' in norm and ('total' in norm or 'chicks' in norm): col_map['hatched_chicks'] = i
        elif 'male' in norm and 'ratio' in norm: col_map['male_ratio'] = i

    # Fallback to fixed indices if not found (Template standard)
    if 'setting_date' not in col_map: col_map['setting_date'] = 0
    if 'candling_date' not in col_map: col_map['candling_date'] = 1
    if 'hatching_date' not in col_map: col_map['hatching_date'] = 2
    if 'flock_id' not in col_map: col_map['flock_id'] = 3
    if 'egg_set' not in col_map: col_map['egg_set'] = 4
    if 'clear_eggs' not in col_map: col_map['clear_eggs'] = 5
    if 'rotten_eggs' not in col_map: col_map['rotten_eggs'] = 7 # H
    if 'hatched_chicks' not in col_map: col_map['hatched_chicks'] = 11 # L
    if 'male_ratio' not in col_map: col_map['male_ratio'] = 13 # N

    def get_val(row, key, transform=None):
        idx = col_map.get(key)
        if idx is not None and idx < len(row):
            val = row.iloc[idx]
            if pd.isna(val): return None # Explicitly None for Blanks/NaN

            # Check for Empty String or Whitespace
            if isinstance(val, str) and not val.strip():
                return None

            if transform:
                try: return transform(val)
                except: return None
            return val
        return None

    def parse_date(d):
        if hasattr(d, 'date'): return d.date()
        if isinstance(d, str):
            for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y']:
                try: return datetime.strptime(d, fmt).date()
                except: continue
        return None

    # Pre-fetch data for matching
    all_houses = House.query.all()
    house_map = {h.name: h.id for h in all_houses} # Name -> ID

    # Fetch all flocks, organize by house
    all_flocks = Flock.query.order_by(Flock.intake_date.desc()).all()
    flocks_by_house = {} # house_id -> list of Flock objects sorted desc
    for f in all_flocks:
        if f.house_id not in flocks_by_house:
            flocks_by_house[f.house_id] = []
        flocks_by_house[f.house_id].append(f)

    created_count = 0
    updated_count = 0

    for index, row in df.iterrows():
        # Validations
        s_date = get_val(row, 'setting_date', parse_date)
        f_name_input = get_val(row, 'flock_id', str)

        if not s_date or not f_name_input:
            continue

        f_name = f_name_input.strip()

        # 1. Match House
        house_id = house_map.get(f_name)
        if not house_id:
            # Skip if House not found (as per requirement)
            continue

        # 2. Match Flock in House by Date
        # Find first flock where intake_date <= s_date
        target_flock_id = None
        candidates = flocks_by_house.get(house_id, [])

        for f in candidates:
            if f.intake_date <= s_date:
                target_flock_id = f.id
                break

        if not target_flock_id:
            # No valid flock found for this date
            continue

        # Extract values (None if blank)
        c_date = get_val(row, 'candling_date', parse_date)
        h_date = get_val(row, 'hatching_date', parse_date)
        e_set = get_val(row, 'egg_set', int)
        c_eggs = get_val(row, 'clear_eggs', int)
        r_eggs = get_val(row, 'rotten_eggs', int)
        h_chicks = get_val(row, 'hatched_chicks', int)

        # Always fetch Male Ratio from Farm Database
        # Note: We do not update male_ratio_pct from Excel unless logic changes.
        # User requested: "Validation: Ensure that the importer still checks that the Flock ID and Setting Date match before applying any updates." - done.
        # "Audit Logging: If an update occurs via Excel, log it... (Fields: Clear Eggs, Culls)".
        m_ratio, _ = calculate_male_ratio(target_flock_id, s_date)

        # Check existing record
        existing = Hatchability.query.filter_by(flock_id=target_flock_id, setting_date=s_date).first()
        if existing:
            # Smart Patch Update
            updated_fields = []

            # Helper to update only if not None
            def update_if_present(obj, attr, val, field_name):
                if val is not None:
                    old_val = getattr(obj, attr)
                    if old_val != val:
                        setattr(obj, attr, val)
                        updated_fields.append(field_name)

            update_if_present(existing, 'candling_date', c_date, 'Candling Date')
            update_if_present(existing, 'hatching_date', h_date, 'Hatching Date')
            update_if_present(existing, 'egg_set', e_set, 'Egg Set')
            update_if_present(existing, 'clear_eggs', c_eggs, 'Clear Eggs')
            update_if_present(existing, 'rotten_eggs', r_eggs, 'Rotten Eggs')
            update_if_present(existing, 'hatched_chicks', h_chicks, 'Hatched Chicks')

            # Male Ratio is always updated from calculation? Or only if no update provided?
            # Usually automated fields should be refreshed.
            if existing.male_ratio_pct != m_ratio:
                 existing.male_ratio_pct = m_ratio
                 # Implicit update, maybe not logged as user change

            if updated_fields:
                updated_count += 1
                print(f"[AUDIT] Hatchery Record updated via Excel Import (Fields: {', '.join(updated_fields)}) for Flock {target_flock_id} on {s_date}")

        else:
            # Insert Record (Only if minimum data is present?)
            # If creating new, we need defaults for non-provided fields (0 or None)
            # Default dates if missing
            final_c_date = c_date or (s_date + timedelta(days=18))
            final_h_date = h_date or (s_date + timedelta(days=21))

            h = Hatchability(
                flock_id=target_flock_id,
                setting_date=s_date,
                candling_date=final_c_date,
                hatching_date=final_h_date,
                egg_set=e_set or 0,
                clear_eggs=c_eggs or 0,
                rotten_eggs=r_eggs or 0,
                hatched_chicks=h_chicks or 0,
                male_ratio_pct=m_ratio
            )
            db.session.add(h)
            created_count += 1

    db.session.commit()
    return created_count, updated_count
