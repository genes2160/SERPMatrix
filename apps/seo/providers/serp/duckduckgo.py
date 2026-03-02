# apps/seo/providers/serp/duckduckgo.py

from duckduckgo_search import DDGS

class DuckDuckGoSerpProvider:
    def search(self, keyword, geo="GH", device="desktop"):
        with DDGS() as ddgs:
            results = ddgs.text(keyword, region=geo.lower(), max_results=10)

            formatted = []
            for r in results:
                formatted.append({
                    "title": r.get("title"),
                    "link": r.get("href"),
                    "snippet": r.get("body"),
                })

            return formatted