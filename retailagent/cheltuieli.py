"""Profilul de cheltuieli al unui client pe ultimele luni: suma pe fiecare categorie de plată (ca în aplicația
băncii), ieșirile și intrările totale, ce pleacă spre alte bănci și spre conturile proprii.

Pur: primește tranzacțiile clientului (cu câmpul `categorie` scris de generate.py) și data de azi.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date



def transaction_category(transaction: dict) -> str:
    """Use stored categories; classify legacy rows without mutating the source data."""
    if transaction.get("categorie"):
        return transaction["categorie"]
    from .generate import categoria
    return categoria(transaction.get("platitor_beneficiar", ""), transaction.get("tip_etichetat", ""),
                     transaction.get("directie", "out"))


def luni_recente(today: date, luni: int) -> set[str]:
    """Cheile YYYY-MM ale ultimelor `luni` luni, inclusiv luna curentă."""
    y, m, out = today.year, today.month, set()
    for _ in range(luni):
        out.add(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out


def profil_cheltuieli(transactions: list[dict], today: date, luni: int = 3) -> dict:
    """Categoriile ieșirilor, ordonate descrescător, cu suma, ponderea și numărul de plăți; intrările pe lună."""
    recente = luni_recente(today, luni)
    out = [t for t in transactions if t["directie"] == "out" and t["data"][:7] in recente]
    inn = [t for t in transactions if t["directie"] == "in" and t["data"][:7] in recente]
    suma: dict[str, float] = defaultdict(float)
    nr: dict[str, int] = defaultdict(int)
    for t in out:
        cat = transaction_category(t)
        suma[cat] += t["suma"]
        nr[cat] += 1
    total_out = sum(suma.values())
    categorii = [{"categorie": c, "suma": round(s, 2), "procent": round(s / total_out, 4) if total_out else 0.0, "nr": nr[c]}
                 for c, s in sorted(suma.items(), key=lambda kv: -kv[1])]
    return {
        "luni": luni,
        "total_out": round(total_out, 2),
        "total_in": round(sum(t["suma"] for t in inn), 2),
        "venit_lunar": round(sum(t["suma"] for t in inn) / luni, 2),
        "categorii": categorii,
        "loan_payments": round(suma.get("loan_payments", 0.0), 2),
        "internal_transfers": round(suma.get("internal_transfers", 0.0), 2),
    }
