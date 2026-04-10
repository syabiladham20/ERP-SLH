# SLH-OP Data Architecture & Visualization Breakdown

This document provides a detailed breakdown of the Single Source of Truth (SSOT), data processing logic, and chart visualization within the SLH-OP poultry management system.

## 1. The Single Source of Truth (SSOT): Database Models
The raw data is strictly stored in the SQLite/PostgreSQL database via SQLAlchemy models defined in `app.py`. This constitutes the SSOT. The system is designed such that raw inputs are preserved and derived metrics are calculated dynamically.

### Core Models (`app.py`)
*   **`Flock`**: The primary entity representing a batch of birds in a specific house.
    *   *Raw Data:* `intake_date`, `intake_male`, `intake_female`, `doa_male`, `doa_female`, `production_start_date`, `start_of_lay_date`.
    *   *Phase Baselines:* Stores starting stock when the phase switches to production (`prod_start_male`, `prod_start_female`, etc.).
*   **`DailyLog`**: The fundamental transactional record for daily flock data.
    *   *Mortality & Culls:* `mortality_male`, `mortality_female`, `culls_male`, `culls_female` (plus hospital variants).
    *   *Feed Intake:* `feed_male_gp_bird`, `feed_female_gp_bird` (Grams per Bird - **Crucial SSOT rule:** This is user input, not a derived metric). Total feed in Kg (`feed_male`, `feed_female`) is also stored but often dynamically recalculated in processing functions.
    *   *Production:* `eggs_collected`, `cull_eggs_jumbo`, `cull_eggs_small`, etc., `egg_weight`.
    *   *Body Weight:* `body_weight_male`, `body_weight_female`, `uniformity_male`, `uniformity_female`.
    *   *Water:* Raw meter readings (`water_reading_1/2/3`) and the pre-calculated 24h intake (`water_intake_calculated`).
*   **`Hatchability`**: Stores hatchery performance data per setting date.
    *   *Raw Data:* `egg_set`, `clear_eggs`, `rotten_eggs`, `hatched_chicks`.
*   **`Standard` / `GlobalStandard`**: Industry standards against which performance is benchmarked.

## 2. Data Processing & Logic (Backend)
The raw data is extracted from the SSOT and enriched with calculated metrics (percentages, cumulative totals, ratios) before being sent to the frontend.

### `metrics.py` (The Enrichment Engine)
This file is the core processing hub. It prevents the database schema from being bloated with derived fields.
*   **`enrich_flock_data(flock, logs, hatchability_data=None, custom_start_stock=None)`**: This is the most critical function. It iterates through a flock's sorted `DailyLog`s and generates a comprehensive list of dictionaries containing both raw and derived data for each day.
    *   *Phase Switching:* Dynamically determines if a flock is in 'Brooding', 'Growing', 'Pre-lay', or 'Production' based on age, feed programs, and egg production % (switching to Production automatically at 5% egg prod).
    *   *Stock Tracking:* Calculates the exact number of birds alive at the start and end of every day (`stock_male_start`, `stock_female_start`, `stock_male_prod_end`, etc.) by applying mortality, culls, and hospital transfers.
    *   *Calculated Metrics:* Computes daily percentages:
        *   `mortality_female_pct`, `mortality_male_pct`
        *   `egg_prod_pct` (Total Eggs / Active Female Stock)
        *   `hatch_egg_pct` (Hatching Eggs / Total Eggs)
        *   `water_per_bird`, `water_feed_ratio`
    *   *Cumulative Metrics:* Tracks running totals across the phase:
        *   `mortality_cum_female_pct`
*   **`aggregate_weekly_metrics(daily_stats)` & `aggregate_monthly_metrics(daily_stats)`**: Takes the output of `enrich_flock_data` and groups the daily dictionaries into biological weeks or calendar months, calculating sums (e.g., total eggs) and weighted averages (e.g., body weight, uniformity).

