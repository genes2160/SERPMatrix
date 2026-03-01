from apps.seo.models import AuditRun, RunStep


DEFAULT_STEPS = [
    RunStep.StepName.FETCH_CLIENT,
    RunStep.StepName.CLASSIFY,
    RunStep.StepName.KEYWORDS,
    RunStep.StepName.SERP,
    RunStep.StepName.COMPETITORS,
    RunStep.StepName.ANALYZE,
    RunStep.StepName.FINALIZE,
]


def create_run(*, site, config: dict) -> AuditRun:
    run = AuditRun.objects.create(
        client_site=site,
        config=config or {},
        status=AuditRun.Status.QUEUED,
    )

    RunStep.objects.bulk_create([
        RunStep(audit_run=run, step_name=step)
        for step in DEFAULT_STEPS
    ])

    return run


def retry_run(*, run: AuditRun) -> AuditRun:
    run.status = AuditRun.Status.QUEUED
    run.started_at = None
    run.finished_at = None
    run.error_summary = None
    run.save(update_fields=["status", "started_at", "finished_at", "error_summary"])

    run.steps.update(
        status=RunStep.Status.QUEUED,
        attempts=0,
        last_error=None,
    )

    return run