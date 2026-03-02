CLIENT → CREATE SITE
        │
        ▼
POST /sites
    → ClientSite created
        │
        ▼
POST /sites/{id}/runs
    → run_service.create_run()
    → AuditRun(status=QUEUED)
    → RunStep rows pre-created (per RUN_STEP_ORDER)
    → OutboxEvent(event_type="audit_run_start", PENDING)
        │
        ▼
Outbox Dispatcher (control queue)
    → claims OutboxEvent
    → run_start.delay(run_id, resume_from)
    → mark event SENT
        │
        ▼
run_start (pipeline entry)
    → if not SUCCESS/CANCELED:
        set AuditRun.status=RUNNING
    → build Celery chain from resume_from
        FETCH_CLIENT
        → CLASSIFY
        → KEYWORDS
        → SERP
        → COMPETITORS
        → ANALYZE
        → FINALIZE
        │
        ▼
Each Step Task:
    _claim_step()
        → lock RunStep
        → increment attempts
        → create RunStepAttempt
        → mark RUNNING

    ├─ on success:
    │      _finish_success()
    │      → step SUCCESS
    │      → attempt SUCCESS
    │
    └─ on failure:
           _finish_failed()
           → step FAILED
           → attempt FAILED
           → retry (if attempts < max)

        │
        ▼
STEP LOGIC SUMMARY

FETCH_CLIENT
    → create client PageSnapshot (stub)

CLASSIFY
    → set niche_label

KEYWORDS
    → extract from client snapshot
    → create KeywordSetVersion(EXTRACTED)

SERP
    → provider search (config-driven)
    → create SerpSnapshot
    → create KeywordResult

COMPETITORS
    → fetch competitor pages
    → create/update competitor PageSnapshot

ANALYZE
    → compare word counts
    → inspect keyword rankings
    → create Recommendation rows

FINALIZE
    → compute run.summary
    → set AuditRun.status=SUCCESS
    → set finished_at

        │
        ▼
OPTIONAL: AI_ANALYZE (heavy queue)
    → build structured payload
    → LLM generate summary + recs
    → write ai_summary + ai_meta
    → optionally persist Recommendation rows

        │
        ▼
Dashboard

GET /runs/{id}/dashboard
    → load run
    → load steps
    → derive status via _derive_run_status_from_steps()
    → return:
        run (derived status, derived finished_at)
        steps
        ai block
        system block

        │
        ▼
Reconciler (background supervisor)

reconcile_runs:
    → find QUEUED/RUNNING runs
    → determine next incomplete step
    → if exhausted attempts → mark FAILED
    → else enqueue OutboxEvent(resume_from)

        │
        ▼
System guarantees

- Step-level idempotency via row locks
- Attempt tracking via RunStepAttempt
- Run-level derived status (not always DB-truth)
- Outbox for reliable pipeline restart
- Reconciler for stuck runs