### `analytics.py` (Insight Generation)
*   **`analyze_health_events(flock_logs)`**: Scans daily logs for anomalies (mortality spikes >50% above a 7-day rolling average, water intake drops, feed cleanup delays).
*   **`predict_diseases(note_text)`**: Uses a predefined `DISEASE_KNOWLEDGE_BASE` to scan clinical notes for keywords (e.g., "bloody droppings") and flag potential diseases (e.g., "Coccidiosis").

### `app.py` (Routing & API Endpoints)
*   Routes like `/flock/<id>` (Flock Details) and `/api/chart_data/<id>` fetch the SSOT models, pass them through `metrics.py`, and construct the structured JSON payloads expected by the frontend charts.
*   **`calculate_flock_summary(flock, daily_stats)`**: Specifically calculates the Hen Housed Average (HHA) metrics (Total Eggs HHA, Chicks HHA) and Feed Efficiency (Feed per 100 Chicks) for the Production Summary dashboard.
*   **`get_iso_aggregated_data_sql(...)`**: A heavily optimized raw SQL function used in the Executive Dashboard to rapidly aggregate data across *all* active flocks by ISO Week/Month without relying on Python-level iteration.

## 3. Visualization: Tables & Charts (Frontend)
The presentation layer consumes the enriched dictionaries/JSON and renders them using HTML tables and JavaScript charting libraries.

### Core View Templates
*   **`flock_detail_readonly.html`**: The primary "Flock Dashboard".
    *   *Tables:* Jinja loops iterate directly over the `daily_stats` and `weekly_stats` generated by `metrics.py` to populate the "Daily Logs" and "Weekly Summary" tables.
    *   *Charts:* Uses **Chart.js**. The backend route pre-packages the data into strict arrays (e.g., `chart_data.dates`, `chart_data.egg_prod`) which are injected into the template as JSON (`{{ chart_data | tojson }}`).
    *   *Logic:* Javascript functions (`renderGeneralChart`, `renderWaterChart`, etc.) configure Chart.js datasets. It includes complex custom plugins like `dynamicYMaxPlugin` to automatically scale secondary axes (like Uniformity or Egg Prod %) based on which datasets the user has toggled visible.
*   **`flock_charts.html`**: A more analytical chart view.
    *   Uses **Plotly.js** instead of Chart.js for interactive, zoomable charting.
    *   Fetches data asynchronously via `fetch('/api/chart_data/<flockId>?mode=...')`.
    *   Includes logic to slice data arrays locally (`filterDataLocally`) when using Quick Filters (e.g., "Last 30 Days") to avoid redundant server calls.
*   **`executive_dashboard.html` / `additional_report.html`**: High-level overviews utilizing the output of `get_iso_aggregated_data_sql`.

### Visualization Rules (as seen in JS)
*   **Decimals:** Egg Prod %, Mortality % are strictly formatted to 2 decimal places. Water:Feed ratio is 2 decimal places (without the `%` sign).
*   **Sparse Datasets:** When plotting body weight partitions (`M1`, `F1`), the backend passes `null` for missing values rather than `0` so Chart.js breaks the line correctly instead of plunging to the x-axis.
*   **Data Labels:** The `chartjs-plugin-datalabels` is configured globally. It explicitly hides labels for "Standard" metrics (targets) to reduce clutter, showing labels only for actual performance data.

## 4. Other Supporting Files
*   **`gemini_engine.py`**: Integrates with Google's Gemini AI. It takes raw log data, strips identifying information using `privacy_filter.py`, sends it to the LLM for analysis ("spot mortality spikes, feed efficiency drops"), and then restores the names before returning insights to the dashboard.
*   **`privacy_filter.py`**: A utility class that swaps real `House` names with generic identifiers (e.g., "House 1") before sending data to external APIs to maintain data security.
*   **`init_db.py` / `seed_standards.py`**: Scripts used to generate the initial database schema and populate the `Standard` model with Arbor Acres breeder performance targets from an external source.
