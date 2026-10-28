"""Fiecare semnal: un test pozitiv și unul negativ, pe contexte construite de mână."""
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from retailagent.common import last_months, month_key, shift_month
from retailagent.signals import REGISTRY, Context
from retailagent.signals.inflows import Patterns, analyze

from .conftest import TODAY

MARKET = {"data": TODAY.isoformat(), "ircc": 5.55, "dobanda_fixa_piata_ipotecar": 4.90,
          "dobanda_piata_nevoi_personale": 8.90, "dobanda_piata_card": 22.0}
MONTHS = last_months(month_key(TODAY), 12)
PH_MONTHS = last_months(shift_month(month_key(TODAY), -1), 24)


def d(days: int) -> str:
    return (TODAY + timedelta(days=days)).isoformat()


def salary(months=MONTHS, amount=8000.0, payer="ALFA LOGISTIC SRL", factor_last3=1.0):
    out = []
    for i, m in enumerate(months):
        amt = amount * (factor_last3 if i >= len(months) - 3 else 1.0)
        out.append({"client_id": "C1", "data": f"{m}-10", "suma": amt, "directie": "in",
                    "platitor_beneficiar": payer, "tip_etichetat": "salariu"})
    return out


def outflows(payee: str, months: list[str], amount=900.0):
    return [{"client_id": "C1", "data": f"{m}-15", "suma": amount, "directie": "out",
             "platitor_beneficiar": payee, "tip_etichetat": "x"} for m in months]


def base_client(**kw):
    c = {"client_id": "C1", "nume": "Test Client", "ci_expira_la": d(800), "kyc_actualizat_la": d(-100),
         "nivel_relatie": "standard", "consimtamant_anaf": True, "consimtamant_biroul_credit": True,
         "flag_pep": False, "flag_frauda_interna": False, "flag_decedat": False, "angajator_id": "F1",
         "produse_atasate": ["cont_salariu"], "tipologie_declarata": "salariat"}
    c.update(kw)
    return c


def base_loan(**kw):
    l = {"loan_id": "L1", "client_id": "C1", "produs": "ipotecar", "moneda": "RON", "suma_initiala": 400_000,
         "sold_ramas": 300_000, "data_acordare": "2020-01-15", "data_scadenta": "2045-01-15", "rata_lunara": 2400,
         "tip_dobanda": "variabila", "dobanda_curenta": 8.05, "dobanda_fixa_expira_la": None, "indice": "IRCC",
         "marja": 2.5, "restructurat_anterior": False, "restructurari": [],
         "garantie": {"tip": "imobil", "valoare_evaluare": 500_000, "data_evaluare": "2019-12-20",
                      "asigurare_expira_la": d(200)},
         "codebitori": [], "limita": None, "utilizare_limita": None}
    l.update(kw)
    return l


def card_loan(**kw):
    return base_loan(loan_id="L2", produs="card_credit", suma_initiala=10_000, sold_ramas=5_000, tip_dobanda="fixa",
                     dobanda_curenta=22.9, marja=None, indice=None, garantie=None, limita=10_000,
                     utilizare_limita=0.5, data_scadenta=d(700), **kw)


def history(loan_id="L1", zile=None, minima=None):
    zile = zile or {}
    minima = minima or set()
    return [{"loan_id": loan_id, "luna": m, "zile_intarziere": zile.get(m, 0), "suma_restanta": 500 if zile.get(m) else 0,
             "plata_minima_card": m in minima, "rambursare_anticipata": 0} for m in PH_MONTHS]


@pytest.fixture
def run(cfg):
    patterns = Patterns(cfg.signals.tipare)
    params = {s.id: s.parametri for s in cfg.signals.semnale}

    def _run(signal_id, client=None, loan=None, txs=None, payments=None, employer=None, requests=None):
        client = client or base_client()
        loan = loan if loan is not None else base_loan()
        txs = salary() if txs is None else txs
        ctx = Context(today=TODAY, client=client, loan=None, loans=[loan],
                      transactions=txs, payments={loan["loan_id"]: payments or history(loan["loan_id"])},
                      employer=employer or {"angajator_id": "F1", "nume": "ALFA LOGISTIC SRL", "status": "activ",
                                            "trend_plati_salarii_3l": 0.02},
                      market=MARKET, requests=requests or [],
                      flows=analyze(txs, TODAY, patterns, cfg.signals.recurenta))
        sd = REGISTRY[signal_id]
        return sd.fn(replace(ctx, loan=loan if sd.nivel == "credit" else None, params=params[signal_id])).scor
    return _run


def req(tip, zile_in_urma, produs="ipotecar"):
    return {"request_id": "R1", "client_id": "C1", "data": d(-zile_in_urma), "tip": tip,
            "detalii": {"produs_vizat": produs}}


