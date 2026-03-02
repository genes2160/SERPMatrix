# 🔎 SEO Audit Engine

### Django • Celery • Outbox Pattern • Step-Orchestrated Workflow

A production-grade, step-driven SEO audit backend built with Django and Celery.

This system is designed to be:

* 🧠 **Evidence-first** — Database is the single source of truth
* 🔁 **Deterministic** — Step-based execution with strict ordering
* 🔄 **Self-healing** — Background reconciler resumes stuck runs
* 📨 **Reliable** — Outbox pattern for guaranteed task dispatch
* ⚙️ **Horizontally scalable** — Multi-queue Celery architecture
* 📊 **Observable** — DB-backed timeline + dashboard monitoring
* 🤖 **AI-extendable** — Structured interpretation layer built in

---
<img width="1361" height="634" alt="Screenshot 2026-03-02 191430" src="https://github.com/user-attachments/assets/b2d0d3c2-25e7-4a56-8bf7-4bde605fb49b" />
<img width="1363" height="636" alt="Screenshot 2026-03-02 191448" src="https://github.com/user-attachments/assets/13823329-79e5-4775-a980-5eea0196cff6" />
<img width="1359" height="635" alt="Screenshot 2026-03-02 191339" src="https://github.com/user-attachments/assets/40c9c248-e8a5-42b1-af16-a1ab4fd2aa04" />
<img width="1363" height="616" alt="Screenshot 2026-03-02 191359" src="https://github.com/user-attachments/assets/f22a2c47-3f93-4e3d-a3ee-b137bf09c59a" />
<img width="1361" height="633" alt="Screenshot 2026-03-02 191324" src="https://github.com/user-attachments/assets/72b09b49-fec8-4830-93a4-b94a26c8a308" />



# 🎯 System Purpose

The SEO Audit Engine evaluates a client website and determines:

* Whether it ranks for relevant keywords
* Who its competitors are
* Why competitors outrank it
* What changes will improve ranking

Every audit run captures:

* Page snapshots
* Keyword sets (versioned)
* SERP snapshots
* Competitor URLs
* Derived keyword metrics
* Deterministic recommendations
* Optional AI interpretation summary

Nothing is ephemeral.
The database is the system of record.

---

# 🏗 System Architecture

```
Client
   ↓
REST API
   ↓
AuditRun (DB)
   ↓
RunSteps (DB – ordered pipeline)
   ↓
OutboxEvent (guaranteed dispatch)
   ↓
Celery Workers (multi-queue)
   ↓
Evidence Tables
   ↓
Analysis
   ↓
Recommendations
   ↓
Dashboard (Derived Status)
```

---

# 🔁 Core Architectural Patterns

## 1️⃣ Step-Orchestrated Pipeline

Each `AuditRun` contains ordered `RunStep` rows:

```
FETCH_CLIENT
CLASSIFY
KEYWORDS
SERP
COMPETITORS
ANALYZE
FINALIZE
```

Rules:

* Each step is idempotent
* Each step logs attempts
* Each step records start + finish timestamps
* Each step stores structured meta
* Each step can retry independently
* Run status is derived from step states

There is no hidden state.

---

## 2️⃣ Fully Derived Run Status

Run status is not trusted as authoritative state.

Instead, it is derived from step outcomes:

* FINALIZE success → SUCCESS
* Any running step → RUNNING
* Any step failed with max attempts → FAILED
* Otherwise → QUEUED

This ensures:

* No divergence between worker state and dashboard state
* Deterministic system behavior
* Zero reliance on in-memory task state

---

## 3️⃣ Outbox Pattern (Guaranteed Dispatch)

Audit runs do not directly trigger Celery tasks.

Instead:

* An `OutboxEvent` is created in the same DB transaction.
* A dispatcher worker reads PENDING events.
* Events are claimed with row-level locking.
* Tasks are dispatched safely.
* Failures are retried with exponential backoff.
* Max-attempt failures move to DLQ.

