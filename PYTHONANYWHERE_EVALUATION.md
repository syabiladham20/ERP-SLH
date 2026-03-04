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