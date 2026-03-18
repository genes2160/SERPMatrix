# apps/seo/models.py
import json
import uuid
from django.db import models
from django.contrib.auth.models import User
from django.db.models import Q

class ClientSite(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    url = models.URLField()
    normalized_url = models.URLField()

    geo = models.CharField(max_length=32, default="GH")
    language = models.CharField(max_length=16, default="en")
    device = models.CharField(max_length=16, default="desktop")

    niche_label = models.CharField(max_length=128, null=True, blank=True)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="sites",
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "normalized_url"],
                name="uniq_user_normalized_url"
            ),
            models.UniqueConstraint(
                fields=["user", "url"],
                name="uniq_user_url"
            ),
        ]

class AuditRun(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued"
        RUNNING = "running"
        SUCCESS = "success"
        FAILED = "failed"
        CANCELED = "canceled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client_site = models.ForeignKey(ClientSite, on_delete=models.CASCADE, related_name="runs")

    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED)

    last_reconciled_at = models.DateTimeField(null=True, blank=True)  # ← ADD THIS
    # provider + limits + geo + device + language
    config = models.JSONField(default=dict)

    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    # run-wide computed metrics
    summary = models.JSONField(default=dict, blank=True)
    ai_summary = models.TextField(null=True, blank=True)
    ai_meta = models.JSONField(null=True, blank=True)

    error_summary = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["client_site", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
        ]
        
    def save(self, *args, **kwargs):
        if self.config is None:
            self.config = {}
        elif not isinstance(self.config, dict):
            try:
                parsed = json.loads(self.config)
                self.config = parsed if isinstance(parsed, dict) else {}
            except Exception:
                self.config = {}
        super().save(*args, **kwargs)

class RunStep(models.Model):
    class StepName(models.TextChoices):
        FETCH_CLIENT = "FETCH_CLIENT"
        CLASSIFY = "CLASSIFY"
        KEYWORDS = "KEYWORDS"
        SERP = "SERP"
        COMPETITORS = "COMPETITORS"
        ANALYZE = "ANALYZE"
        # NEW:
        # AI_ANALYZE = "AI_ANALYZE"
        FINALIZE = "FINALIZE"

    class Status(models.TextChoices):
        QUEUED = "queued"
        RUNNING = "running"
        SUCCESS = "success"
        FAILED = "failed"
        SKIPPED = "skipped"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    audit_run = models.ForeignKey(AuditRun, on_delete=models.CASCADE, related_name="steps")
    step_name = models.CharField(max_length=32, choices=StepName.choices)

    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED)

    attempts = models.PositiveIntegerField(default=0)

    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    last_error = models.TextField(null=True, blank=True)
    meta = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["audit_run", "step_name"], name="uniq_run_step"),
        ]
        indexes = [
            models.Index(fields=["audit_run", "step_name"]),
            models.Index(fields=["status"]),
        ]


class RunStepAttempt(models.Model):
    class Status(models.TextChoices):
        RUNNING = "running"
        SUCCESS = "success"
        FAILED = "failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run_step = models.ForeignKey(RunStep, on_delete=models.CASCADE, related_name="attempt_records")

    attempt_no = models.PositiveIntegerField()

    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RUNNING)

    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    error = models.TextField(null=True, blank=True)

    worker_hostname = models.CharField(max_length=255, null=True, blank=True)
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["run_step", "attempt_no"], name="uniq_step_attempt_no"),
        ]
        indexes = [
            models.Index(fields=["run_step", "-attempt_no"]),
        ]


class PageSnapshot(models.Model):
    class Role(models.TextChoices):
        CLIENT = "client"
        COMPETITOR = "competitor"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    audit_run = models.ForeignKey(AuditRun, on_delete=models.CASCADE, related_name="page_snapshots")

    url = models.URLField()
    role = models.CharField(max_length=16, choices=Role.choices)

    http_status = models.IntegerField(null=True, blank=True)
    fetched_at = models.DateTimeField(auto_now_add=True)

    html_hash = models.CharField(max_length=64)  # sha256 hex
    content_type = models.CharField(max_length=128, null=True, blank=True)

    extracted = models.JSONField(default=dict, blank=True)
    raw_html_ref = models.CharField(max_length=512, null=True, blank=True)  # future: s3 key

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["audit_run", "url", "role"],
                name="uniq_run_url_role"
            )
        ]
        indexes = [
            models.Index(fields=["audit_run", "role"]),
            models.Index(fields=["url"]),
            models.Index(fields=["html_hash"]),
        ]


class KeywordSetVersion(models.Model):
    class Source(models.TextChoices):
        USER = "user"
        EXTRACTED = "extracted"
        AI = "ai"
        HYBRID = "hybrid"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    audit_run = models.ForeignKey(AuditRun, on_delete=models.CASCADE, related_name="keyword_sets")

    source = models.CharField(max_length=16, choices=Source.choices, default=Source.EXTRACTED)
    keywords = models.JSONField(default=list)  # ordered list: [{"kw": "...", "w": 1.0}, ...]

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["audit_run", "-created_at"]),
        ]


class SerpSnapshot(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    audit_run = models.ForeignKey(AuditRun, on_delete=models.CASCADE, related_name="serp_snapshots")

    keyword = models.CharField(max_length=255)
    provider = models.CharField(max_length=64)

    provider_meta = models.JSONField(default=dict, blank=True)
    results = models.JSONField(default=dict)  # raw-ish normalized structure

    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["audit_run"]),
            models.Index(fields=["keyword"]),
            models.Index(fields=["-fetched_at"]),
        ]


