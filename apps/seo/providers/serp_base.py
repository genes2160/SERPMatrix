from urllib.parse import urlparse
import requests
import logging

logger = logging.getLogger(__name__)


def extract_domain(url: str) -> str:
    return urlparse(url).netloc.replace("www.", "")


def fetch_page(url: str) -> requests.Response | None:
    # normalise: if no scheme, add https://
    if not url.startswith("http"):
        url = f"https://{url}"

    logger.info("🌐 [fetch_page] Fetching | url=%s", url)

    try:
        response = requests.get(
            url,
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0"},
            allow_redirects=True,
        )

        logger.info(
            "✅ [fetch_page] Response received | url=%s | status=%s | content_type=%s | size=%s bytes",
            url,
            response.status_code,
            response.headers.get("Content-Type", "unknown"),
            len(response.content),
        )

        response.raise_for_status()
        return response

    except requests.exceptions.Timeout:
        logger.error("⏱️ [fetch_page] Timeout | url=%s", url)
        return None

    except requests.exceptions.TooManyRedirects:
        logger.error("🔁 [fetch_page] Too many redirects | url=%s", url)
        return None

    except requests.exceptions.SSLError as e:
        logger.error("🔒 [fetch_page] SSL error | url=%s | error=%s", url, str(e))
        return None

    except requests.exceptions.ConnectionError as e:
        logger.error("🔌 [fetch_page] Connection error | url=%s | error=%s", url, str(e))
        return None

    except requests.exceptions.HTTPError as e:
        logger.error(
            "❌ [fetch_page] HTTP error | url=%s | status=%s | error=%s",
            url, response.status_code, str(e),
        )
        return None

    except Exception as e:
        logger.exception("💥 [fetch_page] Unexpected error | url=%s | error=%s", url, str(e))
        return None