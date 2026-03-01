from urllib.parse import urlparse
from apps.seo.models import ClientSite


def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    scheme = parsed.scheme or "https"
    netloc = parsed.netloc or parsed.path
    return f"{scheme}://{netloc}".rstrip("/")


def create_site(*, url: str, geo: str, language: str, device: str) -> ClientSite:
    normalized = normalize_url(url)

    site, _ = ClientSite.objects.get_or_create(
        normalized_url=normalized,
        defaults={
            "url": url,
            "geo": geo,
            "language": language,
            "device": device,
        },
    )

    return site