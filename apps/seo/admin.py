from django.contrib import admin
from apps.seo.models import (
    ClientSite,
    AuditRun,
    Notification,
    RunStep,
    RunStepAttempt,
    PageSnapshot,
    KeywordSetVersion,
    SerpSnapshot,
    KeywordResult,
    Recommendation,
    OutboxEvent,
    LLMBatch,
    LLMRun,
)

admin.site.register(ClientSite)
admin.site.register(AuditRun)
admin.site.register(RunStep)
admin.site.register(RunStepAttempt)
admin.site.register(PageSnapshot)
admin.site.register(KeywordSetVersion)
admin.site.register(SerpSnapshot)
admin.site.register(KeywordResult)
admin.site.register(Recommendation)
admin.site.register(OutboxEvent)
admin.site.register(Notification)

@admin.register(LLMBatch)
class LLMBatchAdmin(admin.ModelAdmin):
    list_display  = ["created_at", "audit_run", "provider", "model"]
    list_filter   = ["provider", "model"]
    readonly_fields = [f.name for f in LLMBatch._meta.fields]

@admin.register(LLMRun)
class LLMRunAdmin(admin.ModelAdmin):
    list_display  = ["created_at", "audit_run", "provider", "model", "status", "parse_status", "recs_parsed", "latency_seconds"]
    list_filter   = ["status", "provider", "parse_status"]
    readonly_fields = [f.name for f in LLMRun._meta.fields]