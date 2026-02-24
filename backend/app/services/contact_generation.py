from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .domains import COMPANY_DOMAINS
from .search_client import google_search
from .title_parser import extract_city, parse_title


DIVISION_PATTERNS = [
    r"investment management$",
    r"asset management$",
    r"global advisors$",
    r"wealth management$",
    r"private wealth$",
    r"investors$",
    r"capital management$",
    r"capital$",
    r"corporation$",
    r"management$",
    r"associates$",
    r"financial$",
    r"global investor$",
    r"strategic advisors$",
    r"investment corporation$",
    r"investment group$",
    r"investments$",
    r"technology$",
    r"technologies$",
    r"company$",
    r"&$",
    r"strategy$",
    r"etfs$",
    r"markets$",
    r"investment$",
    r"global$",
    r"inc$",
    r"llc$",
    r"ltd$",
    r"co$",
    r"corp$",
    r"plc$",
]

COMPANY_WHITELIST = {
    "neuberger berman",
    "t. rowe price",
    "lord abbett",
    "janus henderson",
    "fidelity investments",
    "capital group",
    "vanguard",
    "pimco",
    "jennison associates",
}

GENERIC_COMPANY_TOKENS = {
    "and", "co", "company", "companies", "inc", "incorporated", "corp", "corporation", "llc",
    "ltd", "limited", "lp", "llp", "plc", "group", "holdings", "global", "international",
    "financial", "securities", "capital", "management", "asset", "assets", "investments", "investment",
    "banking",
    "partners", "partner", "advisors", "advisor", "associates", "bank",
}

GENERIC_ROLE_TOKENS = {
    "and",
    "the",
    "of",
    "for",
    "with",
    "at",
    "in",
    "to",
    "a",
    "an",
    "team",
    "role",
    "group",
    "analyst",
    "associate",
    "vice",
    "president",
    "director",
    "managing",
    "executive",
    "senior",
    "junior",
}

GROUP_MATCH_STOPWORDS = GENERIC_ROLE_TOKENS | {
    "investment",
    "banking",
    "global",
    "markets",
    "capital",
    "finance",
    "financial",
    "services",
    "coverage",
    "division",
    "industry",
    "sector",
    "group",
    "team",
    "institutional",
}

GENERIC_KEYWORD_VARIANTS = {
    "analyst",
    "associate",
    "vice president",
    "vp",
    "director",
    "executive director",
    "managing director",
    "md",
}
SHORT_DESK_TOKENS = {"fx", "fi", "dcm", "ecm", "fig", "tmt", "ma", "mna"}

SENIORITY_QUERY_MAP = {
    "Analyst": "Analyst",
    "Associate": "Associate",
    "VP": '("Vice President" OR VP)',
    "Executive Director": '("Executive Director" OR ED)',
    "Director": "Director",
    "Managing Director": '("Managing Director" OR MD)',
}

SENIORITY_UI_ORDER = [
    "Analyst",
    "Associate",
    "VP",
    "Director",
    "Executive Director",
    "Managing Director",
]

SENIORITY_ORDER_INDEX = {level: idx for idx, level in enumerate(SENIORITY_UI_ORDER)}

SENIORITY_DISTRIBUTION_WEIGHTS = {
    "Analyst": 6,
    "Associate": 3,
    "VP": 2,
    "Director": 1,
    "Executive Director": 1,
    "Managing Director": 1,
}

SENIORITY_LABEL_REGEX = {
    "Analyst": r"\banalyst\b",
    "Associate": r"\bassociate\b",
    "VP": r"\b(vice president|vp)\b",
    "Director": r"\b(director|principal)\b",
    "Executive Director": r"\bexecutive director\b",
    "Managing Director": r"\b(managing director|md)\b",
}


@dataclass
class JobContextLike:
    job_name: str
    company: str
    city: str | None = None
    jd_text: str | None = None
    extracted_keywords: list[str] | None = None


@dataclass
class ContactGenResult:
    rows: list[dict[str, Any]]
    query_count: int


def normalize_company_name(raw: str) -> str:
    name = (raw or "").strip()
    if not name:
        return ""
    name_lower = name.lower()
    if name_lower in COMPANY_WHITELIST:
        return name
    for pattern in DIVISION_PATTERNS:
        if re.search(pattern, name_lower, flags=re.IGNORECASE):
            name = re.sub(pattern, "", name, flags=re.IGNORECASE).strip()
            break
    return name


def clean_full_name(raw_name: str):
    full_name = (raw_name or "").strip()
    name = re.sub(r"\(.*?\)", "", full_name)
    name = name.split(",")[0]
    name = name.replace(".", "")
    name = re.sub(r"\s+", " ", name).strip()
    parts = [p for p in name.split(" ") if p]
    if len(parts) < 2:
        return name, (parts[0] if parts else ""), ""
    return name, parts[0], parts[-1]


