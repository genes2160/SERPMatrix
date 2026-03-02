# apps/seo/providers/serp/mock.py

class MockSerpProvider:
    def search(self, keyword, geo="GH", device="desktop"):
        return [
            {
                "title": f"{keyword} - Competitor A",
                "link": "https://competitor-a.com",
            },
            {
                "title": f"{keyword} - Competitor B",
                "link": "https://competitor-b.com",
            },
            {
                "title": f"{keyword} - Client Site",
                "link": "https://your-client-site.com",
            },
        ]