"""Categoriile de plată pe tranzacții (ca în aplicația băncii) și profilul de cheltuieli al clientului."""
from __future__ import annotations

import re
from datetime import date

import yaml

from retailagent.cheltuieli import luni_recente, profil_cheltuieli
from retailagent.generate import CATEGORII_IN, CATEGORII_OUT, COMERCIANTI_CATEGORIE, Generator, categoria

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]


def test_categoria_din_comerciant():
    assert categoria("KAUFLAND", "altele", "out") == "groceries"
    assert categoria("OMV PETROM", "altele", "out") == "transport"
    assert categoria("ENEL ENERGIE MUNTENIA", "utilitati", "out") == "utilities_bills"
    assert categoria("BCR RATA CREDIT", "rata_alt_creditor", "out") == "loan_payments"
    assert categoria("NETFLIX", "altele", "out") == "entertainment"
    assert categoria("ION POPESCU CHIRIE", "chirie_out", "out") == "housing"
    assert categoria("BEJ X POPRIRE DOSAR 1/2026", "poprire", "out") == "legal"
    assert categoria("ARGES METAL SA", "salariu", "in") == "income_salary"
    assert categoria("TRANSFER ANA POP", "transfer_propriu", "in") == "internal_transfers"
    assert categoria("NECUNOSCUT", "extern", "in") == "transfers_in"
    assert categoria("NECUNOSCUT", "altele", "out") == "other"


def test_comerciantii_noi_nu_sunt_firme_sau_creditori():
    """Regex-urile din signals.yaml (firmă SRL/SA, creditori, poprire) nu trebuie să prindă comercianții noi."""
    cfg = yaml.safe_load((ROOT / "config" / "signals.yaml").read_text(encoding="utf-8"))
    tipare = [re.compile(p, re.I) for k in ("firma", "creditor", "poprire", "pensie") for p in cfg["tipare"][k]]
    for lista in COMERCIANTI_CATEGORIE.values():
        for cine in lista:
            assert not any(p.search(cine) for p in tipare), cine


def test_toate_tranzactiile_generate_au_categorie_valida():
    g = Generator(n=60, seed=42, today=date(2026, 10, 28))
    g.run()
    assert g.transactions
    for t in g.transactions:
        permise = CATEGORII_OUT if t["directie"] == "out" else CATEGORII_IN
        assert t["categorie"] in permise, t
    cats = {t["categorie"] for t in g.transactions if t["directie"] == "out"}
    assert {"groceries", "restaurants", "transport", "utilities_bills"} <= cats


def test_categoriile_nu_schimba_sumele_si_datele():
    """RNG-ul principal nu e atins: două generări identice dau aceleași sume/date; categoria e deterministă."""
    a = Generator(n=60, seed=42, today=date(2026, 10, 28))
    a.run()
    b = Generator(n=60, seed=42, today=date(2026, 10, 28))
    b.run()
    assert a.transactions == b.transactions


def test_profil_cheltuieli():
    today = date(2026, 10, 28)
    assert luni_recente(today, 3) == {"2026-10", "2026-09", "2026-08"}
    tx = [
        {"client_id": "C1", "data": "2026-10-03", "suma": 300.0, "directie": "out", "platitor_beneficiar": "LIDL", "tip_etichetat": "altele", "categorie": "groceries"},
        {"client_id": "C1", "data": "2026-09-12", "suma": 200.0, "directie": "out", "platitor_beneficiar": "NETFLIX", "tip_etichetat": "altele", "categorie": "entertainment"},
        {"client_id": "C1", "data": "2026-08-20", "suma": 500.0, "directie": "out", "platitor_beneficiar": "BCR RATA CREDIT", "tip_etichetat": "rata_alt_creditor", "categorie": "loan_payments"},
        {"client_id": "C1", "data": "2026-05-20", "suma": 999.0, "directie": "out", "platitor_beneficiar": "LIDL", "tip_etichetat": "altele", "categorie": "groceries"},   # prea veche
        {"client_id": "C1", "data": "2026-10-10", "suma": 6000.0, "directie": "in", "platitor_beneficiar": "FIRMA SA", "tip_etichetat": "salariu", "categorie": "income_salary"},
    ]
    p = profil_cheltuieli(tx, today, luni=3)
    assert p["total_out"] == 1000.0 and p["total_in"] == 6000.0 and p["venit_lunar"] == 2000.0
    assert [c["categorie"] for c in p["categorii"]] == ["loan_payments", "groceries", "entertainment"]
    assert p["categorii"][0]["procent"] == 0.5 and p["categorii"][1]["nr"] == 1
    assert p["loan_payments"] == 500.0 and p["internal_transfers"] == 0.0
