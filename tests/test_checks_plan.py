"""Planificarea verificărilor după produse deținute + motiv (M2-T2), pe cazuri construite de mână."""
from __future__ import annotations

from retailagent.checks import plan_checks


def client(**kw):
    c = {"client_id": "C1", "nume": "Test Client", "nivel_relatie": "standard", "tipologie_declarata": "salariat",
         "consimtamant_anaf": True, "consimtamant_biroul_credit": True}
    c.update(kw)
    return c


def loan(lid="L1", produs="ipotecar"):
    return {"loan_id": lid, "client_id": "C1", "produs": produs}


def case(semnale=(), risc=0.0, blocaje=(), loan_id="L1"):
    return {"case_id": "Q1", "client_id": "C1", "loan_id": loan_id,
            "semnale": [{"id": s, "familie": "x", "scor": 1.0, "dovada": ""} for s in semnale],
            "scoruri": {"risc_credit": risc}, "blocaje": list(blocaje)}


def cerere(tip):
    return {"request_id": "R1", "client_id": "C1", "tip": tip}


def ids(plan):
    return [p["id"] for p in plan["plan"]]


def omise(plan):
    return {o["id"]: o["motiv"] for o in plan["omise"]}


def test_expirare_dobanda_fixa_pe_ipotecar(cfg):
    p = plan_checks(case(["expirare_dobanda_fixa", "gap_piata_bani"]), client(),
                    [loan(), loan("L2", "card_credit")], [], cfg)
    got = ids(p)
    for v in ("identitate_kyc", "expuneri_interne", "venit_observat", "sold_cont",          # bază
              "ltv", "asigurare_garantie", "utilizare_limita_card",                           # produse deținute
              "scenarii_rata", "cost_mutare", "venit_anaf", "istoric_biroul_credit",         # motiv
              "expuneri_crc", "extras_cf", "reevaluare_garantie"):
        assert v in got, v
    assert "capacitate_plata_actuala" in got                                      # oferta are nevoie de DTI
    for v in ("comision_rambursare_anticipata", "fond_urgenta", "eligibilitate_produs_nou"):
        assert v not in got and "niciun motiv" in omise(p)[v]
    assert [m["motiv"] for m in p["motive"]][:1] == ["expirare_dobanda_fixa"] or any(m["motiv"] == "expirare_dobanda_fixa" for m in p["motive"])
    # ordinea respectă treptele
    trepte = [x["treapta"] for x in p["plan"]]
    assert trepte == sorted(trepte, key=cfg.checks.trepte.index)
    # motivul includerii e explicit
    assert any("expirare_dobanda_fixa" in x["motiv"] for x in p["plan"] if x["id"] == "scenarii_rata")
    assert any("bază" in x["motiv"] for x in p["plan"] if x["id"] == "identitate_kyc")
    assert any("ipotecar" in x["motiv"] for x in p["plan"] if x["id"] == "ltv")


def test_simulare_rambursare_anticipata_sare_externele(cfg):
    p = plan_checks(case(["simulare_in_app"]), client(), [loan()], [cerere("simulare_rambursare_anticipata")], cfg)
    got = ids(p)
    assert "comision_rambursare_anticipata" in got and "fond_urgenta" in got
    for v in ("istoric_biroul_credit", "expuneri_crc", "extras_cf", "reevaluare_garantie"):
        assert v not in got and "simulare_rambursare_anticipata" in omise(p)[v]
    assert p["interogari_externe"]["planificate"] == 0
    assert p["interogari_externe"]["evitate_vs_tot"] == p["interogari_externe"]["rulare_tot"] > 0


def test_credit_nou_fara_credite_existente(cfg):
    p = plan_checks(case(["x"][:0], loan_id=None), client(tipologie_declarata="tanar_fara_istoric"), [],
                    [cerere("credit_nou")], cfg)
    got = ids(p)
    for v in ("identitate_kyc", "venit_anaf", "istoric_biroul_credit", "expuneri_crc",
              "capacitate_plata_actuala", "eligibilitate_produs_nou"):
        assert v in got, v
    for v in ("ltv", "asigurare_garantie", "utilizare_limita_card", "extras_cf", "reevaluare_garantie"):
        assert v not in got and "nu deține" in omise(p)[v]


def test_risc_sare_scenariile_dar_adauga_castiga(cfg):
    p = plan_checks(case(["intarziere_noua"], risc=0.9), client(), [loan()], [], cfg)
    got = ids(p)
    assert "capacitate_plata_actuala" in got and "venit_anaf" in got
    assert "scenarii_rata" not in got and "risc" in omise(p)["scenarii_rata"]
    # capcana a: expirare + întârziere → scenarii_rata rămâne (adauga câștigă în fața lui sare)
    p2 = plan_checks(case(["intarziere_noua", "expirare_dobanda_fixa"], risc=0.9), client(), [loan()], [], cfg)
    assert "scenarii_rata" in ids(p2) and "cost_mutare" in ids(p2)


def test_blocaj_ruleaza_doar_identitatea(cfg):
    p = plan_checks(case(["ci_expirata"], blocaje=["ci_expirata"]), client(), [loan("L1", "nevoi_personale")],
                    [cerere("refinantare")], cfg)
    assert ids(p) == ["identitate_kyc"]
    assert all("blocat de ci_expirata" in m for v, m in omise(p).items())
    assert p["interogari_externe"]["planificate"] == 0


def test_fara_consimtamant_nu_se_interogheaza(cfg):
    p = plan_checks(case(["expirare_dobanda_fixa"]), client(consimtamant_anaf=False), [loan()], [], cfg)
    assert "venit_anaf" not in ids(p) and "consimțământ" in omise(p)["venit_anaf"]
    assert "istoric_biroul_credit" in ids(p)
