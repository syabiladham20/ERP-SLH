# Deployment Guide & Recommendations (PythonAnywhere)

## Recommended Configuration for 30+ Houses Expansion

Based on your current expansion plans (30 houses, 12 new intakes this year) and the screenshot provided, here is the recommended configuration for a "smooth experience" while optimizing costs.

### Summary: You are likely over-provisioning "Web Workers".

| Feature | Your Selection (Image) | **Our Recommendation** | Reasoning |
| :--- | :--- | :--- | :--- |
| **CPU Seconds** | 40000s | **40000s** (Limit) | Good safety margin. Most web requests are fast, but reports use CPU. Keep this high to avoid throttling. |
| **Web Apps** | 1 | **1** | Standard. |
| **Web Workers** | 20 | **2 - 4** | **This is the biggest cost driver.** For 30 houses with ~5-10 concurrent users (staff entering data), 20 workers is huge overkill. 4 workers can easily handle 50+ concurrent users for this type of app. Start with **2 or 3**. You can always scale up later if needed. |
| **Always-on tasks** | 1 | **1** | **Essential.** Keep this for running nightly database backups, email alerts, or heavy report generation in the background. |
| **Postgres** | Enabled | **Enabled** | **Critical.** Do not use SQLite for production with multiple users. Postgres handles concurrent writes much better and is more reliable. The default 125GB storage is plenty. |
| **Disk Space** | 40 GB | **10 - 20 GB** | Code is small (<100MB). Database is separate. Unless you store thousands of high-res photos, 10-20GB is enough. 40GB is safe but might be slightly more expensive. |

### Expected Cost Savings
By reducing Web Workers from 20 to 3-4, you could likely drop the monthly cost significantly (possibly by 50% or more) without sacrificing *perceivable* performance.

---

## Technical Setup for Smooth Scaling

### 1. Switch to PostgreSQL
The app is currently configured to use SQLite by default. For 30 houses and multiple users entering data simultaneously, SQLite will hit "Database Locked" errors.

**Steps:**
1.  In the PythonAnywhere "Databases" tab, initialize the Postgres database.
2.  Get the database URL (e.g., `postgres://super:password@...`).
3.  Set the `DATABASE_URL` environment variable in your `.env` file (or WSGI configuration):
    ```bash
    DATABASE_URL=postgresql://super:password@...
    ```
4.  Run the setup script again to migrate the schema to Postgres:
    ```bash
    bash setup_pa.sh
    ```

### 2. WSGI Configuration
PythonAnywhere requires a WSGI file to serve the app. We have added a `wsgi.py` file to the repository. Point your "Web" tab's WSGI configuration file to:

```python
# /var/www/your_username_pythonanywhere_com_wsgi.py
import sys
import os

# Add your project directory to the sys.path
project_home = '/home/your_username/your_project_folder'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# Set environment variables if not using a .env file loader in app
# os.environ['DATABASE_URL'] = '...'

from app import app as application
```

### 3. Background Tasks (Optional but Recommended)
Use the "Always-on task" or "Scheduled task" to run daily backups:

```bash
pg_dump -h <host> -U <user> <dbname> > /home/your_username/backups/backup_$(date +%F).sql
```

## Performance Tips
-   **Aggregated Reports**: The "Yearly ISO" report processes a lot of data. It is currently optimized to filter by year (processing ~1 year of data at a time). This should remain fast (< 2 seconds) even with 30 houses.
-   **Static Files**: Ensure you configure the "Static Files" section in PythonAnywhere Web tab to serve `/static/` directly, rather than passing it through Flask. This saves CPU.
    -   URL: `/static/` -> Directory: `/home/your_username/your_project/static`