def test_registry_matches_yaml(cfg):
    yaml_ids = {s.id for s in cfg.signals.semnale}
    assert yaml_ids == set(REGISTRY)
    for s in cfg.signals.semnale:
        assert (REGISTRY[s.id].familie, REGISTRY[s.id].nivel) == (s.familie, s.nivel)


# ---------------------------------------------------------------- PLECARE

def test_expirare_dobanda_fixa_pozitiv(run):
    loan = base_loan(tip_dobanda="fixa", dobanda_curenta=5.2, dobanda_fixa_expira_la=d(20))
    assert run("expirare_dobanda_fixa", loan=loan) == 1.0
    assert run("expirare_dobanda_fixa", loan=base_loan(tip_dobanda="fixa", dobanda_fixa_expira_la=d(45))) == 0.8


def test_expirare_dobanda_fixa_negativ(run):
    assert run("expirare_dobanda_fixa") == 0          # variabilă
    assert run("expirare_dobanda_fixa", loan=base_loan(tip_dobanda="fixa", dobanda_fixa_expira_la=d(400))) == 0


def test_gap_piata_bani_pozitiv(run):
    assert run("gap_piata_bani") == 1.0               # 8.05% vs 4.90% pe 300.000 RON, 18 ani


def test_gap_piata_bani_negativ(run):
    assert run("gap_piata_bani", loan=base_loan(tip_dobanda="fixa", dobanda_curenta=4.5,
                                                dobanda_fixa_expira_la=d(1000))) == 0


def test_cerere_adeverinta_sold_pozitiv(run):
    assert run("cerere_adeverinta_sold", requests=[req("adeverinta_sold", 10)]) == 1.0


def test_cerere_adeverinta_sold_negativ(run):
    assert run("cerere_adeverinta_sold", requests=[req("adeverinta_sold", 90)]) == 0       # prea veche
    assert run("cerere_adeverinta_sold", requests=[req("adeverinta_sold", 5, "card_credit")]) == 0  # alt produs


def test_rata_alt_creditor_pozitiv(run):
    assert run("rata_alt_creditor", txs=salary() + outflows("BCR RATA CREDIT", MONTHS[-3:])) == 1.0
    assert run("rata_alt_creditor", txs=salary() + outflows("IFN PROVIDENT", MONTHS[-8:])) == 0.7


def test_rata_alt_creditor_negativ(run):
    # „BOOKING” conține „ING”, dar nu e ING BANK; cumpărăturile recurente nu sunt rate
    assert run("rata_alt_creditor", txs=salary() + outflows("BOOKING.COM", MONTHS)) == 0
    assert run("rata_alt_creditor", txs=salary() + outflows("BCR RATA CREDIT", MONTHS[-2:])) == 0  # < 3 luni


def test_salariu_mutat_pozitiv(run):
    assert run("salariu_mutat", txs=salary(MONTHS[:-2])) == 0.8


def own_transfers(months=MONTHS[-2:], amount=3000.0):
    return [{"client_id": "C1", "data": f"{m}-12", "suma": amount, "directie": "in",
             "platitor_beneficiar": "TRANSFER TEST CLIENT", "tip_etichetat": "transfer_propriu"} for m in months]


def test_salariu_mutat_confirmat_de_transferuri_proprii(run):
    assert run("salariu_mutat", txs=salary(MONTHS[:-2]) + own_transfers()) == 1.0
    assert run("salariu_mutat", txs=salary(MONTHS[:-2]) + own_transfers(amount=1000)) == 0.8   # nu acoperă rata


def test_salariu_mutat_negativ(run):
    assert run("salariu_mutat") == 0
    assert run("salariu_mutat", txs=[]) == 0          # nu a avut niciodată venit la noi


def test_eligibilitate_externa_pozitiv(run):
    assert run("eligibilitate_externa") == 1.0


def test_eligibilitate_externa_negativ(run):
    assert run("eligibilitate_externa", payments=history(zile={PH_MONTHS[5]: 15})) == 0


def test_vechime_credit_pozitiv(run):
    assert run("vechime_credit", loan=base_loan(data_acordare="2017-06-01")) == 0.8


def test_vechime_credit_negativ(run):
    assert run("vechime_credit", loan=base_loan(tip_dobanda="fixa", data_acordare="2015-01-01")) == 0


def test_sold_ramas_pozitiv(run):
    assert run("sold_ramas") == pytest.approx(0.75)


def test_sold_ramas_negativ(run):
    assert run("sold_ramas", loan=card_loan()) == 0
    assert run("sold_ramas", loan=base_loan(data_scadenta=d(400))) == 0     # sub 3 ani rămași


def test_simulare_in_app_pozitiv(run):
    assert run("simulare_in_app", requests=[req("simulare_rambursare_anticipata", 5)]) == 0.6


def test_simulare_in_app_negativ(run):
    assert run("simulare_in_app", requests=[req("simulare_rambursare_anticipata", 40)]) == 0


# ---------------------------------------------------------------- RISC_CREDIT

