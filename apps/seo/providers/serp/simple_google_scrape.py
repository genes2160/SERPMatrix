# apps/seo/providers/serp/simple_google_scrape.py

import requests
from bs4 import BeautifulSoup

class SimpleGoogleScrapeProvider:
    def search(self, keyword, geo="GH", device="desktop"):
        headers = {
            "User-Agent": "Mozilla/5.0"
        }

        url = f"https://www.google.com/search?q={keyword}"
        res = requests.get(url, headers=headers)

        soup = BeautifulSoup(res.text, "html.parser")

        results = []
        for g in soup.select("div.tF2Cxc")[:10]:
            link = g.find("a")
            title = g.find("h3")

            if link and title:
                results.append({
                    "title": title.text,
                    "link": link["href"],
                })

        return results