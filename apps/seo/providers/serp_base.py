from urllib.parse import urlparse
import requests
import logging
import random

logger = logging.getLogger(__name__)

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
]

_BASE_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}


def extract_domain(url: str) -> str:
    return urlparse(url).netloc.replace("www.", "")


def _fetch_with_playwright(url: str) -> requests.Response | None:
    """Fallback for Cloudflare-protected or JS-gated pages."""
    try:
        from playwright.sync_api import sync_playwright
        import urllib3

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=random.choice(_USER_AGENTS),
                locale="en-US",
                viewport={"width": 1280, "height": 800},
            )
            page = context.new_page()

            response = page.goto(url, wait_until="domcontentloaded", timeout=20000)
            html = page.content()
            status = response.status if response else 200

            browser.close()

        # Wrap in a requests.Response-like object so the rest of the pipeline
        # doesn't need to know a browser was involved
        mock = requests.Response()
        mock.status_code = status
        mock._content = html.encode("utf-8")
        mock.headers["Content-Type"] = "text/html; charset=utf-8"
        mock.encoding = "utf-8"
        return mock

    except Exception as e:
        logger.error("💥 [fetch_page] Playwright fallback failed | url=%s | error=%s", url, str(e))
        return None


def fetch_page(url: str, timeout: int = 15, retries: int = 2) -> requests.Response | None:
    if not url.startswith("http"):
        url = f"https://{url}"

    headers = {**_BASE_HEADERS, "User-Agent": random.choice(_USER_AGENTS)}

    logger.info("🌐 [fetch_page] Fetching | url=%s", url)

    last_error = None

    for attempt in range(1, retries + 1):
        try:
            session = requests.Session()
            session.max_redirects = 5

            response = session.get(
                url,
                timeout=timeout,
                headers=headers,
                allow_redirects=True,
            )

            logger.info(
                "✅ [fetch_page] Response | url=%s | status=%s | size=%s bytes | attempt=%s",
                url, response.status_code, len(response.content), attempt,
            )

            if response.status_code in (403, 429):
                logger.warning(
                    "🚫 [fetch_page] Blocked by WAF | url=%s | status=%s — trying Playwright",
                    url, response.status_code,
                )
                return _fetch_with_playwright(url)

            response.raise_for_status()
            return response

        except requests.exceptions.Timeout:
            last_error = "timeout"
            logger.warning("⏱️ [fetch_page] Timeout | url=%s | attempt=%s", url, attempt)

        except requests.exceptions.TooManyRedirects:
            logger.error("🔁 [fetch_page] Too many redirects | url=%s", url)
            return None

        except requests.exceptions.SSLError as e:
            logger.error("🔒 [fetch_page] SSL error | url=%s | error=%s", url, str(e))
            return None

        except requests.exceptions.ConnectionError as e:
            last_error = str(e)
            logger.warning("🔌 [fetch_page] Connection error | url=%s | attempt=%s | error=%s", url, attempt, str(e))

        except requests.exceptions.HTTPError as e:
            logger.error("❌ [fetch_page] HTTP error | url=%s | status=%s", url, response.status_code)
            return None

        except Exception as e:
            logger.exception("💥 [fetch_page] Unexpected error | url=%s | error=%s", url, str(e))
            return None

        headers = {**_BASE_HEADERS, "User-Agent": random.choice(_USER_AGENTS)}

    logger.error("⛔ [fetch_page] All %s attempts failed | url=%s | last_error=%s", retries, url, last_error)
    return None


if __name__ == "__main__":
    p = fetch_page("https://www.jumia.com.gh")
    print("...p", p.text[:500] if p is not None else "None")