class KeywordResult(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    audit_run = models.ForeignKey(AuditRun, on_delete=models.CASCADE, related_name="keyword_results")

    keyword = models.CharField(max_length=255)
    client_position = models.IntegerField(null=True, blank=True)  # null = not found

    visibility_score = models.FloatField(default=0.0)
    difficulty_score = models.FloatField(default=0.0)

    competitor_urls = models.JSONField(default=list)  # top K urls
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["audit_run", "keyword"], name="uniq_run_keyword"),
        ]
        indexes = [
            models.Index(fields=["audit_run"]),
            models.Index(fields=["client_position"]),
        ]


class Recommendation(models.Model):
    class Priority(models.TextChoices):
        LOW = "low"
        MED = "med"
        HIGH = "high"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    audit_run = models.ForeignKey(AuditRun, on_delete=models.CASCADE, related_name="recommendations")

    keyword = models.CharField(max_length=255, null=True, blank=True)

    action_type = models.CharField(max_length=64)  # title_fix, content_expand, etc.
    priority = models.CharField(max_length=8, choices=Priority.choices, default=Priority.MED)

    reason_text = models.TextField()
    evidence_refs = models.JSONField(default=list)  # [{"type":"serp_snapshot","id":"..."}, ...]

    expected_impact = models.CharField(max_length=8, choices=Priority.choices, default=Priority.MED)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["audit_run", "priority"]),
            models.Index(fields=["action_type"]),
        ]
        

class OutboxEvent(models.Model):

    class Status(models.TextChoices):
        PENDING = "PENDING"
        PROCESSING = "PROCESSING"
        SENT = "SENT"
        FAILED = "FAILED"
        DLQ = "DLQ"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    event_type = models.CharField(max_length=100, db_index=True)
    aggregate_id = models.UUIDField(db_index=True)  # run_id
    payload = models.JSONField()

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )

    attempts = models.IntegerField(default=0)
    max_attempts = models.IntegerField(default=5)

    next_retry_at = models.DateTimeField(null=True, blank=True, db_index=True)

    last_error = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "next_retry_at"]),
        ]
        
class LLMBatch(models.Model):
    """One row per prompt sent to the LLM."""
    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    audit_run  = models.ForeignKey("AuditRun", on_delete=models.CASCADE, related_name="llm_batches", null=True, blank=True)
    provider   = models.CharField(max_length=64)
    model      = models.CharField(max_length=128, blank=True, default="")
    prompt     = models.TextField()                          # full prompt stored here
    system     = models.TextField(blank=True, default="")   # system prompt
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["audit_run", "provider"]),
            models.Index(fields=["created_at"]),
        ]


class LLMRun(models.Model):
    """One row per LLM call result — success or failure."""

    class Status(models.TextChoices):
        SUCCESS = "success", "Success"
        FAILED  = "failed",  "Failed"

    class ParseStatus(models.TextChoices):
        OK      = "ok",      "OK"
        FAILED  = "failed",  "Failed"
        SKIPPED = "skipped", "Skipped"

    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    audit_run  = models.ForeignKey("AuditRun", on_delete=models.CASCADE, related_name="llm_runs", null=True, blank=True)
    batch      = models.ForeignKey("LLMBatch", on_delete=models.SET_NULL, related_name="runs", null=True, blank=True)

    provider   = models.CharField(max_length=64)
    model      = models.CharField(max_length=128, blank=True, default="")
    status     = models.CharField(max_length=16, choices=Status.choices, default=Status.FAILED)

    # response
    response        = models.JSONField(null=True, blank=True)   # full parsed JSON or error dict
    response_raw    = models.TextField(blank=True, default="")  # raw text from LLM

    # observability
    prompt_tokens      = models.IntegerField(null=True, blank=True)
    completion_tokens  = models.IntegerField(null=True, blank=True)
    total_tokens       = models.IntegerField(null=True, blank=True)
    latency_seconds    = models.FloatField(null=True, blank=True)

    # parse
    parse_status  = models.CharField(max_length=16, choices=ParseStatus.choices, null=True, blank=True)
    parse_error   = models.TextField(blank=True, default="")
    recs_parsed   = models.IntegerField(null=True, blank=True)

    # failure
    error             = models.TextField(blank=True, default="")
    traceback_snippet = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["audit_run", "provider"]),
            models.Index(fields=["batch"]),
            models.Index(fields=["status"]),
            models.Index(fields=["created_at"]),
        ]


class Notification(models.Model):

    class EventType(models.TextChoices):
        RUN_STARTED      = "run_started"
        STEP_SUCCESS     = "step_success"
        STEP_FAILED      = "step_failed"
        RUN_COMPLETE     = "run_complete"
        RUN_FAILED       = "run_failed"

    class Channel(models.TextChoices):
        IN_APP = "in_app"
        EMAIL  = "email"   # future
        PUSH   = "push"    # future (FCM)

    id        = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user      = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications", null=True, blank=True)
    audit_run = models.ForeignKey(AuditRun, on_delete=models.CASCADE, related_name="notifications")

    event_type = models.CharField(max_length=32, choices=EventType.choices)
    channel    = models.CharField(max_length=16, choices=Channel.choices, default=Channel.IN_APP)

    title = models.CharField(max_length=255)
    body  = models.TextField()
    meta  = models.JSONField(default=dict, blank=True)  # step name, counts, errors etc

    read       = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["audit_run", "-created_at"]),
            models.Index(fields=["user", "read"]),
        ]