def normalize_lookup_text(value: str) -> str:
    normalized = (value or "").strip().lower()
    normalized = normalized.replace("fixing income", "fixed income")
    normalized = normalized.replace("m&a", " ma ")
    normalized = normalized.replace("m & a", " ma ")
    normalized = normalized.replace("mergers & acquisitions", " mergers acquisitions ma ")
    normalized = normalized.replace("mergers and acquisitions", " mergers acquisitions ma ")
    normalized = normalized.replace("investment banking division", " investment banking ibd ")
    normalized = normalized.replace("investment banking", " investment banking ibd ")
    normalized = normalized.replace("&", " and ")
    normalized = re.sub(r"[^a-z0-9\s]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def canonicalize_search_keyword(keyword: str) -> str:
    value = (keyword or "").strip()
    if not value:
        return value
    value = re.sub(r"\bfixing\s+income\b", "fixed income", value, flags=re.IGNORECASE)
    return value


def meaningful_company_tokens(value: str) -> set[str]:
    normalized = normalize_lookup_text(value)
    return {t for t in normalized.split() if t not in GENERIC_COMPANY_TOKENS and len(t) >= 2}


def company_acronym(value: str | None) -> str:
    tokens = [t for t in normalize_lookup_text(value or "").split() if len(t) >= 2]
    if not tokens:
        return ""
    if len(tokens) == 1 and len(tokens[0]) <= 6:
        return tokens[0]
    acronym = "".join(token[0] for token in tokens)
    return acronym


def lookup_domain(company_name: str) -> str | None:
    company_norm = normalize_lookup_text(company_name)
    if not company_norm:
        return None

    company_tokens = meaningful_company_tokens(company_name)
    best_match_domain = None
    best_match_score = 0

    for key, domain in COMPANY_DOMAINS.items():
        key_norm = normalize_lookup_text(key)
        if not key_norm:
            continue
        if company_norm == key_norm:
            return domain

        key_tokens = meaningful_company_tokens(key)
        score = 0
        if len(company_norm) >= 4 and company_norm not in GENERIC_COMPANY_TOKENS:
            if key_norm in company_norm or company_norm in key_norm:
                score = max(score, 300 + min(len(company_norm), len(key_norm)))
        if company_tokens and key_tokens:
            overlap = len(company_tokens & key_tokens)
            if overlap:
                subset_bonus = 20 if (company_tokens <= key_tokens or key_tokens <= company_tokens) else 0
                score = max(score, 120 + overlap * 30 + subset_bonus)
        if score > best_match_score:
            best_match_score = score
            best_match_domain = domain

    return best_match_domain if best_match_score >= 120 else None


def extract_company_from_role_text(role_text: str) -> str:
    role = (role_text or "").strip()
    if not role:
        return ""
    at_match = re.search(r"\bat\s+(.+)$", role, flags=re.IGNORECASE)
    if at_match:
        role = at_match.group(1).strip()
    else:
        hyphen_parts = [p.strip() for p in role.split(" - ") if p.strip()]
        if len(hyphen_parts) >= 2:
            role = hyphen_parts[-1]
    role = re.split(r"\||\(|,|;|/", role)[0].strip()
    if re.search(
        r"\b(analyst|associate|vice president|vp|director|managing director|executive director|intern|researcher|trader|sales)\b",
        role,
        flags=re.IGNORECASE,
    ):
        return ""
    return role


def resolve_domain(raw_company: str, normalized_company: str, parsed_title: str, full_result_title: str) -> str | None:
    for candidate in [raw_company, normalized_company, extract_company_from_role_text(parsed_title), full_result_title]:
        domain = lookup_domain(candidate)
        if domain:
            return domain
    return None


def format_display_company(parsed: str | None, raw: str | None, base: str | None) -> str:
    for candidate in (parsed, raw, base):
        if not candidate:
            continue
        clean = str(candidate).replace("...", "").replace("…", "").strip()
        if clean:
            return clean
    return (raw or base or "").strip()


def clean_email_part(raw_part: str) -> str:
    normalized = (raw_part or "").replace("’", "'")
    cleaned = re.sub(r"[^a-zA-Z0-9\-']", "", normalized)
    cleaned = cleaned.replace("'", "")
    return cleaned.strip("-").lower()


def generate_email(first: str, last: str, domain: str | None) -> str:
    if not domain:
        return "N/A"
    first_clean = clean_email_part(first)
    last_clean = clean_email_part(last)
    if not first_clean or not last_clean:
        return "N/A"
    return f"{first_clean}.{last_clean}@{domain.lower()}"


def detect_seniority_level(title: str) -> str:
    t = (title or "").lower()
    if re.search(r"\bmanaging director\b|\bmd\b", t):
        return "Managing Director"
    if re.search(r"\bexecutive director\b", t):
        return "Executive Director"
    if re.search(r"\bvice president\b|\bvp\b", t):
        return "VP"
    if re.search(r"\bprincipal\b", t):
        return "Director"
    if re.search(r"\bdirector\b", t):
        return "Director"
    if re.search(r"\bassociate\b", t):
        return "Associate"
    if re.search(r"\banalyst\b", t):
        return "Analyst"
    return "Unknown"


def final_keywords(filters: dict[str, Any], job_context: JobContextLike) -> list[str]:
    combined = []
    # Precision-first ordering: custom group / desk keywords should run first so they fill quota before generic titles.
    for key in ["custom_keywords", "front_office_keywords", "hr_keywords"]:
        combined.extend(filters.get(key) or [])
    if not combined and job_context.extracted_keywords:
        combined.extend(job_context.extracted_keywords)
    deduped: list[str] = []
    seen = set()
    for item in combined:
        value = (item or "").strip()
        if not value:
            continue
        for variant in keyword_variants(value):
            lower = variant.lower()
            if lower in seen:
                continue
            seen.add(lower)
            deduped.append(variant)
    deduped.sort(
        key=lambda v: (
            -len([t for t in normalize_lookup_text(v).split() if t not in GROUP_MATCH_STOPWORDS]),
            -len(v),
        )
    )
    return deduped


def keyword_variants(value: str) -> list[str]:
    raw = (value or "").strip()
    if not raw:
        return []
    out = [canonicalize_search_keyword(raw)]

    # Split comma/semicolon-separated idea buckets: "Fund Finance Solutions FX, Analyst"
    parts = [p.strip() for p in re.split(r"[;,]", raw) if p.strip()]
    out.extend(canonicalize_search_keyword(p) for p in parts if p)

    # Slash expansion: "Analyst/Associate" => "Analyst", "Associate"
    slash_parts = [p.strip() for p in re.split(r"/", raw) if p.strip()]
    out.extend(canonicalize_search_keyword(p) for p in slash_parts if p)

    # Remove explicit seniority words to keep desk/group keywords usable.
    no_level = re.sub(
        r"\b(analyst|associate|vice president|vp|director|executive director|managing director|md)\b",
        " ",
        raw,
        flags=re.IGNORECASE,
    )
    no_level = re.sub(r"\s+", " ", no_level).strip(" ,-/")
    if no_level and no_level.lower() != raw.lower():
        out.append(canonicalize_search_keyword(no_level))

    # Token-level fallback (skip ultra-generic fragments)
    for token in re.split(r"[/,\-]", raw):
        t = token.strip()
        if len(t) < 3 and t.lower() not in SHORT_DESK_TOKENS:
            continue
        if t.lower() in {"analyst", "associate", "vp", "director"}:
            continue
        out.append(canonicalize_search_keyword(t))

    # Acronym-like desk tokens embedded in long phrases (e.g., FX, FIG, TMT)
    for tok in normalize_lookup_text(raw).split():
        if tok in SHORT_DESK_TOKENS:
            out.append(tok.upper() if tok != "ma" else "M&A")

    deduped: list[str] = []
    seen = set()
    for item in out:
        v = (item or "").strip()
        if not v:
            continue
        if normalize_lookup_text(v) in {normalize_lookup_text(g) for g in GENERIC_KEYWORD_VARIANTS}:
            continue
        key = v.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(v)
    return deduped


def title_has_intern_or_nonfulltime_markers(title: str | None) -> bool:
    t = (title or "").lower()
    return bool(re.search(r"\b(intern|internship|summer analyst|summer associate|incoming|off[- ]cycle)\b", t))


def title_has_former_markers(title: str | None) -> bool:
    t = (title or "").lower()
    return bool(re.search(r"\b(former|previously|prev(?:ious)?|ex[- ]|past)\b", t))


def ordered_selected_seniority_levels(levels: list[str]) -> list[str]:
    unique = []
    seen = set()
    for level in SENIORITY_UI_ORDER:
        if level in (levels or []) and level not in seen:
            unique.append(level)
            seen.add(level)
    for level in (levels or []):
        if level not in seen:
            unique.append(level)
            seen.add(level)
    return unique


def seniority_priority_key(level: str | None) -> int:
    if not level:
        return 999
    return SENIORITY_ORDER_INDEX.get(level, 999)


def title_mentions_selected_seniority(title: str | None, target_levels: list[str]) -> bool:
    text = (title or "").lower()
    if not text:
        return False
    for level in ordered_selected_seniority_levels(target_levels):
        pattern = SENIORITY_LABEL_REGEX.get(level)
        if pattern and re.search(pattern, text):
            return True
    return False


def allocate_seniority_quotas(target_levels: list[str], total_slots: int) -> dict[str, int]:
    selected = ordered_selected_seniority_levels(target_levels)
    if total_slots <= 0 or not selected:
        return {}
    weights = [SENIORITY_DISTRIBUTION_WEIGHTS.get(level, 1) for level in selected]
    weight_sum = sum(weights) or len(selected)
    exacts = [total_slots * (w / weight_sum) for w in weights]
    quotas = [int(v) for v in exacts]
    assigned = sum(quotas)
    remainders = sorted(
        [(exacts[idx] - quotas[idx], idx) for idx in range(len(selected))],
        key=lambda item: (item[0], -item[1]),  # tie-break junior levels first
        reverse=True,
    )
    for _, idx in remainders:
        if assigned >= total_slots:
            break
        quotas[idx] += 1
        assigned += 1
    return {selected[idx]: quotas[idx] for idx in range(len(selected))}


def fit_score_from_row(row: dict[str, Any]) -> int:
    raw = row.get("raw_data") or {}
    return int(raw.get("fit_score") or 0)


def candidate_row_identity(row: dict[str, Any]) -> str:
    email = str(row.get("email") or "").strip().lower()
    if email and email != "n/a":
        return f"email:{email}"
    url = str(row.get("linkedin_url") or "").strip().lower()
    if url:
        return f"url:{url}"
    return "name:" + "|".join(
        [
            str(row.get("full_name") or "").strip().lower(),
            str(row.get("company") or "").strip().lower(),
            str(row.get("title") or "").strip().lower(),
        ]
    )


def prioritize_company_rows(rows: list[dict[str, Any]], target_levels: list[str], max_per_company: int) -> list[dict[str, Any]]:
    if max_per_company <= 0 or not rows:
        return []
    selected_levels = ordered_selected_seniority_levels(target_levels)
    if not selected_levels:
        return sorted(rows, key=lambda r: (-fit_score_from_row(r), str(r.get("full_name") or "")))[:max_per_company]

    grouped: dict[str, list[dict[str, Any]]] = {level: [] for level in selected_levels}
    unknown_rows: list[dict[str, Any]] = []
    extra_rows: list[dict[str, Any]] = []

    for row in rows:
        detected = str((row.get("raw_data") or {}).get("detected_level") or "Unknown")
        if detected in grouped:
            grouped[detected].append(row)
        elif detected == "Unknown":
            unknown_rows.append(row)
        else:
            extra_rows.append(row)

    for level in grouped:
        grouped[level].sort(key=lambda r: (-fit_score_from_row(r), str(r.get("full_name") or "")))
    unknown_rows.sort(key=lambda r: (-fit_score_from_row(r), str(r.get("full_name") or "")))
    extra_rows.sort(key=lambda r: (-fit_score_from_row(r), str(r.get("full_name") or "")))

    quotas = allocate_seniority_quotas(selected_levels, max_per_company)
    picked: list[dict[str, Any]] = []
    picked_ids: set[str] = set()

    for level in selected_levels:
        quota = int(quotas.get(level, 0))
        if quota <= 0:
            continue
        for row in grouped.get(level, []):
            if len(picked) >= max_per_company or quota <= 0:
                break
            row_key = candidate_row_identity(row)
            if row_key in picked_ids:
                continue
            picked.append(row)
            picked_ids.add(row_key)
            quota -= 1

    if len(picked) < max_per_company:
        for level in selected_levels:
            for row in grouped.get(level, []):
                if len(picked) >= max_per_company:
                    break
                row_key = candidate_row_identity(row)
                if row_key in picked_ids:
                    continue
                picked.append(row)
                picked_ids.add(row_key)
            if len(picked) >= max_per_company:
                break

    if len(picked) < max_per_company:
        for row in unknown_rows + extra_rows:
            if len(picked) >= max_per_company:
                break
            row_key = candidate_row_identity(row)
            if row_key in picked_ids:
                continue
            picked.append(row)
            picked_ids.add(row_key)

    picked.sort(
        key=lambda r: (
            seniority_priority_key((r.get("raw_data") or {}).get("detected_level")),
            -fit_score_from_row(r),
            str(r.get("full_name") or ""),
        )
    )
    return picked[:max_per_company]


def looks_like_current_role_at_target(
    *,
    role_company_text: str | None,
    target_company: str,
    snippet: str | None = None,
    precision_mode: str = "strict",
) -> tuple[bool, str | None, list[str]]:
    title = (role_company_text or "").strip()
    reasons: list[str] = []
    parsed_company = extract_company_from_role_text(title)
    snippet_text = (snippet or "").strip()
    title_has_at = " at " in title.lower()
    title_company_match = bool(parsed_company and companies_likely_match(parsed_company, target_company))
    loose_title_company_match = companies_likely_match(title, target_company) if title else False
    snippet_company_match = companies_likely_match(snippet_text, target_company) if snippet_text else False

    if precision_mode == "strict":
        if not title or not title_has_at:
            return False, parsed_company or None, ["Missing explicit 'at Company' pattern in LinkedIn title."]
        if not title_company_match:
            return False, parsed_company or None, [f"Current role company does not match target company ({target_company})."]
    elif precision_mode == "balanced":
        if not title:
            return False, parsed_company or None, ["Missing LinkedIn role/company text."]
        if not (title_company_match or (title_has_at and loose_title_company_match)):
            return False, parsed_company or None, [f"Could not verify current role at target company ({target_company})."]
    else:  # search
        if not title:
            return False, parsed_company or None, ["Missing LinkedIn role/company text."]
        if not (title_company_match or loose_title_company_match or snippet_company_match):
            return False, parsed_company or None, [f"Could not verify company match for target ({target_company})."]

    primary_segment = title.split("|")[0].strip()
    if title_has_former_markers(primary_segment):
        return False, parsed_company or None, ["LinkedIn title appears to describe a former role."]
    if title_has_intern_or_nonfulltime_markers(primary_segment):
        return False, parsed_company or None, ["LinkedIn title appears to be intern/non-full-time."]

    snippet_lower = snippet_text.lower()
    if snippet_lower and re.search(r"\bformer\b|\bpreviously\b|\bex[- ]", snippet_lower):
        reasons.append("Google snippet includes prior-role markers (soft warning).")
    resolved_company = (
        parsed_company
        if (parsed_company and companies_likely_match(parsed_company, target_company))
        else (target_company if (loose_title_company_match or snippet_company_match) else None)
    )
    return True, resolved_company, reasons


def seniority_match_for_mode(
    *,
    detected_level: str,
    target_levels: list[str],
    title_text: str | None = None,
    precision_mode: str = "strict",
) -> tuple[bool, str]:
    targets = [t for t in (target_levels or []) if t]
    if not targets:
        return True, "No seniority filter provided."
    if not detected_level or detected_level == "Unknown":
        title_l = (title_text or "").lower()
        if re.search(r"\b(managing director|executive director|vice president|vp|director|principal|partner|head)\b", title_l):
            return False, "Title text indicates higher seniority than selected levels."
        if title_mentions_selected_seniority(title_text, targets):
            return True, "Title text includes selected seniority markers."
        if precision_mode == "strict":
            return False, "Could not confidently detect seniority from title."
        return False, "Could not verify seniority level from title."
    if detected_level in targets:
        return True, f"Detected level {detected_level} matches selected seniority."
    # In non-strict modes, still reject clearly higher levels when targeting junior roles.
    junior_targets = {"Analyst", "Associate"}
    if set(targets) <= junior_targets:
        return False, f"Detected level {detected_level} is outside selected seniority ({', '.join(targets)})."
    if precision_mode == "search" and detected_level == "Unknown":
        return True, "Unknown detected level allowed in search mode."
    return False, f"Detected level {detected_level} is outside selected seniority ({', '.join(targets)})."


def keyword_phrase_match_score(keyword: str, title: str | None) -> tuple[int, int, set[str]]:
    kw_norm = normalize_lookup_text(keyword)
    title_norm = normalize_lookup_text(title or "")
    if not kw_norm or not title_norm:
        return 0, 0, set()

    if kw_norm in title_norm:
        kw_tokens = {t for t in kw_norm.split() if t and t not in GROUP_MATCH_STOPWORDS}
        return 100, len(kw_tokens) or 1, kw_tokens

    kw_tokens = {t for t in kw_norm.split() if t and t not in GROUP_MATCH_STOPWORDS and len(t) >= 3}
    title_tokens = set(title_norm.split())
    overlap = kw_tokens & title_tokens
    if not kw_tokens:
        return 0, 0, set()
    if not overlap:
        return 0, 0, set()

    # Require at least one distinctive token; multi-token group keywords get higher score with more overlap.
    score = 50 + min(35, len(overlap) * 15)
    return score, len(overlap), overlap


def best_keyword_match(keywords: list[str], title: str | None) -> tuple[str | None, int, int]:
    best_keyword = None
    best_score = 0
    best_overlap = 0
    for kw in keywords or []:
        score, overlap_count, _ = keyword_phrase_match_score(kw, title)
        if score > best_score or (score == best_score and overlap_count > best_overlap):
            best_keyword = kw
            best_score = score
            best_overlap = overlap_count
    return best_keyword, best_score, best_overlap


def custom_keyword_precision_match(custom_keywords: list[str], title: str | None, *, precision_mode: str = "strict") -> tuple[bool, str | None, int]:
    custom_keywords = [k for k in (custom_keywords or []) if (k or "").strip()]
    if not custom_keywords:
        return True, None, 0
    best_kw, best_score, overlap_count = best_keyword_match(custom_keywords, title)
    if not best_kw:
        return False, None, 0
    specific_tokens = {t for t in normalize_lookup_text(best_kw).split() if t and t not in GROUP_MATCH_STOPWORDS and len(t) >= 2}
    if precision_mode == "search":
        # Search mode is broad, but Job Title Keywords should still have meaningful overlap.
        if best_score >= 50:
            return True, best_kw, best_score
        if overlap_count >= 1 and best_score >= 20:
            return True, best_kw, best_score
        return False, best_kw, best_score
    if precision_mode == "balanced":
        if best_score >= 50:
            return True, best_kw, best_score
        if len(specific_tokens) >= 2 and overlap_count >= 1 and best_score >= 35:
            return True, best_kw, best_score
        if len(specific_tokens) <= 1 and best_score >= 25:
            return True, best_kw, best_score
        return False, best_kw, best_score
    # strict mode: require exact phrase or stronger overlap for multi-token specific-group keywords
    if best_score >= 100:
        return True, best_kw, best_score
    if len(specific_tokens) >= 2 and overlap_count >= 2 and best_score >= 65:
        return True, best_kw, best_score
    if len(specific_tokens) <= 1 and best_score >= 50:
        return True, best_kw, best_score
    return False, best_kw, best_score


SENIORITY_QUERY_NEGATIVES_BY_LEVEL = {
    "Associate": ['"Associate"'],
    "VP": ['"Vice President"', "VP"],
    "Director": ['"Director"', '"Principal"'],
    "Executive Director": ['"Executive Director"', "ED"],
    "Managing Director": ['"Managing Director"', "MD"],
}


def build_seniority_exclusion_query(target_levels: list[str]) -> str:
    levels = ordered_selected_seniority_levels([lvl for lvl in (target_levels or []) if lvl])
    if not levels:
        return ""
    highest_selected_idx = max(SENIORITY_ORDER_INDEX.get(level, -1) for level in levels)
    if highest_selected_idx < 0:
        return ""
    negatives: list[str] = []
    for level in SENIORITY_UI_ORDER[highest_selected_idx + 1 :]:
        negatives.extend(SENIORITY_QUERY_NEGATIVES_BY_LEVEL.get(level, []))
    if not any(level in {"Director", "Executive Director", "Managing Director"} for level in levels):
        negatives.append('"Principal"')
    # De-duplicate while preserving order.
    seen = set()
    deduped = []
    for term in negatives:
        if term in seen:
            continue
        seen.add(term)
        deduped.append(term)
    negatives = deduped
    if not negatives:
        return ""
    return " " + " ".join(f"-{term}" for term in negatives)


def text_tokens(value: str | None, *, min_len: int = 3) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", (value or "").lower())
        if len(token) >= min_len and token not in GENERIC_ROLE_TOKENS
    }


