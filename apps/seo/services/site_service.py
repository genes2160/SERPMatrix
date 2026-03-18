from urllib.parse import urlparse
from apps.seo.models import ClientSite


def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    scheme = parsed.scheme or "https"
    netloc = parsed.netloc or parsed.path
    return f"{scheme}://{netloc}".rstrip("/")


def create_site(*, url: str, geo: str, language: str, device: str, user) -> ClientSite:
    normalized = normalize_url(url)

    site, created = ClientSite.objects.get_or_create(
        user=user,  # scope per user
        normalized_url=normalized,
        defaults={
            "url": url,
            "geo": geo,
            "language": language,
            "device": device,
            "user": user,
        },
    )
    if created:
        from apps.seo.services.run_service import run_service
        run_service.create_run(site=site, config={})

    return site