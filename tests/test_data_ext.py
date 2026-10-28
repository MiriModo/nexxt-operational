"""Consistența datelor pentru modelul final: mock-urile externe spun aceeași poveste ca portofoliul."""
from __future__ import annotations

import json

from retailagent.generate_ext import FINAL


def load(pipeline, name):
    return json.loads((pipeline["dir"] / name).read_text(encoding="utf-8"))


def by_client(rows):
    return {r["client_id"]: r for r in rows}


def scen(pipeline, nr):
    return pipeline["pf"].clients[nr - 1]["client_id"]


def test_fisierele_exista_pentru_fiecare_client(pipeline):
    ids = {c["client_id"] for c in pipeline["pf"].clients}
    for name in ("conturi.json", "documente.json", "externe/anaf.json", "externe/biroul_credit.json", "externe/crc.json"):
        assert set(by_client(load(pipeline, name))) == ids, name
    secured = {l["loan_id"] for l in pipeline["pf"].loans if l["garantie"]}
    assert {g["loan_id"] for g in load(pipeline, "externe/garantii.json")} == secured


def test_rata_la_alt_creditor_apare_in_biroul_de_credit(pipeline):
    bc = by_client(load(pipeline, "externe/biroul_credit.json"))
    tx = load(pipeline, "transactions.json")
    platitori = {t["client_id"]: t["suma"] for t in tx if t["tip_etichetat"] == "rata_alt_creditor"}
    assert platitori
    for cid, rata in platitori.items():
        assert any(c["stare"] == "activ" and c["rata_lunara"] == rata for c in bc[cid]["credite"]), cid


def test_crc_respecta_pragul_de_raportare(pipeline):
    for row in load(pipeline, "externe/crc.json"):
        assert all(e["sold"] >= row["prag_raportare_ron"] for e in row["expuneri"])


def test_salariu_mutat_vs_venit_pierdut_in_anaf(pipeline):
    anaf = by_client(load(pipeline, "externe/anaf.json"))
    ultima = {cid: max(s["valori"]) for cid, a in anaf.items() for s in a["surse"] if s["tip"] == "salariu"}
    luna_inchisa = anaf[scen(pipeline, 13)]["perioada"]["pana_la"]
    assert ultima[scen(pipeline, 13)] == luna_inchisa          # salariul continuă la altă bancă
    for nr in (12, 14, 15):
        assert ultima[scen(pipeline, nr)] < luna_inchisa        # venitul chiar a dispărut


def test_esecurile_plantate_la_verificari(pipeline):
    bc = by_client(load(pipeline, "externe/biroul_credit.json"))
    crc = by_client(load(pipeline, "externe/crc.json"))
    gar = load(pipeline, "externe/garantii.json")
    assert any(c["max_zile_intarziere_24l"] >= 90 for c in bc[scen(pipeline, 46)]["credite"])
    assert any(e["rol"] == "garant" and e["restante"] > 0 for e in crc[scen(pipeline, 47)]["expuneri"])
    assert any(g["cf"]["litigii"] for g in gar if g["client_id"] == scen(pipeline, 5))
    # nimeni altcineva nu are eșecuri plantate
    assert sum(1 for g in gar if g["cf"]["litigii"]) == 1
    assert sum(1 for b in bc.values() for c in b["credite"] if c["max_zile_intarziere_24l"] >= 90) == 1


def test_etalon_recomandari(pipeline):
    gt = load(pipeline, "ground_truth.json")
    for i, row in enumerate(gt):
        rec, picata, _, _ = FINAL[i % len(FINAL) + 1]
        assert row["recomandare_asteptata"] == rec
        assert row["verificare_picata_asteptata"] == picata
        assert row["comportament"]["prag_castig_plecare_ron"] > 0
    # clienții fără bandă în coadă nu au recomandare; cei cu restructurare_preventiva în coadă au restructurare
    for row in gt:
        if row["banda_asteptata"] is None:
            assert row["recomandare_asteptata"] is None
        if row["actiune_asteptata"] and row["actiune_asteptata"].startswith("task_"):
            assert row["recomandare_asteptata"] == "blocat"


def test_codebitor_si_prima_locuinta(pipeline):
    loans = pipeline["pf"].loans
    owner = next(l for l in loans if l["client_id"] == scen(pipeline, 1) and l["produs"] == "ipotecar")
    assert any(c["client_id"] == scen(pipeline, 21) for c in owner["codebitori"])
    assert all(l["prima_locuinta"] is True for l in loans if l["produs"] == "ipotecar")
    assert all(l["prima_locuinta"] is None for l in loans if l["produs"] not in ("ipotecar", "imobiliar"))


def test_poprirea_goleste_contul(pipeline):
    conturi = by_client(load(pipeline, "conturi.json"))
    for nr in (43, 44):
        assert conturi[scen(pipeline, nr)]["istoric_lunar"][-1]["sold_minim"] == 0
