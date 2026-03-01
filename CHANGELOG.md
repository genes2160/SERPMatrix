# Changelog

All notable changes to this project will be documented in this file.

This project follows **Semantic Versioning (SemVer)**:
MAJOR.MINOR.PATCH

- MAJOR: Breaking architectural or API changes
- MINOR: New features (backward compatible)
- PATCH: Bug fixes, performance improvements, non-breaking changes

---

# [0.1.0] - Architecture Foundation

## Added
- Django project scaffold
- SEO application modular structure
- Celery multi-queue setup (`seo_light`, `seo_serp`, `seo_heavy`)
- PostgreSQL integration
- Redis integration
- Flower observability support
- Environment-driven Docker Compose configuration
- .env-based configuration management
- UUID-based primary keys for all models
- Evidence-first database schema

## Database Models Introduced
- `ClientSite`
- `AuditRun`
- `RunStep`
- `RunStepAttempt`
- `PageSnapshot`
- `KeywordSetVersion`
- `SerpSnapshot`
- `KeywordResult`
- `Recommendation`

## Architectural Decisions
- Database is the single source of truth
- Every step is idempotent via unique constraints
- Snapshots are immutable
- Derived data reproducible from evidence
- Celery reliability enabled:
  - `acks_late=True`
  - `task_reject_on_worker_lost=True`
  - `worker_prefetch_multiplier=1`
- Environment-driven service configuration (no hardcoded ports)

---

# Roadmap

---

# [0.2.0] - Fetch + Extraction Engine

## Planned
- Implement `FETCH_CLIENT` step
- HTTP fetch service
- HTML hashing
- Content extraction:
  - Title
  - Meta description
  - H1 / H2
  - Word count
  - Basic schema detection
- Save `PageSnapshot`
- Basic keyword extraction logic
- Create `KeywordSetVersion`
- Health endpoint exposing system version

## Goals
- Establish deterministic site intelligence
- Validate evidence storage integrity
- Test idempotent step execution

---

# [0.3.0] - SERP Capture Integration

## Planned
- SERP provider abstraction layer
- Integration with external SERP API
- Implement `SERP` step
- Store `SerpSnapshot`
- Compute `KeywordResult`
- Basic visibility scoring algorithm
- Rate limiting strategy for SERP queue

## Goals
- Establish ranking truth
- Validate external API resilience
- Track keyword-level ranking data

---

# [0.4.0] - Competitor Intelligence

## Planned
- Implement `COMPETITORS` step
- Fetch top competitor pages
- Store competitor `PageSnapshot`
- Extract competitor signals
- Compute difficulty proxy score
- Extend `KeywordResult` insights

## Goals
- Compare client vs competitor signals
- Build explainable ranking gaps
- Enrich evidence graph

---

# [0.5.0] - Deterministic Analysis Engine

## Planned
- Implement `ANALYZE` step
- Gap detection:
  - Missing keyword in title
  - Weak H1 structure
  - Content depth mismatch
- Generate structured `Recommendation`
- Evidence-linked reasoning references
- Compute run summary metrics

## Goals
- Justify why rankings exist
- Produce explainable, reproducible recommendations
- Avoid AI hallucination by anchoring evidence

---

# [0.6.0] - Ranking Trends & Historical Tracking

## Planned
- Compare runs (delta tracking)
- Store historical ranking changes
- Visibility score progression
- Improvement detection metrics
- Add ranking history API endpoint

## Goals
- Learn from ranking movement
- Establish measurable improvement tracking
- Prepare dataset for future AI layer

---

# [0.7.0] - Observability Hardening

## Planned
- Structured JSON logging
- Worker attempt trace logging
- Step-level execution timing metrics
- Failure analytics summary
- Enhanced Flower integration guidance
- Admin dashboard for run introspection

## Goals
- Operate like production system
- Improve failure diagnostics
- Validate distributed reliability

---

# [0.8.0] - AI Interpretation Layer

## Planned
- AI summary generation based on evidence
- Keyword clustering by intent
- Improvement prioritization scoring
- Natural language explanations for reports
- Guardrail-based prompt discipline

## Goals
- Convert deterministic metrics into strategy
- Maintain explainability
- Avoid opaque reasoning

---

# [1.0.0] - Stable Release

## Planned
- Parallel SERP fan-out per keyword
- Horizontal scaling validation
- Optimized DB indexes after load testing
- Production-ready Docker image
- Admin monitoring dashboard
- API versioning strategy
- Hardened rate limiting
- Security audit pass

## Goals
- Scalable production deployment
- Stable public API
- High-confidence reliability

---

# Versioning Discipline

Every release must:

1. Update `APP_VERSION` in settings
2. Update this CHANGELOG
3. Commit changes
4. Tag release (`git tag vX.Y.Z`)
5. Push tag to repository

No silent architectural changes.
No undocumented migrations.
No hidden feature toggles.

---

# Design Principles (Non-Negotiable)

- Database > Worker Memory
- Snapshots are immutable
- All recommendations link to evidence
- Every step is retryable
- No silent failures
- No hidden state transitions
- Deterministic logic before AI