def companies_likely_match(a: str | None, b: str | None) -> bool:
    a_norm = normalize_lookup_text(a or "")
    b_norm = normalize_lookup_text(b or "")
    if not a_norm or not b_norm:
        return False
    if a_norm == b_norm:
        return True
    if company_acronym(a) and company_acronym(a) == company_acronym(b):
        return True

    a_all_tokens = set(a_norm.split())
    b_all_tokens = set(b_norm.split())
    a_tokens = meaningful_company_tokens(a or "")
    b_tokens = meaningful_company_tokens(b or "")
    if not a_tokens or not b_tokens:
        return False
    overlap = len(a_tokens & b_tokens)
    if overlap == 0:
        return False

    # Avoid false positives on short one-token company names (e.g. "Man Group" vs "Man Numeric").
    if min(len(a_tokens), len(b_tokens)) == 1:
        single = next(iter(a_tokens if len(a_tokens) == 1 else b_tokens))
        if len(single) <= 4 and a_norm != b_norm:
            extra_a = {t for t in a_all_tokens - b_all_tokens if t not in GENERIC_COMPANY_TOKENS}
            extra_b = {t for t in b_all_tokens - a_all_tokens if t not in GENERIC_COMPANY_TOKENS}
            if extra_a or extra_b:
                return False

    return a_tokens <= b_tokens or b_tokens <= a_tokens or overlap >= min(len(a_tokens), len(b_tokens))


