# 🔎 SEO Audit POC – Django + Celery

A simple, scalable, and observable SEO audit backend built with Django.

This project is designed as:

- 🧠 Evidence-first (database is source of truth)
- 🔁 Fully auditable (every run leaves a trail)
- ⚙️ Async and scalable (Celery + multiple queues)
- 📊 Observable (Flower + DB-backed run state)
- 🧱 Architected for growth (AI interpretation layer later)

---

# 🎯 Purpose

This POC analyzes a client's website and determines:

- Whether it ranks for relevant keywords
- Who its competitors are
- Why competitors outrank it
- What changes are needed to improve ranking

Every audit:

- Stores SERP snapshots
- Stores page snapshots
- Stores keyword sets
- Stores derived metrics
- Stores recommendation reasoning

Nothing is ephemeral.
The database is the source of truth.

---

# 🏗 Architecture Overview

Client → API → AuditRun → Celery Tasks → Evidence Tables → Analysis → Recommendations

Queues:

- `seo_light` (fast tasks)
- `seo_serp` (rate-limited SERP calls)
- `seo_heavy` (competitor scraping + analysis)

Core principle:

> Flower is visibility.
> Database is truth.

---

# 📂 Project Structure

```

seo_poc/
config/
apps/
seo/
models.py
services/
tasks/
providers/
docs/
README.md

````

---

# 🗄 Database Philosophy

The DB captures:

- AuditRun
- RunStep
- RunStepAttempt
- PageSnapshot
- SerpSnapshot
- KeywordResult
- Recommendation

Each step is:

- Idempotent
- Logged
- Retryable
- Observable

Snapshots are immutable.
Derived metrics are reproducible.

---

# 🚀 Getting Started

## 1️⃣ Create virtual environment

```bash
python -m venv venv
source venv/bin/activate
````

## 2️⃣ Install dependencies

```bash
pip install django djangorestframework celery redis psycopg2-binary
```

Add to `requirements.txt` if desired.

---

## 3️⃣ Configure environment

Set environment variables:

```bash
export DJANGO_SETTINGS_MODULE=config.settings
export CELERY_BROKER_URL=redis://localhost:6379/0
export CELERY_RESULT_BACKEND=redis://localhost:6379/1
```

---

## 4️⃣ Run migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

---

## 5️⃣ Start services

### Start Redis

```bash
redis-server
```

### Start Django

```bash
python manage.py runserver
```

### Start Celery workers

Light queue:

```bash
celery -A config worker -Q seo_light -l info
```

SERP queue:

```bash
celery -A config worker -Q seo_serp -l info
```

Heavy queue:

```bash
celery -A config worker -Q seo_heavy -l info
```

### Start Flower (observability)

```bash
celery -A config flower -l info
```

---

# 📡 API Endpoints (POC v1)

Create site:

```
POST /api/sites
```

Create audit run:

```
POST /api/sites/{id}/runs
```

Get run:

```
GET /api/runs/{run_id}
```

Get report:

```
GET /api/runs/{run_id}/report
```

Retry failed steps:

```
POST /api/runs/{run_id}/retry
```

---

# 🔁 Audit Lifecycle

1. Create AuditRun
2. Create RunSteps
3. Fetch client page
4. Extract keywords
5. Capture SERP
6. Fetch competitors
7. Analyze + Recommend
8. Finalize

All transitions recorded in DB.

---

# 🧠 Future Roadmap

* SERP fan-out per keyword (parallel scaling)
* AI interpretation layer
* Ranking delta tracking
* Local SEO scoring
* Backlink analysis
* OpenTelemetry tracing
* Prometheus metrics

---

# 📌 Design Principles

* No hidden state
* No silent failures
* DB > Worker memory
* Deterministic scoring before AI
* Evidence-linked recommendations

---

# 🏁 Status

POC architecture defined.
Models implemented.
Task orchestration in progress.

---

Built for learning.
Built for scale.
Built for visibility.

```

---

# 🔥 Now Your Repo Has

- Structure
- Spec
- Philosophy
- Operational clarity

---