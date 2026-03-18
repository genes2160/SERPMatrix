import gzip
import base64
from bs4 import BeautifulSoup
from collections import Counter
from urllib.parse import urlparse

STOP_WORDS = {
    "the","and","for","are","but","not","you","all","can","was","one",
    "our","out","day","get","has","him","his","how","its","may","new",
    "now","old","see","two","who","boy","did","she","too","use","way",
    "with","that","this","have","from","they","will","been","more",
    "when","your","what","said","each","which","their","time","into",
    "than","then","some","could","these","other","also","just","over",
    "such","very","well","even","most","made","after","where","while",
    "about","would",
}

def compress_html(html: str) -> str:
    compressed = gzip.compress(html.encode("utf-8"))
    return base64.b64encode(compressed).decode("utf-8")

def decompress_html(encoded: str) -> str:
    compressed = base64.b64decode(encoded.encode("utf-8"))
    return gzip.decompress(compressed).decode("utf-8")


def extract_page_data(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    # Remove noise
    for tag in soup(["script", "style", "noscript"]):
        tag.extract()

    # Metadata
    title = soup.title.string.strip() if soup.title and soup.title.string else None

    meta_desc_tag = soup.find("meta", attrs={"name": "description"})
    meta_description = (
        meta_desc_tag["content"].strip()
        if meta_desc_tag and meta_desc_tag.get("content")
        else None
    )

    # Headings
    h1 = soup.find("h1")
    h1_text = h1.get_text(strip=True) if h1 else None

    h2s = [h.get_text(strip=True) for h in soup.find_all("h2")][:10]
    h3s = [h.get_text(strip=True) for h in soup.find_all("h3")][:10]

    # Content
    paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
    text_content = " ".join(paragraphs)
    words = text_content.split()
    word_count = len(words)

    # Keywords
    clean_words = [
        w.lower() for w in words
        if len(w) > 3 and w.lower() not in STOP_WORDS
    ]
    top_keywords = [kw for kw, _ in Counter(clean_words).most_common(15)]

    # Links
    base_domain = urlparse(url).netloc
    internal_links = 0
    external_links = 0

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if base_domain in href:
            internal_links += 1
        elif href.startswith("http"):
            external_links += 1

    images = len(soup.find_all("img"))

    return {
        "title": title,
        "meta_description": meta_description,
        "h1": h1_text,
        "h2s": h2s,
        "h3s": h3s,
        "word_count": word_count,
        "text_content": text_content[:5000],  # cap
        "top_keywords": top_keywords,
        "internal_links": internal_links,
        "external_links": external_links,
        "images": images,
        "content_chunks": paragraphs[:20],
    }