def compute_fit_score(
    *,
    job_context: JobContextLike,
    target_company: str,
    result_company: str,
    result_title: str,
    result_city: str | None,
    detected_level: str,
    target_levels: list[str],
    keyword_hit: str | None,
    custom_keyword_hit: str | None,
    custom_keyword_score: int,
    school_target: str | None,
    email: str | None,
    current_company_confirmed: bool = False,
) -> tuple[int, list[str]]:
    score = 18
    reasons: list[str] = []

    if companies_likely_match(result_company, target_company):
        score += 30
        reasons.append(f"Company match with target employer ({target_company}).")
    if current_company_confirmed:
        score += 22
        reasons.append("LinkedIn title indicates current role at target company.")

    if job_context.city and result_city:
        job_city = str(job_context.city).split(",")[0].strip().lower()
        cand_city = str(result_city).split(",")[0].strip().lower()
        if job_city and cand_city and (job_city == cand_city or job_city in cand_city or cand_city in job_city):
            score += 20
            reasons.append(f"Location alignment ({result_city}).")

    if detected_level and detected_level != "Unknown":
        if detected_level in (target_levels or []):
            score += 5
            reasons.append(f"Detected seniority matches your target ({detected_level}).")
        else:
            score -= 35
            reasons.append(f"Detected seniority ({detected_level}) is outside your selected levels.")
    else:
        score -= 10

    if keyword_hit and keyword_hit != custom_keyword_hit:
        score += 8
        reasons.append(f"Matched search keyword: {keyword_hit}.")
    if custom_keyword_hit and custom_keyword_score >= 50:
        score += min(40, 18 + custom_keyword_score // 4)
        reasons.append(f"Title overlaps strongly with job title keyword: {custom_keyword_hit}.")
        if custom_keyword_score >= 100:
            score += 12
            reasons.append("Strong exact phrase match on job title keyword.")
    elif custom_keyword_hit and custom_keyword_score >= 20:
        score += min(16, 6 + custom_keyword_score // 4)
        reasons.append(f"Partial title overlap with job title keyword: {custom_keyword_hit}.")
    else:
        score -= 24
        reasons.append("Weak title overlap with requested job title keywords.")

    title_tokens = text_tokens(result_title)
    job_tokens = text_tokens(job_context.job_name)
    jd_tokens: set[str] = set()
    for kw in job_context.extracted_keywords or []:
        jd_tokens |= text_tokens(kw, min_len=2)

    job_overlap = len(title_tokens & job_tokens)
    jd_overlap = len(title_tokens & jd_tokens)
    if job_overlap:
        score += min(18, 8 + job_overlap * 3)
        reasons.append("Title overlaps with the target job title.")
    elif jd_overlap:
        score += min(10, 4 + jd_overlap * 2)
        reasons.append("Title overlaps with extracted JD keywords.")

    if school_target:
        score += 7
        reasons.append(f"Matched school filter ({school_target}).")

    if email and email != "N/A":
        score += 4
        reasons.append("Predicted corporate email available.")

    title_lower = (result_title or "").lower()
    if title_has_intern_or_nonfulltime_markers(title_lower):
        score -= 35
        reasons.append("Intern/non-full-time title (de-prioritized).")
    if any(term in title_lower for term in ["recruit", "talent acquisition", "early careers", "campus"]):
        score += 5
        reasons.append("Recruiting-facing title may be high leverage for outreach.")

    score = max(0, min(100, score))

    deduped: list[str] = []
    seen = set()
    for reason in reasons:
        if reason in seen:
            continue
        seen.add(reason)
        deduped.append(reason)
    return score, deduped[:4]


def generate_contacts(filters: dict[str, Any], job_context: JobContextLike, serpapi_key: str) -> ContactGenResult:
    companies = [c.strip() for c in (filters.get("companies") or [job_context.company]) if str(c).strip()]
    selected_cities = filters.get("selected_cities") or ([job_context.city] if job_context.city else [])
    selected_cities = [c for c in selected_cities if c]
    selected_schools = [s for s in (filters.get("selected_schools") or []) if str(s).strip()]
    max_per_company = int(filters.get("max_per_company") or 10)
    levels = filters.get("seniority_levels") or ["Analyst", "Associate"]
    keywords = final_keywords(filters, job_context)

    if not companies:
        companies = [job_context.company]
    if not selected_cities:
        selected_cities = [job_context.city] if job_context.city else ["New York, NY"]
    if not keywords:
        keywords = ["Analyst", "Associate", "Research Analyst"]
    keywords = keywords[:8]

    level_filters = levels if levels else [""]

    rows: list[dict[str, Any]] = []
    seen_people: set[str] = set()
    query_count = 0

    for raw_company in companies:
        base_company = normalize_company_name(raw_company)
        company_candidates: list[dict[str, Any]] = []
        gathered_count = 0
        gather_limit = max_per_company * 6
        for city in selected_cities:
            if gathered_count >= gather_limit:
                break
            city_short = str(city).split(",")[0].strip()
            for keyword in keywords:
                if gathered_count >= gather_limit:
                    break
                for level_filter in level_filters:
                    if gathered_count >= gather_limit:
                        break

                    level_clause = f" {SENIORITY_QUERY_MAP.get(level_filter, level_filter)}" if level_filter else ""
                    query = f'site:linkedin.com/in {canonicalize_search_keyword(keyword)}{level_clause} {raw_company} "{city_short}"'
                    query_count += 1

                    for result in google_search(query, api_key=serpapi_key, num=8):
                        if gathered_count >= gather_limit:
                            break
                        raw_name, role_company_text = parse_title(result.get("title", ""))
                        raw_item = result.get("raw") or {}
                        snippet = raw_item.get("snippet") if isinstance(raw_item, dict) else None
                        full_name, first, last = clean_full_name(raw_name)

                        detected_level = detect_seniority_level(role_company_text)
                        is_current, parsed_current_company, current_filter_reasons = looks_like_current_role_at_target(
                            role_company_text=role_company_text,
                            target_company=raw_company,
                            snippet=snippet,
                            precision_mode="search",
                        )
                        if not is_current:
                            continue

                        seniority_ok, seniority_reason = seniority_match_for_mode(
                            detected_level=detected_level,
                            target_levels=[lvl for lvl in levels if lvl],
                            title_text=role_company_text,
                            precision_mode="search",
                        )
                        if not seniority_ok:
                            continue

                        title_plus_context = " ".join([str(role_company_text or ""), str(snippet or "")]).strip()
                        best_any_keyword_hit, best_any_keyword_score, _ = best_keyword_match(keywords, title_plus_context)
                        effective_keyword_hit = best_any_keyword_hit if best_any_keyword_score >= 20 else keyword

                        domain = resolve_domain(
                            raw_company=raw_company,
                            normalized_company=base_company,
                            parsed_title=role_company_text,
                            full_result_title=result.get("title", ""),
                        )
                        email = generate_email(first, last, domain)
                        actual_city = extract_city(str(snippet or "")) or city

                        matched_school = None
                        if selected_schools:
                            blob_norm = normalize_lookup_text(" ".join([role_company_text or "", snippet or ""]))
                            for school in selected_schools:
                                school_norm = normalize_lookup_text(school)
                                if school_norm and school_norm in blob_norm:
                                    matched_school = school
                                    break

                        fit_score, fit_reasons = compute_fit_score(
                            job_context=job_context,
                            target_company=job_context.company or raw_company,
                            result_company=(parsed_current_company or raw_company.strip() or base_company),
                            result_title=role_company_text or "",
                            result_city=actual_city,
                            detected_level=detected_level,
                            target_levels=[lvl for lvl in levels if lvl],
                            keyword_hit=effective_keyword_hit,
                            custom_keyword_hit=None,
                            custom_keyword_score=0,
                            school_target=matched_school,
                            email=email,
                            current_company_confirmed=True,
                        )

                        unique_key = (
                            email.lower()
                            if email != "N/A"
                            else f"{first}|{last}|{raw_company}|{result.get('url','')}".lower()
                        )
                        if unique_key in seen_people:
                            continue
                        seen_people.add(unique_key)

                        display_company = format_display_company(parsed_current_company, raw_company.strip(), base_company)
                        company_candidates.append(
                            {
                                "full_name": full_name,
                                "first_name": first or None,
                                "last_name": last or None,
                                "title": role_company_text or None,
                                "company": display_company,
                                "city": actual_city,
                                "school": matched_school,
                                "linkedin_url": result.get("url"),
                                "email": email,
                                "source_tag": keyword,
                                "raw_data": {
                                    "fit_score": fit_score,
                                    "fit_reasons": fit_reasons,
                                    "query": query,
                                    "query_keyword": keyword,
                                    "result_title": result.get("title"),
                                    "target_level": level_filter,
                                    "detected_level": detected_level,
                                    "seniority_reason": seniority_reason,
                                    "school_target": matched_school,
                                    "base_company": base_company,
                                    "current_company_reasons": current_filter_reasons,
                                    "custom_keyword_hit": None,
                                    "custom_keyword_score": 0,
                                    "snippet": snippet,
                                },
                            }
                        )
                        gathered_count += 1

        rows.extend(prioritize_company_rows(company_candidates, [lvl for lvl in levels if lvl], max_per_company))

    rows.sort(
        key=lambda r: (
            seniority_priority_key((r.get("raw_data") or {}).get("detected_level")),
            -int((r.get("raw_data") or {}).get("fit_score") or 0),
            str(r.get("company") or ""),
            str(r.get("full_name") or ""),
        )
    )
    return ContactGenResult(rows=rows, query_count=query_count)
