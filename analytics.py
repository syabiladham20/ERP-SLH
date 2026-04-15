from datetime import datetime, timedelta

# Common Poultry Diseases in Malaysia / Tropical Regions
DISEASE_KNOWLEDGE_BASE = {
    "Newcastle Disease (ND)": {
        "keywords": ["twisted neck", "paralysis", "tremors", "greenish droppings", "respiratory distress", "drop in egg production", "nervous signs", "gasping", "torticollis"],
        "severity": "High"
    },
    "Infectious Bronchitis (IB)": {
        "keywords": ["snicking", "coughing", "sneezing", "rushing sounds", "wet droppings", "misshapen eggs", "watery albumen", "wrinkled eggs", "pale eggs"],
        "severity": "High"
    },
    "Infectious Bursal Disease (IBD / Gumboro)": {
        "keywords": ["vent picking", "whitish diarrhea", "dehydration", "depression", "ruffled feathers", "prostrate", "bursa enlarged", "hemorrhage in thigh"],
        "severity": "High"
    },
    "Chronic Respiratory Disease (CRD / Mycoplasma)": {
        "keywords": ["swollen face", "foamy eyes", "nasal discharge", "tracheal rales", "coughing", "snicking", "reduced feed intake", "unthriftiness"],
        "severity": "Medium"
    },
    "Coccidiosis": {
        "keywords": ["bloody droppings", "orange droppings", "mucus in droppings", "pale comb", "huddling", "ruffled feathers", "anemia", "blood in caeca"],
        "severity": "Medium"
    },
    "Necrotic Enteritis": {
        "keywords": ["depression", "sudden death", "dark droppings", "sticky droppings", "foul smell", "intestinal necrosis", "turkish towel"],
        "severity": "High"
    },
    "Fowl Cholera": {
        "keywords": ["swollen wattles", "swollen comb", "lameness", "greenish diarrhea", "sudden death", "purple comb", "cyanosis"],
        "severity": "High"
    },
    "Coryza": {
        "keywords": ["swollen face", "foul smelling discharge", "nasal discharge", "swollen eyes", "conjunctivitis", "sneezing"],
        "severity": "Medium"
    },
    "Heat Stress": {
        "keywords": ["panting", "wings spread", "prostrate", "increased water intake", "reduced feed intake", "cannibalism"],
        "severity": "Medium"
    },
    "Salmonella (Pullorum/Fowl Typhoid)": {
        "keywords": ["white diarrhea", "chalky droppings", "huddling", "blindness", "joint swelling", "pasting vents"],
        "severity": "High"
    }
}

def predict_diseases(note_text):
    """
    Scans the clinical note text for keywords and returns a list of potential diseases.
    """
    if not note_text:
        return []

    found_diseases = []
    text_lower = note_text.lower()

    for disease, info in DISEASE_KNOWLEDGE_BASE.items():
        matched_keywords = []
        for keyword in info['keywords']:
            if keyword in text_lower:
                matched_keywords.append(keyword)

        if matched_keywords:
            found_diseases.append({
                "name": disease,
                "severity": info['severity'],
                "matched_symptoms": matched_keywords
            })

    # Sort by severity (High first)
    found_diseases.sort(key=lambda x: 0 if x['severity'] == 'High' else 1)

    return found_diseases

def calculate_feed_cleanup_duration(start_time_str, end_time_str):
    """
    Calculates duration in minutes between two time strings (HH:MM).
    Returns None if invalid.
    """
    if not start_time_str or not end_time_str:
        return None

    try:
        # Check if format includes seconds, if so strip them or parse accordingly
        # But app.py uses %H:%M usually.
        # Let's try flexible parsing
        fmt = '%H:%M'
        if len(start_time_str) > 5: fmt = '%H:%M:%S'

        t1 = datetime.strptime(start_time_str, fmt)
        t2 = datetime.strptime(end_time_str, fmt)

        # Handle overnight cleanup (End < Start)
        if t2 < t1:
            t2 += timedelta(days=1)

        duration = (t2 - t1).total_seconds() / 60 # Minutes
        return int(duration)
    except ValueError:
        return None

