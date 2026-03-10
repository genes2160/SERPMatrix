# apps/seo/notifications.py

import logging
from apps.seo.models import Notification

logger = logging.getLogger(__name__)

def notify(
    run,
    event_type: str,
    title: str,
    body: str,
    meta: dict = None,
    channel: str = Notification.Channel.IN_APP,
):
    if run is None:
        logger.warning(
            "⚠️ [NOTIFY] Skipped — run is None | event_type=%s | title=%s",
            event_type, title,
        )
        return

    try:
        user = getattr(run, "user", None)  # ← resolved from run, no call site concern

        Notification.objects.create(
            audit_run  = run,
            user       = user,
            event_type = event_type,
            channel    = channel,
            title      = title,
            body       = body,
            meta       = meta or {},
        )
        logger.info(
            "🔔 Notification created | run_id=%s | user=%s | event=%s | title=%s",
            run.id, getattr(user, "id", None), event_type, title,
        )
    except Exception as e:
        logger.exception("❌ Notification write failed | run_id=%s | error=%s", run.id, str(e))