# PythonAnywhere CPU Allocation Evaluation

## Summary

You have an allocation of **20,000 CPU seconds per day** (approx. 5.5 hours of dedicated CPU processing) on PythonAnywhere. Based on the current application architecture and expected traffic, this is **more than enough** to run the farm management web app.

## Breakdown of Expected Usage

### 1. Web Traffic (5 Users/Day)
The application primarily involves data entry and viewing dashboards (e.g., `executive_dashboard`, `flock_detail_readonly`).
- Most endpoints (e.g., rendering forms, saving a `DailyLog`) are extremely lightweight and execute in milliseconds.
- Heavy endpoints (e.g., `get_iso_aggregated_data_sql`, `enrich_flock_data`) perform on-the-fly calculations for the dashboards. Even for large datasets, these optimized raw SQL queries take less than a second of CPU time to execute.
- With 5 active users making several requests throughout the day, the cumulative CPU usage from HTTP requests will likely be less than **100-300 CPU seconds per day**.

### 2. General Overhead
Running a WSGI server (like Gunicorn/uWSGI) configured by PythonAnywhere consumes a very small baseline of CPU just to maintain worker processes. This is negligible and typically well under 1,000 CPU seconds daily for a low-traffic application.

---

## Suggested Background Tasks (Cron Jobs)
You currently do not have scheduled background tasks. To improve performance and reliability, consider scheduling the following tasks to run nightly (e.g., at midnight). None of these will significantly impact your 20,000-second quota.

1. **Database Backups:** A script to securely dump the database (`farm.db` or PostgreSQL) and upload it to a safe location (e.g., S3).
   - *Estimated CPU:* < 10 seconds per run.
2. **Data Pre-aggregation:** A script to pre-calculate heavy dashboard metrics (like the `executive_dashboard` ISO data) and store them in a cache or separate database table. This ensures the dashboard loads instantly for users during the day.
   - *Estimated CPU:* < 20 seconds per run.
3. **Daily Health Summary:** A nightly script that reviews the day's `DailyLog` entries across all flocks, summarizing mortality, feed, and water consumption, and sending a daily digest email to managers.
   - *Estimated CPU:* < 5 seconds per run.

---

## Real-Time Auto Alerts (Telegram/WhatsApp)

If you implement real-time auto-alerts (e.g., sending a Telegram or WhatsApp message the moment a user submits a `DailyLog` that indicates a mortality spike, water consumption drop, or disease prediction), the impact on your CPU usage will be **virtually zero**.

### Why?
1. **Network vs. CPU:** Sending a message to Telegram or WhatsApp involves making an HTTP request to their API (e.g., `requests.post('https://api.telegram.org/bot<token>/sendMessage')`). The application spends 99% of its time during this process simply **waiting** for the network to respond (I/O bound), rather than performing complex math or logic (CPU bound).
2. **Logic Complexity:** The logic to determine if an alert should be sent is simple arithmetic (e.g., `if mortality_pct > 0.5:` or `if water_intake < baseline:`). This takes a fraction of a millisecond of CPU time.
3. **Execution:** PythonAnywhere only charges CPU seconds for actual processor time used, not for time spent waiting on a network request to finish.

### Recommendation for Implementation
If you decide to implement real-time alerts:
- **Use Webhooks:** Integrate with the Telegram Bot API or WhatsApp Business API via standard Python `requests`.
- **Background Workers (Optional but Recommended):** If the external API is slow, it could make the user's web page load slowly while it waits for the message to send. To fix this, you can dispatch the alert task to a background queue (like Celery or RQ), but for 5 users, simply using a fire-and-forget background thread (`threading.Thread`) or running it inline is perfectly acceptable and keeps the codebase simple.

---

## When WOULD You Need High CPU Usage?
While your current setup is perfectly fine, you would only start hitting the 20,000 CPU seconds limit under the following specific conditions:

