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
        # Explicitly tie to the owner of the client site
        user = getattr(run.client_site, "user", None)
        if user is None:
            logger.warning(
                "⚠️ [NOTIFY] Skipped — run.client_site.user is None | run_id=%s",
                getattr(run, "id", None),
            )
            return

        Notification.objects.create(
            audit_run  = run,
            user       = user,       # ✅ guaranteed correct user
            event_type = event_type,
            channel    = channel,
            title      = title,
            body       = body,
            meta       = meta or {},
        )
        logger.info(
            "🔔 Notification created | run_id=%s | user=%s | event=%s | title=%s",
            run.id, user.id, event_type, title,
        )
    except Exception as e:
        logger.exception(
            "❌ Notification write failed | run_id=%s | error=%s", run.id, str(e)
        )