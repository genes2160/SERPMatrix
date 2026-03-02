# apps/seo/providers/serp/brave.py

import requests

class BraveSerpProvider:
    def __init__(self, api_key):
        self.api_key = api_key

    def search(self, keyword, geo="GH", device="desktop"):
        url = "https://api.search.brave.com/res/v1/web/search"

        headers = {
            "X-Subscription-Token": self.api_key
        }

        params = {
            "q": keyword,
            "count": 10
        }

        res = requests.get(url, headers=headers, params=params)
        data = res.json()

        results = []
        for r in data.get("web", {}).get("results", []):
            results.append({
                "title": r.get("title"),
                "link": r.get("url"),
                "snippet": r.get("description"),
            })

        return results