from __future__ import annotations

SENIORITY_MAP = {
    "intern": "intern",
    "summer analyst": "analyst",
    "analyst": "analyst",
    "associate": "associate",
    "senior associate": "associate",
    "vp": "vp",
    "vice president": "vp",
    "director": "director",
    "executive director": "executive director",
    "managing director": "managing director",
    "md": "managing director",
    "partner": "partner",
    "principal": "principal",
    "head": "director",
    "manager": "associate",
    "senior": "vp",
}


def detect_seniority(title: str) -> str:
    title_lower = title.lower()
    # Check longer phrases first
    for phrase in sorted(SENIORITY_MAP, key=len, reverse=True):
        if phrase in title_lower:
            return SENIORITY_MAP[phrase]
    return "analyst"
