"""Calcule financiare pure (M1-T1): anuitate, grafic, dobândă pe scenarii, OUG 50, DTI, vârstă."""
from __future__ import annotations

from datetime import date

import pytest

from retailagent.finance import (comision_rambursare_anticipata, dobanda_totala, dti, grafic, luni_ramase,
                                 rata_anuitate, segmente_credit, varsta_la)

TODAY = date(2026, 10, 28)
MARKET = {"ircc": 5.55}
OUG50 = {"fixa_peste_1_an_pct": 1.0, "fixa_sub_1_an_pct": 0.5, "variabila_pct": 0.0}


def loan(**kw):
    l = {"loan_id": "L1", "produs": "ipotecar", "sold_ramas": 300_000, "data_scadenta": "2046-10-28",
         "tip_dobanda": "fixa", "dobanda_curenta": 5.2, "dobanda_fixa_expira_la": "2027-10-28", "marja": 2.5}
    l.update(kw)
    return l


def test_anuitate_pe_caz_cunoscut():
    # 100.000 RON, 6% / an, 10 ani → 1.110,21 RON (formula standard a anuității)
    assert rata_anuitate(100_000, 6.0, 120) == pytest.approx(1110.21, abs=0.01)
    assert rata_anuitate(12_000, 0.0, 12) == pytest.approx(1000.0)


def test_graficul_stinge_soldul_si_dobanda_totala_coincide():
    rows = grafic(100_000, [(120, 6.0)], "2026-11")
    assert len(rows) == 120
    assert rows[-1]["sold_ramas"] == pytest.approx(0.0, abs=0.01)
    assert rows[0]["luna"] == "2026-11" and rows[1]["luna"] == "2026-12" and rows[2]["luna"] == "2027-01"
    assert sum(r["dobanda"] for r in rows) == pytest.approx(dobanda_totala(100_000, [(120, 6.0)]), abs=0.5)
    assert dobanda_totala(100_000, [(120, 6.0)]) == pytest.approx(120 * 1110.21 - 100_000, abs=1.0)


def test_schimbarea_de_dobanda_reamortizeaza():
    # 2 ani la 5% apoi 8%: dobânda totală e între „tot la 5%" și „tot la 8%", iar rata crește la schimbare
    mixt = dobanda_totala(200_000, [(24, 5.0), (216, 8.0)])
    assert dobanda_totala(200_000, [(240, 5.0)]) < mixt < dobanda_totala(200_000, [(240, 8.0)])
    rows = grafic(200_000, [(24, 5.0), (216, 8.0)], "2026-11")
    assert rows[23]["rata"] < rows[24]["rata"]
    assert rows[23]["dobanda_pct"] == 5.0 and rows[24]["dobanda_pct"] == 8.0


def test_luni_ramase():
    assert luni_ramase(loan(), TODAY) == 240
    assert luni_ramase(loan(produs="card_credit"), TODAY) == 12
    assert luni_ramase(loan(data_scadenta="2020-01-01"), TODAY) == 1       # scadență trecută → minimum 1


def test_segmente_credit_fixa_apoi_variabila():
    seg = segmente_credit(loan(), TODAY, MARKET)
    assert seg == [(12, 5.2), (228, 8.05)]
    assert segmente_credit(loan(tip_dobanda="variabila", dobanda_fixa_expira_la=None, dobanda_curenta=8.05),
                           TODAY, MARKET) == [(240, 8.05)]
    # fixa pe toată durata (fără marjă) rămâne la dobânda curentă
    assert segmente_credit(loan(produs="nevoi_personale", marja=None, dobanda_fixa_expira_la=None,
                                dobanda_curenta=11.0, data_scadenta="2029-10-28"), TODAY, MARKET) == [(36, 11.0)]
    # fixa deja expirată → direct IRCC + marjă
    assert segmente_credit(loan(dobanda_fixa_expira_la="2025-01-01"), TODAY, MARKET) == [(240, 8.05)]


def test_comision_oug50():
    assert comision_rambursare_anticipata(loan(tip_dobanda="variabila"), 20_000, TODAY, OUG50)[0] == 0.0
    c, txt = comision_rambursare_anticipata(loan(dobanda_fixa_expira_la="2029-10-28"), 20_000, TODAY, OUG50)
    assert c == pytest.approx(200.0) and "1.0%" in txt
    c, _ = comision_rambursare_anticipata(loan(dobanda_fixa_expira_la="2027-03-01"), 20_000, TODAY, OUG50)
    assert c == pytest.approx(100.0)


def test_dti_si_varsta():
    assert dti(2_000, 5_000) == pytest.approx(0.4)
    assert dti(2_000, 0) is None
    assert varsta_la("1960-10-28", date(2046, 10, 28)) == pytest.approx(86.0, abs=0.05)