1. **Massive Increase in Traffic:** If you scale up from 5 daily users to **hundreds of users actively clicking through the application concurrently**. Every HTTP request requires a small amount of CPU to process; thousands of requests per hour would begin to stack up.
2. **Years of Historical Data (Without Caching):** Currently, the `executive_dashboard` aggregates data dynamically using SQL queries. If you accumulate 5 to 10 years of daily logs across dozens of flocks and do not implement **pre-aggregation** (as suggested above), the database will have to scan and compute millions of rows every single time a user loads the dashboard. This forces the CPU to work very hard.
3. **Heavy Excel Processing:** If users frequently (multiple times a day) upload massive, unoptimized Excel files containing tens of thousands of rows using pandas (`pd.read_excel`), parsing these files is a highly CPU-intensive task.
4. **Machine Learning / Predictive Models:** If you move away from your current rule-based Disease Prediction system and implement a heavy Machine Learning model (e.g., neural networks processing images or large datasets) directly on the PythonAnywhere server.
5. **Image Processing:** If users begin uploading thousands of high-resolution photos for the clinical notes, and your application is set up to resize, compress, or apply filters to those images on the server (using libraries like `Pillow`). Image manipulation is notoriously CPU-heavy.

---

## Evaluating Your Proposed PythonAnywhere Plan ($39.05/month)

You are looking at a custom plan with the following specs:
- **CPU time:** 10,000 seconds
- **Web apps:** 1
- **Web workers:** 5
- **Always-on tasks:** 1
- **Disk space:** 50 GB
- **Postgres disk space:** 20 GB

For **5 daily users**, this configuration is **overkill and unnecessarily expensive**. You can safely downgrade to save money without sacrificing any performance.

### The Ideal, Cost-Optimized Plan for 5 Users

Here is what you actually need:

*   **CPU time per day: 2,000 to 4,000 seconds (Downgrade)**
    *   *Why:* As calculated earlier, 5 users doing data entry and viewing dashboards will consume less than 300 seconds a day. Even 2,000 seconds (which is roughly the base "Hacker" plan level) gives you a massive 6x buffer for complex SQL queries or database backups. 10,000 is vastly more than you need.
*   **Number of web apps: 1 (Keep)**
    *   *Why:* You only need 1 app for the farm management system.
*   **Number of web workers: 2 (Downgrade)**
    *   *Why:* You selected 5 workers. A "worker" handles one HTTP request at a time. With 5 users, the chances of 5 people clicking "Save" or "Load Dashboard" at the *exact same millisecond* is incredibly low. **2 workers** are more than enough to handle your traffic smoothly.
*   **Number of always-on tasks: 0 or 1 (Optional)**
    *   *Why:* If you only use scheduled tasks (Cron jobs) for nightly backups or alerts, you do **not** need an "Always-on task" (which is meant for continuous loops, like a Discord bot). Scheduled tasks are included for free in paid plans. Set this to 0 unless you specifically build a continuous background queue (like Celery) later.
*   **Disk space: 5 GB to 10 GB (Downgrade)**
    *   *Why:* You selected 50 GB. The only files taking up space are the codebase, some Excel templates, and user-uploaded photos for clinical notes. Unless your users are uploading thousands of high-resolution, uncompressed photos every month, 5 GB to 10 GB will last you years. (You can always upgrade this later with one click if it gets full).
*   **Postgres disk space: 1 GB to 2 GB (Downgrade)**
    *   *Why:* You selected 20 GB. Text data (which makes up 99% of your database: daily logs, metrics, flock names) is tiny. 1 GB of PostgreSQL can hold literally millions of rows of `DailyLog` entries. 20 GB is meant for massive enterprise applications.

### Summary
By dropping your Web Workers to 2, Disk Space to 10 GB, Postgres to 2 GB, and CPU to 2,000-4,000 seconds, your monthly bill should drop from **$39.05** down to closer to **$10 to $15 per month**, and your 5 users will not notice any difference in speed or performance.