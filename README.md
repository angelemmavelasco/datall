# Datall BI-ETL System

## What is Datall?

Datall is a Business Intelligence platform designed for commercial analytics, sales performance monitoring, and territory management.
The system processes operational data through an asynchronous ETL pipeline, allowing organizations to upload large volumes of sales, target, route, customer, and product records from Excel and CSV files.
It cleans and transforms this data in the background to provide interactive dashboards, KPI tracking, quota fulfillment metrics, and geospatial insights that support data driven decision making.

## Stack

### Backend
- Python 3.12
- Django 5.2
- Django Q2 (for background tasks)
- Pandas (for data processing)
- Openpyxl (for excel file reading)
- Gunicor / Uvicorn ASGI
- Whitenoise

### Frontend
- Django templates
- HTMX (by using `django-htmx`)
- Chart.js (for visualizations)
- CSSv4 (by using `tailwindcss/cli`)
- ApexCharts (for advanced visualizations)

### Database and Storages
- `DEBUG=True`: SQLite3 + local storage for media
- `DEBUG=False`: PostgreSQL + Cloudflare R2 storage for media (via S3 api / boto3)

### Integrated Tools
- Resend (for sending emails)
- Carto API (for geospatial visualizations)


## Requirements and how to run the project

### Cloning

```bash
# Clone the repo
git clone https://github.com/angelemmavelasco/datall.git
cd datall
```

Currently, the project has two varaints to be run after cloning the repo:
- By using docker
- By using local python environment 

### Docker environment
#### Requirements
- Docker / Docker Compose
- Python 3.12+

### Local python environment
#### Requirements
- Python 3.12+
- Node.js (v18+ o v20+) y npm
- Redis 7+ (active listening on port 6379)
- PostgreSQL 16+ (optional, works with sqlite3 as well if DEBUG=True in `config/settings.py`)

### Step by step for running the project

#### Local environment
1. Crate and activate virtual environment
```bash
python3 -m venv .venv
source .venv/bin/activate #on macos
.venv\Scripts\activate #on Windows
```
2. Install dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```
3. Install frontend dependencies to compile CSS

```bash
npm install
npm run build:css
```
If editing design and view, you can leave runing in another terminal `npm run watch:css` to auto compile when changes are made.

4. Configure enviornment variables

Create a file named as `.env`in the root project directory and add the following variables:

```dotenv
DEBUG=True
SECRET_KEY=replace-with-a-strong-secret-key-here
ALLOWED_HOSTS=localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000

# Redis for background tasks
REDIS_HOST=127.0.0.1
REDIS_PORT=6379

# Optional for development (only if specific modules are used):
# RESEND_API_KEY=
# CARTO_API_KEY=
# DEEPSEEK_API_KEY=
```
By having `DEBUG=True`, django uses SQLite3 as default database, creating a file named as `db.sqlite3`in the root project directory, avoiding
Postgres configuration and usage, and R2 storage usage and configuration.

5. Start REDIS
Redis is required by django Q2 for ETL execution pipeline.
```bash
# If you have Redis installed locally:
redis-server

# Or through a quick Docker container:
docker run -d -p 6379:6379 --name datall_redis redis:7-alpine
```

6. Run migrations
```bash
python manage.py migrate
```

7. Create a superuser
```bash
python manage.py createsuperuser
```

8. Run development servers
Datall require two simultaneous processes.

    1. Run django development server

    ```bash
    python manage.py runserver
    ```

    2. Django Q2 cluster

    ```bash
    python manage.py qcluster
    ```

You can access datall at `http://localhost:8000` and login with the superuser created at step 7.

#### Docker compose
if you prefer not installing python and redis:

1. Create the `.env` file with corresponding variables.

2. Start the container

    - For development environment:
    ```bash
    docker compose -f docker-compose.dev.yml up --build
    ```
    - For complete stack (postgres + r2):
    ```bash
    docker compose up --build
    ```

3. Migrate and create superuser
```bash
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

You can access datall at `http://localhost:8000` and login with the superuser created at step 3.

## Workflows

### ETL process
Datall processes large volumes of commercial data without blocking user interaction through an asynchronous pipeline:

1. Extract (File Ingestion and Validation):
   - Users upload operational spreadsheets (`.xlsx`, `.xls`, `.csv`) via the web interface `/uploads/` (sales transactions, quotas, product catalogs, customer databases, or INEGI DENUE records).
   - Preliminary validation checks file format, integrity, and permissions (`BaseETLHelper`).
   - A `GeneratedReport` task record is created in `PENDING` status, and the file is stored in a temporary shared volume.

2. Queue (Asynchronous Task Dispatch):
   - The upload task is enqueued to Django Q2 using Redis as the message broker (`process_bulk_upload_task`).
   - HTTP requests return immediately, avoiding timeouts during heavy file processing.

3. Transform (Cleaning, Normalization and Business Rules):
   - The background worker (`qcluster`) picks up the task and inspects the payload using Pandas.
   - Handles multi-encoding detection (`utf-8`, `latin-1`, `cp1252`), cleans invalid characters, normalizes date and numerical formats, and matches relational keys (e.g. routes to employees, customers to sales).

4. Load (Bulk Upsert and Real-Time Feedback):
   - Data is committed in batch operations (`bulk_create` / `bulk_update`) into the target database (SQLite in development or PostgreSQL in production).
   - The report status updates to `COMPLETED` or `FAILED` with diagnostics (rows processed, created, updated, or validation errors).
   - The frontend updates live via HTMX polling without requiring a full page refresh.

---

### Commercial Analytics and Sales Intelligence
Once data is processed, the commercial intelligence workflow enables end users to explore and analyze operational performance:

1. Data Scoping and Filtering:
   - Users select date ranges (daily, monthly, yearly) and filter by management division, commercial route, or customer tier.
   - Dynamic role-based permissions adjust visible metrics (e.g. qualitative margin indicators for sales reps versus exact percentages for directors).

2. Executive Overview and KPI Evaluation:
   - Real-time aggregation of net sales, quotas, quota achievement percentage, volume in units, active buying customers, and gross profit margin.

3. Drill-down Analysis:
   - Timeline Evolution: Dual-axis charts comparing sales revenue vs physical units sold and cumulative quota progression.
   - Territory Comparison: Horizontal bar charts contrasting management regions against their respective monthly goals.
   - Route Ranking: Interactive tables ranking sales routes from highest to lowest revenue, with direct links to individual route profiles.

---

### Quota and Target Achievement
1. Quota Definition: Monthly commercial targets are established and assigned per route and managerial division.
2. Real-Time Progress Tracking: Throughout the month, daily net revenue is compared against proportional targets to calculate surpluses or deficits.
3. Pacing Alerts: Highlights routes or regions running behind schedule so managers can take corrective actions before the monthly close.

---

### Geospatial and Market Intelligence (Mapser)
1. Territory Mapping: Integrates customer locations and commercial routes with INEGI DENUE economic census data.
2. Interactive Visualization: Uses Carto API to plot sales points, commercial density, and prospect clusters.
3. Route Optimization: Helps managers identify unserved commercial zones and rebalance sales route territories based on geographic demand.