def analyze_health_events(flock_logs):
    """
    Processes a list of DailyLog objects to identify health events.
    Returns a list of event dictionaries sorted by date (descending).
    """
    events = []

    # Sort logs by date ascending to calculate rolling averages
    sorted_logs = sorted(flock_logs, key=lambda x: x.date)

    # Rolling Window Helpers
    rolling_mortality = [] # List of (mortality_total_pct)
    rolling_water = []     # List of (water_per_bird)
    rolling_cleanup = []   # List of (cleanup_duration)

    WINDOW_SIZE = 7

    for log in sorted_logs:
        # 1. Basic Data Extraction
        date_str = log.date.strftime('%Y-%m-%d')

        # Metrics
        stock_start = (log.flock.intake_male + log.flock.intake_female) # Simplified baseline or use enriched logic
        # Ideally we should use the enriched metrics from `metrics.py` but for simplicity in this standalone analysis:
        # We will recalculate basic metrics or use raw values if enriched data isn't passed.
        # However, to be accurate on deviations, we need "Per Bird" metrics.

        # Let's rely on raw values and simple calc for now to avoid circular imports or heavy dependency.
        # app.py passes `logs` which are SQLAlchemy objects.

        # Note Parsing
        notes = log.clinical_notes or ""
        predicted_diseases = predict_diseases(notes)

        # Feed Cleanup
        cleanup_duration = calculate_feed_cleanup_duration(log.feed_cleanup_start, log.feed_cleanup_end)

        # Mortality % (Daily) - Approximate using Intake as denominator if stock history is complex
        # Or calculate cumulative loss.
        # For trend analysis, raw count is okay if stock doesn't change drastically, but % is better.
        # Let's use a simplified stock estimate: Intake. (Deviation will still show spikes)
        current_mort = (log.mortality_male + log.mortality_female + log.culls_male + log.culls_female)

        # Water
        water_vol = log.water_intake_calculated or 0

        # 2. Calculate Deviations (vs Rolling Average of previous days)
        def get_avg(lst):
            return sum(lst) / len(lst) if lst else 0

        avg_mort = get_avg(rolling_mortality)
        avg_water = get_avg(rolling_water)
        avg_cleanup = get_avg(rolling_cleanup)

        # Deviations
        mort_diff = current_mort - avg_mort
        water_diff = water_vol - avg_water
        cleanup_diff = (cleanup_duration - avg_cleanup) if (cleanup_duration is not None and avg_cleanup > 0) else 0

        # Thresholds for "Significant Event"
        # 1. Clinical Notes exist
        # 2. Mortality Spike (> 50% increase vs avg AND > 5 birds)
        # 3. Water Drop (> 10% decrease)
        # 4. Feed Cleanup Increase (> 30 mins)

        is_significant = False
        reasons = []

        if notes:
            is_significant = True
            reasons.append("Clinical Signs Observed")

        if avg_mort > 0 and current_mort > avg_mort * 1.5 and current_mort > 5:
            is_significant = True
            reasons.append(f"Mortality Spike (+{int(mort_diff)})")
        elif avg_mort == 0 and current_mort > 5:
             is_significant = True
             reasons.append(f"Mortality Spike ({current_mort})")

        if avg_water > 0 and water_vol < avg_water * 0.9 and water_vol > 0:
            is_significant = True
            pct_drop = int((1 - water_vol/avg_water)*100)
            reasons.append(f"Water Intake Drop (-{pct_drop}%)")

        if avg_cleanup > 0 and cleanup_duration and cleanup_duration > avg_cleanup + 30:
            is_significant = True
            reasons.append(f"Slow Feed Cleanup (+{int(cleanup_diff)}m)")

        # 3. Construct Event Object
        if is_significant:
            event = {
                "date": log.date,
                "age_week": (log.date - log.flock.intake_date).days // 7 + 1,
                "notes": notes,
                "predicted_diseases": predicted_diseases,
                "metrics": {
                    "mortality": current_mort,
                    "mortality_avg": round(avg_mort, 1),
                    "water": round(water_vol, 1),
                    "water_avg": round(avg_water, 1),
                    "cleanup_min": cleanup_duration,
                    "cleanup_avg": round(avg_cleanup, 1)
                },
                "flags": reasons
            }
            events.append(event)

        # 4. Update Rolling Windows
        rolling_mortality.append(current_mort)
        if len(rolling_mortality) > WINDOW_SIZE: rolling_mortality.pop(0)

        if water_vol > 0:
            rolling_water.append(water_vol)
            if len(rolling_water) > WINDOW_SIZE: rolling_water.pop(0)

        if cleanup_duration is not None:
            rolling_cleanup.append(cleanup_duration)
            if len(rolling_cleanup) > WINDOW_SIZE: rolling_cleanup.pop(0)

    # Return reversed (Newest first)
    return events[::-1]
