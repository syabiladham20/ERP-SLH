# SLH-OP Architecture and Knowledge Base (AGENTS.md)

This document is the system prompt and knowledge base for any AI agent interacting with the SLH-OP codebase. It contains critical rules regarding architecture, PythonAnywhere deployments, offline caching, database migrations, and our specific coding style preferences.

## 1. System Architecture & Multitenancy
- **Farm Scoping:** The application uses a multi-farm architecture. Core models like `User`, `House`, `Flock`, and `HatcheryEggReceipt` are strictly scoped to a specific `Farm` via a `farm_id` foreign key. Legacy data assumes `farm_id = 1` ('Farm A').
- **Department Isolation:** The application is split into operational departments: `Breeder` (formerly Farm), `Hatchery`, and `Broiler`.
- **Role Hierarchy:** Roles are structured as `Admin` > `Management` > `Manager` > `Supervisor` > `Worker`. Admins and Management have broad access. Workers are restricted from dashboards and are routed directly to data entry views.

## 2. Progressive Web App (PWA) & Offline Caching
- **Service Worker Strategy (`sw.js`):**
  - **Network-First** for HTML navigations. Successful responses are dynamically cached.
  - **Cache-First** for static assets (CSS, JS, images).
- **Offline Mirror & IndexedDB:** Instead of complex offline queues, we use an `offline_mirror` approach for read-only access.
  - While online, `offline_sync.js` fetches a payload from `/api/offline_snapshot` and upserts it into an IndexedDB database (`slh_offline_db`).
  - This payload contains the last 14 days of detailed flock performance logs.
  - When the device goes offline, HTML fetch failures fallback to the `/offline_mirror` route, which reads from IndexedDB and uses Chart.js to render the dashboard locally.
  - **Form Submission Restrictions:** There is NO offline queueing for form data. When `navigator.onLine` is false, all `<form>` elements get an `opacity-75` class and submit events are `preventDefault()`'d. Data entry MUST be done online.
- **Push Notifications:** The service worker also handles push events with `farm-alert` tags.

## 3. Database & Schema Rules (Flask-Migrate)
- **Strict Alembic Enforcement:** All schema changes must use `flask db migrate` and `flask db upgrade`. **Never** execute `ALTER TABLE` manually on the production database.
- **Model Decoupling (Breeder vs Broiler):**
  - Breeder bodyweight is decoupled into `FlockBodyweight` and `FlockBodyweightPartition`.
  - Broiler bodyweight remains integrated strictly within the `BroilerDailyLog` table.
- **Data Transfer Scripts:** When extracting legacy data from decoupled columns, use raw SQL via `db.session.execute(text('...')).mappings().fetchall()` to prevent `AttributeError` on SQLAlchemy 2.0+ row objects.
- **Bypassing Bad Migrations:** If an Alembic migration fails but the chain needs to be preserved, neutralize it by replacing the `upgrade()` and `downgrade()` logic with `pass`.

## 4. Coding Style & UI/UX Preferences
- **Dark Mode Implementation:** We use Tabler's native `data-bs-theme`. User preferences are stored in `localStorage`.
- **CSS Specificity:** Do not use inline `text-body` classes or conflicting Bootstrap utility classes. Use semantic global rules in `custom.css` targeted via the `[data-bs-theme="dark"]` selector.
- **Chart.js Adaptability:** When toggling themes, dispatch a `themeChanged` window event. Chart configurations must listen to this event to dynamically update grid/text colors and call `.update()`.
  - **Buffer Zones:** Charts requiring a visual top buffer (mortality/culls) must set the Y-axis `max` to 1.1 times the max data value.
  - **Plugins:** Data labels (`datalabels`) must use dynamic coloring based on the theme and be anchored with `align: 'top'` and `anchor: 'end'`.
- **Defensive Jinja Templating:** Use `.get()` for dictionary access in templates (e.g., `m.get('property')`) to prevent `UndefinedError` crashes. Build maps using defensive checks like `hasattr(s, 'week')`.
- **Form UI:**
  - For percentages, display the human-readable format (e.g., 16%) in the frontend, but divide by 100 before saving to the DB.
  - Section headers should dynamically display the selected `House Name` using JavaScript, while individual input labels should remain clean.
  - Inline editable rows must support a 'Cancel' action that triggers `form.reset()` to restore the original value.
  - All read-only fractional metrics round to 1-2 decimal places depending on context (e.g., FCR to 2, Feed/Weight to 1), but input fields must retain full precision.

## 5. Deployment Rules (PythonAnywhere & GitHub Actions)
- **Automated Deployment:** Production deployments are managed via `deploy.sh`, which pulls the code, runs `flask db upgrade`, and touches the WSGI file (`/var/www/syabiladham_pythonanywhere_com_wsgi.py`) to restart the workers.
- **GitHub Actions Configuration:** Define environment variables (like `DATABASE_URL`) strictly in the YAML `env` block. Do not write a `.env` file via a bash step in CI workflows.
- **Dynamic Environments:** Use `FLASK_ENV` in `config.py` to toggle branding colors (Arbor Acres Blue for prod, Red for dev/staging).

## 6. Access Control & Security
- **Authentication Routes:** Local login is strictly at `/login` (not `/auth/login`).
- **Decorators:** Ensure access control decorators (`@dept_required`, `@role_required`) normalize string checks with `.strip().lower()`. If a check fails, return `abort(403)` rather than a dynamic redirect to prevent infinite loops.
- **Admin Supremacy:** Always explicitly grant `Admin` absolute access in all route decorators and UI visibility checks.
- **Rate Limiting:** Apply `@limiter.limit` strictly on sensitive routes. Do not define `default_limits` globally in `extensions.py`.
- **CSRF Token:** Set `WTF_CSRF_TIME_LIMIT = None` in `config.py` to prevent token expiration on active sessions. Catch `CSRFError` globally and differentiate between AJAX/API responses (JSON) and standard form submissions (HTML).
