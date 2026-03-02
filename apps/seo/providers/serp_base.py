from urllib.parse import urlparse
import requests


def extract_domain(url: str) -> str:
    return urlparse(url).netloc.replace("www.", "")


def fetch_page(domain: str) -> str:
    try:
        response = requests.get(
            f"https://{domain}",
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        response.raise_for_status()
        return response
    except Exception as err:
        return None