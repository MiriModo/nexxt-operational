"""O singură funcție `features(...)`, folosită identic la antrenare și la inferență.

Vectorul e construit din ce vede agentul (observabile): B în orizont, legăturile cu banca, semnalele active,
clientul, creditul și concluziile verificărilor. Niciodată din `comportament` sau din etichetă. `FEATURE_NAMES`
fixează ordinea coloanelor; versiunea schemei intră în metadatele modelului.
"""
from __future__ import annotations

import math
from datetime import date

from ..common import parse_date, years_between

SCHEMA_VERSIUNE = 1
NIVELURI = ("gold", "platinum")                           # standard = referință
TIPOLOGII = ("salariat", "independent", "pensionar", "antreprenor", "diaspora", "tanar_fara_istoric")
PRODUSE = ("ipotecar", "imobiliar", "nevoi_personale", "card_credit", "refinantare")
ACTIVE = ("salariu_mutat", "cerere_adeverinta_sold", "expirare_dobanda_fixa", "interogari_bc", "simulare_in_app", "rata_alt_creditor")

FEATURE_NAMES: tuple[str, ...] = (
    "B_norm", "B_log", "legaturi", "leg_produse", "leg_vechime", "leg_nivel", "leg_activitate", "n_active",
    *(f"activ_{a}" for a in ACTIVE),
    "vechime_ani", "nr_produse", "sold_log", "luni_ramase", "dobanda_fixa", "marja", "dti", "dti_necunoscut",
    "interogari_bc", "salariu_alta_banca",
    *(f"nivel_{n}" for n in NIVELURI), *(f"tip_{t}" for t in TIPOLOGII), *(f"produs_{p}" for p in PRODUSE),
)


def features(B: float, legaturi: dict, semnale_active: list[str], client: dict, loan: dict | None, concluzii: dict,
             today: date, cfg, luni_ramase: int | None = None) -> dict[str, float]:
    R = cfg.retention
    comp = legaturi.get("componente", {})
    dti = (concluzii or {}).get("dti_curent")
    x: dict[str, float] = {
        "B_norm": min(max(B, 0.0) / R.B_referinta_ron, R.B_norm_max),
        "B_log": math.log1p(max(B, 0.0)) / 12.0,
        "legaturi": float(legaturi.get("scor", 0.0)),
        "leg_produse": float(comp.get("produse", 0.0)), "leg_vechime": float(comp.get("vechime", 0.0)),
        "leg_nivel": float(comp.get("nivel", 0.0)), "leg_activitate": float(comp.get("activitate", 0.0)),
        "n_active": float(len(semnale_active)),
    }
    for a in ACTIVE:
        x[f"activ_{a}"] = 1.0 if a in semnale_active else 0.0
    x["vechime_ani"] = min(20.0, years_between(parse_date(client["client_din"]), today)) / 20.0
    x["nr_produse"] = min(4, len(client.get("produse_atasate", []))) / 4.0
    x["sold_log"] = math.log1p(loan["sold_ramas"]) / 15.0 if loan else 0.0
    x["luni_ramase"] = min(360, luni_ramase or 0) / 360.0
    x["dobanda_fixa"] = 1.0 if loan and loan.get("tip_dobanda") == "fixa" else 0.0
    x["marja"] = (loan.get("marja") or 0.0) / 5.0 if loan else 0.0
    x["dti"] = min(1.5, dti) if dti is not None else 0.0
    x["dti_necunoscut"] = 0.0 if dti is not None else 1.0
    x["interogari_bc"] = min(5, (concluzii or {}).get("interogari_bc", 0) or 0) / 5.0
    x["salariu_alta_banca"] = 1.0 if (concluzii or {}).get("salariu_la_alta_banca") else 0.0
    for n in NIVELURI:
        x[f"nivel_{n}"] = 1.0 if client.get("nivel_relatie") == n else 0.0
    for t in TIPOLOGII:
        x[f"tip_{t}"] = 1.0 if client.get("tipologie_declarata") == t else 0.0
    for p in PRODUSE:
        x[f"produs_{p}"] = 1.0 if loan and loan.get("produs") == p else 0.0
    assert tuple(x) == FEATURE_NAMES, "features(): ordinea coloanelor diferă de FEATURE_NAMES"
    return x


def vector(x: dict[str, float]) -> list[float]:
    return [float(x[f]) for f in FEATURE_NAMES]
