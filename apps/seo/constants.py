# apps/seo/constants.py

from typing import List

from apps.seo.models import RunStep

RUN_STEP_ORDER: List[str] = [
    RunStep.StepName.FETCH_CLIENT,
    RunStep.StepName.CLASSIFY,
    RunStep.StepName.KEYWORDS,
    RunStep.StepName.SERP,
    RunStep.StepName.COMPETITORS,
    RunStep.StepName.ANALYZE,
    RunStep.StepName.FINALIZE,
]