This guarantees:

* No lost tasks
* No double dispatch
* Reliable restart behavior

---

## 4️⃣ Reconciler (Self-Healing Supervisor)

A background Celery task:

* Scans incomplete runs
* Uses JOIN-based step inspection
* Determines resume point
* Enqueues outbox event
* Avoids in-flight duplicates

The reconciler ensures:

* Stuck runs recover automatically
* Worker crashes do not corrupt execution
* Partial runs resume safely

---

## 5️⃣ Multi-Queue Scaling

Workers are separated by workload type:

| Queue       | Purpose                     |
| ----------- | --------------------------- |
| `seo_light` | Lightweight tasks           |
| `seo_serp`  | Rate-limited SERP calls     |
| `seo_heavy` | Competitor fetch + analysis |
| `control`   | Outbox + reconciler         |

This enables horizontal scaling and isolation.

---

# 🗄 Database Model Overview

### Core Execution Models

* `AuditRun`
* `RunStep`
* `RunStepAttempt`
* `OutboxEvent`

### Evidence Models

* `PageSnapshot`
* `SerpSnapshot`
* `KeywordSetVersion`
* `KeywordResult`
* `Recommendation`

Snapshots are immutable.
Derived metrics are reproducible.

---

# 📊 Dashboard & Observability

The admin dashboard provides:

* Live run monitor
* Step timeline visualization
* Per-step duration metrics
* Attempt counts
* Error panel
* AI summary view
* System-derived recommendation table

Polling stops automatically on terminal states.

The dashboard reflects derived truth from the database.

---

# 🤖 AI Interpretation Layer

The system supports an optional AI analysis phase:

* Structured payload only (no raw HTML)
* Deterministic evidence first
* AI generates:

  * Summary
  * Strategic recommendations
  * Prioritized actions
* Results persisted in DB

AI augments — it does not replace deterministic logic.

---

# 🚀 Getting Started (Docker Recommended)

## Run Full Stack

```bash
docker compose up --build
```

## Run Tests

```bash
docker compose exec web python manage.py test -v 2
```

---

# 🧪 Test Coverage

Tests validate:

* API endpoints
* Run creation
* Retry behavior
* Outbox dispatch logic
* Backoff handling
* DLQ transitions
* Authentication enforcement

The system is tested against:

* DB state correctness
* Dispatch failure handling
* Idempotent behavior

---

# 📡 API Endpoints

### Sites

```
POST   /api/sites
GET    /api/sites
GET    /api/sites/{id}
```

### Runs

```
POST   /api/sites/{id}/runs
GET    /api/runs/{id}
GET    /api/runs/{id}/dashboard
POST   /api/runs/{id}/retry
```

### System

```
GET    /api/health
GET    /api/dashboard/overview
```

---

# 🔁 Audit Lifecycle

1. Create site
2. Create audit run
3. Initialize step rows
4. Outbox event created
5. Dispatcher sends run_start
6. Step chain executes in order
7. Evidence captured per step
8. Derived metrics computed
9. Optional AI interpretation
10. Finalize

Each transition is recorded.

---

# 📐 Design Principles

* DB is truth
* Deterministic before AI
* No silent failures
* Retryable units
* Idempotent steps
* Observable execution
* Explicit state transitions
* Evidence-linked recommendations

---

# 📈 Scaling Characteristics

The architecture supports:

* SERP fan-out parallelism
* Multi-tenant audits
* Queue isolation
* Horizontal worker scaling
* Automatic recovery via reconciler
* Dead-letter queue inspection
* AI workload isolation

---

# 🏁 System Status

Production-grade orchestration complete.

* Step-driven execution ✔
* Outbox pattern implemented ✔
* Reconciler supervisor active ✔
* Derived status logic ✔
* AI analysis integration ✔
* Dashboard monitoring ✔
* Test suite passing ✔

---

Built for reliability.
Built for determinism.
Built for scale.
