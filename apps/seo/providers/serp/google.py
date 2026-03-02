import requests


class GoogleSerpProvider:
    BASE_URL = "https://serpapi.com/search"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def search(self, keyword: str, geo: str = "gh", device: str = "desktop"):
        params = {
            "q": keyword,
            "engine": "google",
            "google_domain": "google.com",
            "hl": "en",
            "gl": geo,
            "api_key": self.api_key,
        }

        response = requests.get(self.BASE_URL, params=params, timeout=10)
        response.raise_for_status()

        data = response.json()

        organic = data.get("organic_results", [])
        return organic