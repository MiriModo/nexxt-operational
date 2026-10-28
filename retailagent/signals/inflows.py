"""Deducerea încasărilor și plăților recurente din tranzacții (salariu, pensie, rate la alți creditori, popriri).

Nu citește `tip_etichetat`: tipul se deduce din numele plătitorului/beneficiarului (regex din
config/signals.yaml → tipare) și din recurență (aceeași contraparte, luni consecutive).
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from ..common import last_months, month_key

VENIT = ("salariu", "pensie")


@dataclass(frozen=True)
class Flow:
    contraparte: str
    tip: str                     # salariu | pensie | dividende | rata_alt_creditor | poprire | altele
    luni: tuple[str, ...]        # luni (YYYY-MM) cu cel puțin o tranzacție, sortate
    suma_medie: float
    suma_totala: float
    ultima_data: str


@dataclass(frozen=True)
class Flows:
    months: tuple[str, ...]                 # lunile analizate (cronologic, ultima = luna lui `today`)
    venit_lunar: dict[str, float]           # salariu + pensie, per lună
    surse_venit: tuple[Flow, ...]
    creditori: tuple[Flow, ...]
    popriri: tuple[Flow, ...]
    clasificare: tuple[str, ...]            # tipul dedus pentru fiecare tranzacție (aceeași ordine)


class Patterns:
    def __init__(self, tipare: dict[str, list[str]]):
        self.rx = {k: re.compile("|".join(f"(?:{p})" for p in v), re.IGNORECASE) for k, v in tipare.items()}

    def match(self, kind: str, text: str) -> bool:
        return bool(self.rx[kind].search(text))


def _max_run(luni: list[str], months: list[str]) -> int:
    idx = sorted(months.index(m) for m in luni if m in months)
    best = run = 0
    prev = None
    for i in idx:
        run = run + 1 if prev is not None and i == prev + 1 else 1
        best = max(best, run)
        prev = i
    return best


def analyze(transactions: list[dict], today: date, patterns: Patterns, rec: dict[str, int]) -> Flows:
    months = last_months(month_key(today), rec.get("luni_analizate", 12))
    groups: dict[tuple[str, str], list[int]] = defaultdict(list)
    for i, t in enumerate(transactions):
        if t["data"][:7] in months:
            groups[(t["directie"], " ".join(t["platitor_beneficiar"].upper().split()))].append(i)

    clasificare = ["altele"] * len(transactions)
    surse, creditori, popriri = [], [], []
    venit_lunar = {m: 0.0 for m in months}

    for (directie, nume), idxs in groups.items():
        txs = [transactions[i] for i in idxs]
        luni = sorted({t["data"][:7] for t in txs})
        tip = "altele"
        if directie == "in":
            if patterns.match("pensie", nume):
                tip = "pensie"
            elif patterns.match("dividende", nume):
                tip = "dividende"
            elif patterns.match("firma", nume) and _max_run(luni, months) >= rec["salariu_min_luni_consecutive"] \
                    and len(txs) <= len(luni) + 1:          # cel mult o încasare pe lună (plus o abatere)
                tip = "salariu"
        else:
            if patterns.match("poprire", nume):
                tip = "poprire"
            elif patterns.match("creditor", nume) and len(luni) >= rec["creditor_min_luni"] \
                    and luni[-1] in months[-rec["creditor_activ_ultimele_luni"]:]:
                tip = "rata_alt_creditor"
        for i in idxs:
            clasificare[i] = tip
        total = sum(t["suma"] for t in txs)
        flow = Flow(nume, tip, tuple(luni), total / len(luni), total, max(t["data"] for t in txs))
        if tip in VENIT:
            surse.append(flow)
            for t in txs:
                venit_lunar[t["data"][:7]] += t["suma"]
        elif tip == "rata_alt_creditor":
            creditori.append(flow)
        elif tip == "poprire":
            popriri.append(flow)

    key = lambda f: f.contraparte  # noqa: E731 — ordine deterministă
    return Flows(tuple(months), venit_lunar, tuple(sorted(surse, key=key)), tuple(sorted(creditori, key=key)),
                 tuple(sorted(popriri, key=key)), tuple(clasificare))
