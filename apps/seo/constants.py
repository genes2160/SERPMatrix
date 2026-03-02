# apps/seo/constants.py

from typing import List, Optional, Tuple

from apps.seo.models import AuditRun, RunStep

RUN_STEP_ORDER: List[str] = [
    RunStep.StepName.FETCH_CLIENT,
    RunStep.StepName.CLASSIFY,
    RunStep.StepName.KEYWORDS,
    RunStep.StepName.SERP,
    RunStep.StepName.COMPETITORS,
    RunStep.StepName.ANALYZE,
    # RunStep.StepName.AI_ANALYZE,
    RunStep.StepName.FINALIZE,
]

# NEW: keep retries aligned everywhere
STEP_MAX_ATTEMPTS = 3  # NEW: single source of truth

# NEW: for ordering checks
STEP_INDEX = {name: i for i, name in enumerate(RUN_STEP_ORDER)}  # NEW


def previous_steps(step_name: str) -> List[str]:  # NEW
    idx = STEP_INDEX.get(step_name, 0)
    return RUN_STEP_ORDER[:idx]


def next_resume_step_from_db(run: AuditRun) -> Tuple[Optional[str], Optional[str]]:  # NEW
    """
    Returns (resume_from_step_name or None, terminal_error or None)

    - If everything done => (None, None)
    - If a step failed and attempts >= STEP_MAX_ATTEMPTS => (None, "terminal...")
    - Else => (earliest incomplete step_name, None)
    """
    steps = {s.step_name: s for s in run.steps.all()}

    for step_name in RUN_STEP_ORDER:
        s = steps.get(step_name)

        if s is None:
            return (step_name, None)

        if s.status in [RunStep.Status.SUCCESS, RunStep.Status.SKIPPED]:
            continue

        if s.status in [RunStep.Status.QUEUED, RunStep.Status.RUNNING]:
            return (step_name, None)

        if s.status == RunStep.Status.FAILED:
            if (s.attempts or 0) >= STEP_MAX_ATTEMPTS:
                return (None, f"Step {step_name} exceeded max attempts ({s.attempts})")
            return (step_name, None)

    return (None, None)


def _derive_run_status_from_steps(steps):
    """
    steps: iterable of dicts or model objects that include:
      - step_name
      - status
      - attempts
    """
    def get(x, k, default=None):
        return x.get(k, default) if isinstance(x, dict) else getattr(x, k, default)

    # 1) finalize success wins
    for s in steps:
        if get(s, "step_name") == RunStep.StepName.FINALIZE and get(s, "status") == RunStep.Status.SUCCESS:
            return AuditRun.Status.SUCCESS

    # 2) any running -> running
    for s in steps:
        if get(s, "status") == RunStep.Status.RUNNING:
            return AuditRun.Status.RUNNING

    # 3) any failed + exhausted attempts -> failed
    for s in steps:
        if get(s, "status") == RunStep.Status.FAILED and (get(s, "attempts") or 0) >= STEP_MAX_ATTEMPTS:
            return AuditRun.Status.FAILED

    # 4) otherwise queued
    return AuditRun.Status.QUEUED