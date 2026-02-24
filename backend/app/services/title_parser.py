# title_parser.py
import re

def parse_title(text: str):
    """
    Parse LinkedIn / Google title snippet.
    Example:
    'Jane Doe - Campus Recruiter at Goldman Sachs | LinkedIn'
    """
    if not text:
        return "", ""

    text = text.replace("| LinkedIn", "").strip()
    parts = [p.strip() for p in text.split(" - ") if p.strip()]

    name = parts[0] if len(parts) >= 1 else ""
    # Google often returns: "Name - Title - Company | LinkedIn"
    # Keep all segments after the name so we don't accidentally drop the company.
    role_company = " - ".join(parts[1:]) if len(parts) >= 2 else ""

    return name, role_company


def extract_city(snippet: str):
    """
    Try to extract city from Google snippet.
    Common patterns:
    'New York, United States'
    'Greater Chicago Area'
    'San Francisco Bay Area'
    """
    if not snippet:
        return ""

    city_patterns = [
        r"([A-Z][a-zA-Z ]+), United States",
        r"Greater ([A-Z][a-zA-Z ]+) Area",
        r"([A-Z][a-zA-Z ]+) Area",
        r"([A-Z][a-zA-Z ]+), [A-Z]{2}"
    ]

    for pattern in city_patterns:
        match = re.search(pattern, snippet)
        if match:
            return match.group(1).strip()

    return ""
