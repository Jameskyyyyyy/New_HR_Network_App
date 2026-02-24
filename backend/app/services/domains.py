from __future__ import annotations

COMPANY_DOMAINS: dict[str, str] = {
    "goldman sachs": "gs.com",
    "blackrock": "blackrock.com",
    "morgan stanley": "morganstanley.com",
    "jpmorgan": "jpmorgan.com",
    "jp morgan": "jpmorgan.com",
    "j.p. morgan": "jpmorgan.com",
    "bank of america": "bankofamerica.com",
    "citigroup": "citi.com",
    "citi": "citi.com",
    "citadel": "citadel.com",
    "kkr": "kkr.com",
    "blackstone": "blackstone.com",
    "carlyle": "carlyle.com",
    "apollo": "apollo.com",
    "bain capital": "baincapital.com",
    "tpg": "tpg.com",
    "bridgewater": "bwater.com",
    "two sigma": "twosigma.com",
    "renaissance technologies": "rentec.com",
    "de shaw": "deshaw.com",
    "d.e. shaw": "deshaw.com",
    "point72": "point72.com",
    "millennium": "mlp.com",
    "balyasny": "bamfunds.com",
    "alliance bernstein": "alliancebernstein.com",
    "lazard": "lazard.com",
    "evercore": "evercore.com",
    "moelis": "moelis.com",
    "piper sandler": "pipersandler.com",
    "houlihan lokey": "hl.com",
    "jefferies": "jefferies.com",
    "raymond james": "raymondjames.com",
    "wells fargo": "wellsfargo.com",
    "ubs": "ubs.com",
    "credit suisse": "credit-suisse.com",
    "deutsche bank": "db.com",
    "barclays": "barclays.com",
    "hsbc": "hsbc.com",
    "nomura": "nomura.com",
    "mizuho": "mizuhogroup.com",
    "macquarie": "macquarie.com",
    "cowen": "cowen.com",
    "pimco": "pimco.com",
    "vanguard": "vanguard.com",
    "fidelity": "fidelity.com",
    "t. rowe price": "troweprice.com",
    "t rowe price": "troweprice.com",
    "wellington": "wellington.com",
    "neuberger berman": "nb.com",
    "nuveen": "nuveen.com",
    "invesco": "invesco.com",
    "franklin templeton": "franklintempleton.com",
    "legg mason": "leggmason.com",
    "harris associates": "harrisassoc.com",
    "advent international": "adventinternational.com",
    "warburg pincus": "warburgpincus.com",
    "general atlantic": "ga.com",
    "hellman friedman": "hf.com",
    "silver lake": "silverlake.com",
    "vista equity": "vistaequitypartners.com",
    "insight partners": "insightpartners.com",
    "tiger global": "tigerglobal.com",
    "coatue": "coatue.com",
}


def get_company_domain(company: str) -> str | None:
    if not company:
        return None
    key = company.strip().lower()
    # Try exact match
    if key in COMPANY_DOMAINS:
        return COMPANY_DOMAINS[key]
    # Try partial match
    for known, domain in COMPANY_DOMAINS.items():
        if known in key or key in known:
            return domain
    # Fallback: guess from company name
    clean = "".join(c for c in key if c.isalpha() or c == " ").strip()
    first_word = clean.split()[0] if clean.split() else clean
    return f"{first_word}.com" if first_word else None
