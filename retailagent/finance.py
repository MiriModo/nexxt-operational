"""Calcule financiare pure: anuitate, grafic de rambursare, dobândă pe scenarii, comision OUG 50, DTI.

Toate funcțiile primesc numere și întorc numere; nu citesc fișiere și nu depind de configurație.
Dobânzile sunt procente anuale (5.1 = 5,1%), perioadele în luni. Un „scenariu" e o listă de segmente
(luni, dobândă%) — de exemplu 12 luni la fixa curentă, apoi 228 luni la IRCC + marjă.
"""
from __future__ import annotations

from datetime import date

from .common import fmt_ron, parse_date, shift_month


def rata_anuitate(sold: float, dobanda_pct: float, luni: int) -> float:
    """Rata lunară constantă care stinge `sold` în `luni` la dobânda dată."""
    luni = max(1, int(luni))
    r = dobanda_pct / 100 / 12
    if r <= 0:
        return sold / luni
    return sold * r / (1 - (1 + r) ** -luni)


def luni_ramase(loan: dict, today: date) -> int:
    if loan["produs"] == "card_credit":
        return 12                          # revolving: orizont de un an
    scad = parse_date(loan["data_scadenta"])
    return max(1, (scad.year - today.year) * 12 + scad.month - today.month)


def _iter_scenariu(sold: float, segmente: list[tuple[int, float]]):
    """Generează (nr, dobândă, principal, sold_rămas, dobândă%) lună de lună.

    La fiecare schimbare de dobândă rata se recalculează pe soldul rămas și pe lunile rămase, exact cum
    face banca la expirarea perioadei fixe sau la o renegociere.
    """
    total = sum(l for l, _ in segmente)
    rest, idx = float(sold), 0
    for luni_seg, dob in segmente:
        rata = rata_anuitate(rest, dob, total - idx)
        r = dob / 100 / 12
        for _ in range(luni_seg):
            if rest <= 0.005:
                return
            d = rest * r
            principal = min(rest, rata - d)
            rest -= principal
            idx += 1
            yield idx, d, principal, max(0.0, rest), dob


def rata_in_luna(sold: float, segmente: list[tuple[int, float]], luna: int) -> float:
    """Rata plătită în luna `luna` (1 = luna următoare) a scenariului; 0 dacă creditul e stins până atunci."""
    for nr, d, principal, *_ in _iter_scenariu(sold, segmente):
        if nr == luna:
            return d + principal
    return 0.0


def grafic(sold: float, segmente: list[tuple[int, float]], luna_start: str) -> list[dict]:
    """Graficul de rambursare, rând cu rând, pentru un scenariu de dobânzi."""
    rows, luna = [], luna_start
    for nr, d, principal, rest, dob in _iter_scenariu(sold, segmente):
        rows.append({"nr": nr, "luna": luna, "rata": round(d + principal, 2), "dobanda": round(d, 2),
                     "principal": round(principal, 2), "sold_ramas": round(rest, 2), "dobanda_pct": dob})
        luna = shift_month(luna, 1)
    return rows


def dobanda_totala(sold: float, segmente: list[tuple[int, float]]) -> float:
    """Dobânda totală plătită pe un scenariu (fără a construi graficul în memorie)."""
    return sum(d for _, d, *_ in _iter_scenariu(sold, segmente))


def dobanda_perioada(sold: float, segmente: list[tuple[int, float]], luni: int) -> float:
    """Dobânda plătită în primele `luni` ale scenariului (orizontul de decizie al clientului)."""
    return sum(d for nr, d, *_ in _iter_scenariu(sold, segmente) if nr <= luni)


def segmente_credit(loan: dict, today: date, market: dict, luni: int | None = None) -> list[tuple[int, float]]:
    """Scenariul „rămâi așa": dobânda curentă până la expirarea perioadei fixe, apoi IRCC + marjă."""
    luni = luni or luni_ramase(loan, today)
    exp = parse_date(loan.get("dobanda_fixa_expira_la"))
    cur = float(loan["dobanda_curenta"])
    if loan["tip_dobanda"] != "fixa" or not exp or loan.get("marja") is None:
        return [(luni, cur)]
    post = round(market["ircc"] + loan["marja"], 2)
    if exp <= today:
        return [(luni, post)]
    luni_fixe = min(luni, max(0, (exp.year - today.year) * 12 + exp.month - today.month))
    if luni_fixe >= luni:
        return [(luni, cur)]
    return [(luni_fixe, cur), (luni - luni_fixe, post)] if luni_fixe > 0 else [(luni, post)]


def comision_rambursare_anticipata(loan: dict, suma: float, today: date, reguli: dict) -> tuple[float, str]:
    """OUG 50/2010: 0 la dobândă variabilă; la fixă, un procent din suma rambursată, după anii rămași din fixă."""
    exp = parse_date(loan.get("dobanda_fixa_expira_la"))
    fixa_acum = loan["tip_dobanda"] == "fixa" and (exp is None or exp > today)
    if not fixa_acum:
        return 0.0, "dobândă variabilă → comision 0 (OUG 50/2010)"
    ani = luni_ramase(loan, today) / 12
    if exp:
        ani = min(ani, max(0.0, (exp - today).days / 365.25))
    pct = reguli["fixa_peste_1_an_pct"] if ani > 1 else reguli["fixa_sub_1_an_pct"]
    return round(suma * pct / 100, 2), f"dobândă fixă cu {ani:.1f} ani rămași → {pct:.1f}% din {fmt_ron(suma)} RON"


def cost_mutare_total(loan: dict, market: dict) -> tuple[float, dict[str, float]]:
    """Ce plătește clientul ca să-și mute creditul la altă bancă (market.json → costuri_mutare[produs])."""
    c = market["costuri_mutare"][loan["produs"]]
    sold = loan["sold_ramas"]
    comp = {"evaluare_imobil": c["evaluare_imobil"], "notar": c["notar_fix"] + sold * c["notar_pct_sold"] / 100,
            "ocpi": c["ocpi"], "asigurari_noi": c["asigurari_noi"],
            "comisioane_banca_noua": c["comision_analiza_banca_noua"] + sold * c["comision_acordare_pct"] / 100}
    return sum(comp.values()), comp


def dti(rate_lunare: float, venit_lunar: float | None) -> float | None:
    """Gradul de îndatorare: rate lunare / venit lunar net. None dacă venitul e necunoscut sau zero."""
    if not venit_lunar or venit_lunar <= 0:
        return None
    return rate_lunare / venit_lunar


def varsta_la(data_nasterii: str, la: date) -> float:
    return (la - parse_date(data_nasterii)).days / 365.25
