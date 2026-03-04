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

---

## Evaluating the $10/month "Developer" Plan

You also looked at the standard **Developer ($10/month)** plan:
- **Web apps:** 1 (Custom domain supported)
- **CPU time:** 5,000 seconds per day
- **Disk space:** 5 GB
- **Traffic rating:** "Enough power to run a typical 150,000 hit/day website"

### Verdict: This is the PERFECT Plan for You

This plan aligns exactly with the "Ideal Configuration" calculated above. It is highly recommended that you choose this plan over the custom $39.05 plan.

**Why it is a perfect fit:**
1. **5,000 CPU Seconds is Huge for Your App:** As mentioned, your 5 users will barely scratch 300 CPU seconds a day. 5,000 seconds is massive. You could easily run your daily backups, pre-aggregation scripts, and real-time WhatsApp alerts, and you still wouldn't even hit 10% of this limit.
2. **150,000 hits/day:** Your app will likely see under 1,000 hits (page loads/saves) per day from 5 users. This means you have a 150x buffer for traffic spikes.
3. **5 GB Disk Space is Plenty:** 99% of your data is just text stored in a database, which takes up mere megabytes. 5 GB is more than enough to store the application code, years of database logs, and a reasonable amount of user-uploaded clinical note photos. If you ever hit the 5 GB limit years from now, you can upgrade just the storage for a few extra dollars without changing your whole plan.
4. **Cost-Effective:** At $10/month, you are getting enterprise-grade reliability and plenty of overhead for future growth, saving you almost $350 a year compared to the $39.05/month custom plan.

---

## Your Selected $17.00/month Custom Postgres Plan

Because the standard $10/month "Developer" plan uses **MySQL** instead of **PostgreSQL**, and your codebase is actively preparing for a migration to PostgreSQL, you have opted for a **$17.00/month Custom Plan**.

**Specs:**
- **CPU time:** 5,000 seconds
- **Web apps:** 1
- **Web workers:** 3
- **Always-on tasks:** 1
- **Disk space:** 5 GB
- **Postgres disk space:** 1 GB
- **Price:** $17.00 / month

### Verdict: An Excellent Choice

This is a fantastic configuration. Here is why it works perfectly for you:

1. **PostgreSQL Support:** The primary reason for the extra $7/month is access to the dedicated PostgreSQL server. Since your application's `executive_dashboard` relies on heavy SQL aggregations (like `to_char` for dates), PostgreSQL will handle these analytical queries much faster and more reliably than SQLite or MySQL.
2. **1 GB Postgres Storage:** As mentioned earlier, text data is incredibly small. 1 GB of database storage will comfortably hold all your daily logs, clinical notes, and farm metrics for the next 5 to 10 years without breaking a sweat.
3. **3 Web Workers:** Moving from 2 workers to 3 workers provides an extra layer of stability. If two users are simultaneously uploading photos or generating a heavy dashboard, the third worker is still immediately available to load the site instantly for the next user.
4. **1 Always-on Task:** This gives you the flexibility to build a continuous background worker (like a Celery worker or a dedicated polling script for WhatsApp API responses) in the future without needing to upgrade your plan again.

---

## When Should You Consider Upgrading?

Even though the $10/month plan is perfect for now, you should monitor your usage over time. Here are the exact triggers for when you should consider upgrading your plan:

1. **Storage Hits 4.5 GB:** Check your PythonAnywhere dashboard occasionally. If your storage usage creeps up to 4.5 GB (usually due to thousands of uploaded clinical note photos or un-deleted daily database backups), you can easily add more storage for a few dollars a month via the custom plan slider.
2. **CPU "Tarpitting" Occurs:** If you consistently exceed your 5,000 CPU seconds limit, PythonAnywhere will put your app in the "tarpit." This means your app will still work, but it will be given a lower priority and will load **very slowly**. If your users start complaining that the app takes 10-20 seconds to load a page, check your CPU usage graph. If it's hitting the red line, it's time to upgrade your CPU allocation.
3. **You Need Multiple Applications:** The $10/month plan only allows 1 web app (e.g., `farm.yourdomain.com`). If you ever need to host a completely separate application (like a public marketing website or a different tool on a different subdomain), you will need to upgrade to a plan that supports 2+ web apps.
4. **"Worker timeouts" in Error Logs:** If your users experience "504 Gateway Timeout" or "502 Bad Gateway" errors, check your PythonAnywhere `error.log`. If you see a lot of "worker timeout" messages, it means your current web workers are overwhelmed by too many simultaneous users. *At that point*, you should upgrade to add more web workers (e.g., from the default 2 up to 3 or 4).