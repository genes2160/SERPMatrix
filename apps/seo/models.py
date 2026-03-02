# apps/seo/models.py
import json
import uuid
from django.db import models
from django.db.models import Q

class ClientSite(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    url = models.URLField(unique=True)
    normalized_url = models.URLField(unique=True)

    geo = models.CharField(max_length=32, default="GH")
    language = models.CharField(max_length=16, default="en")
    device = models.CharField(max_length=16, default="desktop")  # desktop|mobile

    niche_label = models.CharField(max_length=128, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


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