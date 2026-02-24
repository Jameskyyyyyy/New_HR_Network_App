from __future__ import annotations

import re
from typing import Any


MERGE_TAG_MAP = {
    "{{ First Name }}": "first_name",
    "{{ Last Name }}": "last_name",
    "{{ Company }}": "company",
    "{{ Title }}": "title",
    "{{ School }}": "school",
    "{{ Location }}": "location",
}


def render_template(template: str, contact: dict[str, Any]) -> str:
    result = template
    for tag, field in MERGE_TAG_MAP.items():
        value = contact.get(field) or ""
        result = result.replace(tag, value)
    # Also handle lowercase/flexible tags
    result = re.sub(r"\{\{\s*first\s*name\s*\}\}", contact.get("first_name") or "", result, flags=re.I)
    result = re.sub(r"\{\{\s*last\s*name\s*\}\}", contact.get("last_name") or "", result, flags=re.I)
    result = re.sub(r"\{\{\s*company\s*\}\}", contact.get("company") or "", result, flags=re.I)
    result = re.sub(r"\{\{\s*title\s*\}\}", contact.get("title") or "", result, flags=re.I)
    result = re.sub(r"\{\{\s*school\s*\}\}", contact.get("school") or "", result, flags=re.I)
    return result


DEFAULT_SUBJECT = "Interest in {{ Company }}"

DEFAULT_BODY = """Hi {{ First Name }},

I hope this message finds you well. My name is [Your Name], and I'm a student at [Your School] studying finance. I came across your profile and was impressed by your work as a {{ Title }} at {{ Company }}.

I'm currently exploring career opportunities in finance and would love to learn more about your experience and journey to {{ Company }}. Would you be open to a brief 15-minute coffee chat? I'd be happy to work around your schedule.

Thank you so much for your time — I really appreciate it.

Best,
[Your Name]
[Your School] | [Your Graduation Year]
[LinkedIn URL]"""


def generate_draft(
    subject_template: str,
    body_template: str,
    contact: dict[str, Any],
) -> tuple[str, str]:
    subject = render_template(subject_template or DEFAULT_SUBJECT, contact)
    body = render_template(body_template or DEFAULT_BODY, contact)
    return subject, body
