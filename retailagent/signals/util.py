"""Calcule comune folosite de mai multe semnale (și de coadă)."""
from __future__ import annotations

from datetime import date

from ..common import parse_date, years_between


def ani_ramasi(loan: dict, today: date) -> float:
    if loan["produs"] == "card_credit":
        return 1.0                       # card revolving: orizont de un an
    return max(0.0, years_between(today, parse_date(loan["data_scadenta"])))


def dobanda_post_expirare(loan: dict, market: dict) -> float | None:
    if loan.get("marja") is None:
        return None
    return round(market["ircc"] + loan["marja"], 2)


def rata_relevanta(loan: dict, market: dict, today: date, fereastra_zile: int) -> tuple[float, str]:
    """Dobânda la care se compară clientul cu piața: cea de după expirare dacă fixa expiră în fereastră."""
    exp = parse_date(loan.get("dobanda_fixa_expira_la"))
    post = dobanda_post_expirare(loan, market)
    if loan["tip_dobanda"] == "fixa" and exp and post is not None and (exp - today).days <= fereastra_zile:
        return post, "post_expirare"
    return float(loan["dobanda_curenta"]), "curenta"


def marja_efectiva(loan: dict, market: dict) -> float:
    """Marja băncii: marja contractuală sau, la card, dobânda minus IRCC."""
    if loan.get("marja") is not None:
        return float(loan["marja"])
    return max(0.0, float(loan["dobanda_curenta"]) - market["ircc"])


def ltv(loan: dict) -> float | None:
    g = loan.get("garantie")
    if not g or not g.get("valoare_evaluare"):
        return None
    return loan["sold_ramas"] / g["valoare_evaluare"]


def cereri_pe_credit(requests: list[dict], loan: dict, tipuri: list[str], zile: int, today: date) -> list[dict]:
    """Cererile de tipurile date, din ultimele `zile`, care vizează acest credit (după loan_id sau produs)."""
    out = []
    for r in requests:
        if r["tip"] not in tipuri:
            continue
        age = (today - parse_date(r["data"])).days
        if age < 0 or age > zile:
            continue
        det = r.get("detalii") or {}
        if det.get("loan_id"):
            if det["loan_id"] != loan["loan_id"]:
                continue
        elif det.get("produs_vizat") not in (None, loan["produs"]):
            continue
        out.append(r)
    return sorted(out, key=lambda r: (r["data"], r["request_id"]), reverse=True)
