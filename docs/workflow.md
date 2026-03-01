# Execution Workflow

1. User logs in → obtains JWT
2. User creates ClientSite
3. User triggers AuditRun
4. System creates RunSteps
5. Celery task run_start triggered
6. Each step executes in sequence
7. Step updates DB status
8. Failures recorded
9. Analysis step computes metrics
10. Finalize step builds summary + recommendations
11. AuditRun marked SUCCESS
12. User retrieves run report

---

## Error Flow

- Step failure → RunStepAttempt created
- Status marked FAILED
- Error stored
- Retry available via API

---

## Data Flow

ClientSite → AuditRun → RunStep → PageSnapshot → KeywordSetVersion → SerpSnapshot → KeywordResult → Recommendation