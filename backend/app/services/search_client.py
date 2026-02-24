from __future__ import annotations

import requests


SERPAPI_URL = "https://serpapi.com/search.json"


def google_search(query: str, api_key: str, num: int = 10) -> list[dict]:
    if not api_key:
        raise ValueError("SERPAPI_KEY is not configured")

    params = {
        "engine": "google",
        "q": query,
        "num": num,
        "api_key": api_key,
    }
    response = requests.get(SERPAPI_URL, params=params, timeout=25)
    response.raise_for_status()
    data = response.json()

    results: list[dict] = []
    for item in data.get("organic_results", []):
        link = item.get("link", "")
        title = item.get("title", "")
        if "linkedin.com/in" in link:
            results.append({"title": title, "url": link, "raw": item})
    return results