def test_intarziere_noua_pozitiv(run):
    assert run("intarziere_noua", payments=history(zile={PH_MONTHS[-1]: 10})) == 0.9
    assert run("intarziere_noua", payments=history(zile={PH_MONTHS[-1]: 35, PH_MONTHS[-2]: 5})) == 1.0


def test_intarziere_noua_negativ(run):
    assert run("intarziere_noua") == 0
    assert run("intarziere_noua", payments=history(zile={PH_MONTHS[-1]: 10, PH_MONTHS[-2]: 10})) == 0  # nu e nouă


def test_venit_in_scadere_pozitiv(run):
    assert run("venit_in_scadere", txs=salary(factor_last3=0.5)) == 1.0
    assert run("venit_in_scadere", txs=salary(factor_last3=0.7)) == 0.8


def test_venit_in_scadere_negativ(run):
    assert run("venit_in_scadere", txs=salary(factor_last3=0.9)) == 0


def test_venit_disparut_pozitiv(run):
    assert run("venit_disparut", txs=salary(MONTHS[:-2])) == 0.9


def test_venit_disparut_negativ(run):
    assert run("venit_disparut", txs=salary(MONTHS[:-1])) == 0    # lipsește o singură lună
    assert run("venit_disparut", txs=salary(MONTHS[:-2]) + own_transfers()) == 0   # salariu mutat, ratele plătite


def test_card_stres_pozitiv(run):
    loan = card_loan(); loan["utilizare_limita"] = 0.95
    assert run("card_stres", loan=loan, payments=history("L2", minima={PH_MONTHS[-1], PH_MONTHS[-2]})) == 0.9


def test_card_stres_negativ(run):
    loan = card_loan(); loan["utilizare_limita"] = 0.95
    assert run("card_stres", loan=loan, payments=history("L2", minima={PH_MONTHS[-1]})) == 0


def test_angajator_in_dificultate_pozitiv(run):
    emp = {"angajator_id": "F1", "nume": "X SRL", "status": "insolventa", "trend_plati_salarii_3l": 0.0}
    assert run("angajator_in_dificultate", employer=emp) == 1.0


def test_angajator_in_dificultate_negativ(run):
    assert run("angajator_in_dificultate") == 0


def test_restructurare_anterioara_pozitiv(run):
    loan = base_loan(restructurat_anterior=True, restructurari=[{"data": "2023-01-01", "tip": "prelungire"}])
    assert run("restructurare_anterioara", loan=loan) == 0.5


def test_restructurare_anterioara_negativ(run):
    assert run("restructurare_anterioara") == 0


def test_poprire_activa_pozitiv(run):
    assert run("poprire_activa", txs=salary() + outflows("BEJ POPESCU POPRIRE DOSAR 1/2026", MONTHS[-1:])) == 0.7


def test_poprire_activa_negativ(run):
    assert run("poprire_activa", txs=salary() + outflows("BEJ POPESCU POPRIRE DOSAR 1/2026", MONTHS[:2])) == 0


def test_ltv_depasit_pozitiv(run):
    g = {"tip": "imobil", "valoare_evaluare": 250_000, "data_evaluare": "2021-01-01", "asigurare_expira_la": d(200)}
    assert run("ltv_depasit", loan=base_loan(garantie=g)) == 1.0      # 0.8 + 0.2 evaluare veche


def test_ltv_depasit_negativ(run):
    assert run("ltv_depasit") == 0


# ---------------------------------------------------------------- BLOCAJ_PROCES

def test_ci_expirata_pozitiv(run):
    assert run("ci_expirata", client=base_client(ci_expira_la=d(-5))) == 1.0
    assert run("ci_expirata", client=base_client(ci_expira_la=d(10))) == 0.5


def test_ci_expirata_negativ(run):
    assert run("ci_expirata") == 0


def test_kyc_vechi_pozitiv(run):
    assert run("kyc_vechi", client=base_client(kyc_actualizat_la=d(-30 * 31))) == 1.0


def test_kyc_vechi_negativ(run):
    assert run("kyc_vechi") == 0


def test_consimtamant_lipsa_pozitiv(run):
    assert run("consimtamant_lipsa", client=base_client(consimtamant_anaf=False)) == 1.0


def test_consimtamant_lipsa_negativ(run):
    assert run("consimtamant_lipsa") == 0


def test_asigurare_expirata_pozitiv(run):
    g = {"tip": "imobil", "valoare_evaluare": 500_000, "data_evaluare": "2019-12-20", "asigurare_expira_la": d(10)}
    assert run("asigurare_expirata", loan=base_loan(garantie=g)) == 1.0


def test_asigurare_expirata_negativ(run):
    assert run("asigurare_expirata") == 0
    assert run("asigurare_expirata", loan=card_loan()) == 0           # fără garanție


def test_flag_blocant_pozitiv(run):
    assert run("flag_blocant", client=base_client(flag_frauda_interna=True)) == 1.0


def test_flag_blocant_negativ(run):
    assert run("flag_blocant") == 0
