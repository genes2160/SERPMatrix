# Technical Specification

## Stack

Backend:
- Django 5
- DRF
- SimpleJWT
- PostgreSQL
- Redis
- Celery
- Flower

---

## Deployment Model

Containers:
- web
- redis
- db
- worker_light
- worker_serp
- worker_heavy
- flower

---

## Database Design Principles

- UUID primary keys
- Indexed status fields
- Unique constraints for run steps
- Unique constraint per keyword per run
- JSON fields for flexible storage
- Audit-first model design

---

## Celery Reliability

- CELERY_TASK_ACKS_LATE = True
- CELERY_TASK_REJECT_ON_WORKER_LOST = True
- PREFETCH_MULTIPLIER = 1
- Soft + hard time limits
- Explicit task routing

---

## Security

- JWT authentication
- Token rotation
- Token blacklist
- IsAuthenticated default
- Health endpoint public

---

## Observability

- RunStep tracking
- RunStepAttempt tracking
- Error summaries
- Flower monitoring
- Structured summary JSON per run

---

## Future Enhancements

- AI recommendation engine
- Rank delta tracking
- Time-series ranking history
- SERP provider abstraction
- Multi-tenant isolation
- API versioning
- Caching layer