from __future__ import annotations

import logging
import re
from typing import Any

import requests

from ..config import settings
from .domains import get_company_domain
from .title_parser import detect_seniority

logger = logging.getLogger(__name__)


# ── SerpAPI ────────────────────────────────────────────────────────────────────

def serpapi_search(query: str, num: int = 10) -> list[dict[str, Any]]:
    if not settings.serpapi_key:
        logger.warning("SERPAPI_KEY not set — returning empty results")
        return []
    try:
        resp = requests.get(
            "https://serpapi.com/search",
            params={"engine": "google", "q": query, "api_key": settings.serpapi_key, "num": num},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("organic_results", [])
    except Exception as exc:
        logger.error("SerpAPI error: %s", exc)
        return []


# ── LinkedIn snippet parser ────────────────────────────────────────────────────

def parse_linkedin_snippet(result: dict[str, Any]) -> dict[str, Any] | None:
    title_raw: str = result.get("title", "")
    snippet: str = result.get("snippet", "")
    link: str = result.get("link", "")

    if "linkedin.com/in/" not in link:
        return None

    # Parse name from title: "John Smith - Investment Analyst at Goldman Sachs | LinkedIn"
    name_part = title_raw.split(" - ")[0].strip() if " - " in title_raw else title_raw.split("|")[0].strip()
    parts = name_part.split()
    first_name = parts[0] if parts else ""
    last_name = " ".join(parts[1:]) if len(parts) > 1 else ""

    # Parse job title and company
    job_title = ""
    company = ""
    if " - " in title_raw:
        rest = title_raw.split(" - ", 1)[1]
        rest = rest.replace("| LinkedIn", "").strip()
        if " at " in rest:
            job_title, company = rest.split(" at ", 1)
            job_title = job_title.strip()
            company = company.split("|")[0].strip()
        else:
            job_title = rest.split("|")[0].strip()

    # Parse location and school from snippet
    location = ""
    school = ""
    if snippet:
        # LinkedIn snippets often have "City · connections · University"
        lines = snippet.replace("\n", " · ").split(" · ")
        for part in lines:
            part = part.strip()
            if re.search(r"\b(NY|CA|IL|MA|TX|NY|London|Chicago|Boston|San Francisco|New York)\b", part, re.I):
                location = part
            if re.search(r"\b(university|college|school|institute|business)\b", part, re.I):
                school = part

    if not first_name:
        return None

    return {
        "first_name": first_name,
        "last_name": last_name,
        "title": job_title,
        "company": company,
        "location": location,
        "school": school,
        "linkedin_url": link,
        "email": None,
    }


# ── Fit score ──────────────────────────────────────────────────────────────────

def calculate_fit_score(
    contact: dict[str, Any],
    title_keywords: str,
    seniority_levels: str,
    target_schools: str,
    location_list: str,
) -> float:
    score = 0.0

    # Title keyword match (40 points)
    title = (contact.get("title") or "").lower()
    for kw in title_keywords.splitlines():
        if kw.strip().lower() in title:
            score += 40
            break

    # Seniority match (25 points)
    detected = detect_seniority(title)
    target_levels = [s.strip().lower() for s in seniority_levels.split(",") if s.strip()]
    if detected in target_levels:
        score += 25

    # School match (20 points)
    school = (contact.get("school") or "").lower()
    for s in target_schools.splitlines():
        if s.strip().lower() and s.strip().lower() in school:
            score += 20
            break

    # Location match (15 points)
    location = (contact.get("location") or "").lower()
    for loc in location_list.splitlines():
        if loc.strip().lower() and loc.strip().lower() in location:
            score += 15
            break

    return min(score, 100.0)


# ── Hunter.io email finder ─────────────────────────────────────────────────────

def hunter_find_email(first_name: str, last_name: str, domain: str | None) -> str | None:
    if not domain or not settings.hunter_api_key or settings.hunter_api_key == "your_hunter_api_key_here":
        return None
    try:
        resp = requests.get(
            "https://api.hunter.io/v2/email-finder",
            params={
                "domain": domain,
                "first_name": first_name,
                "last_name": last_name,
                "api_key": settings.hunter_api_key,
            },
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            email = data.get("data", {}).get("email")
            return email
    except Exception as exc:
        logger.error("Hunter.io error: %s", exc)
    return None


# ── Main generation function ───────────────────────────────────────────────────

def generate_contacts(
    company_list: str,
    title_keywords: str,
    location_list: str,
    target_schools: str,
    seniority_levels: str,
    target_count: int,
) -> list[dict[str, Any]]:
    companies = [c.strip() for c in company_list.splitlines() if c.strip()]
    titles = [t.strip() for t in title_keywords.splitlines() if t.strip()]
    locations = [l.strip() for l in location_list.splitlines() if l.strip()]
    first_location = locations[0] if locations else ""

    queries: list[tuple[str, str, str]] = []
    for company in companies:
        for title in titles:
            query = f'site:linkedin.com/in "{title}" "{company}"'
            if first_location:
                query += f' "{first_location}"'
            queries.append((company, title, query))

    raw_results: list[dict[str, Any]] = []
    for company, title, query in queries[:20]:  # cap queries
        results = serpapi_search(query, num=10)
        raw_results.extend(results)

    seen_urls: set[str] = set()
    contacts: list[dict[str, Any]] = []

    for result in raw_results:
        contact = parse_linkedin_snippet(result)
        if not contact:
            continue
        url = contact.get("linkedin_url", "")
        if url in seen_urls:
            continue
        seen_urls.add(url)

        contact["fit_score"] = calculate_fit_score(
            contact, title_keywords, seniority_levels, target_schools, location_list
        )

        # Find email via Hunter.io
        domain = get_company_domain(contact.get("company", ""))
        contact["email"] = hunter_find_email(
            contact.get("first_name", ""), contact.get("last_name", ""), domain
        )

        contacts.append(contact)

    contacts.sort(key=lambda x: x.get("fit_score", 0), reverse=True)
    return contacts[: target_count * 2]
