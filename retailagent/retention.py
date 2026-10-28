"""Modelul de retenție: cea mai ieftină implicare a băncii care păstrează clientul (MODEL_FINAL §3).

Partea de model (funcții pure, parametri din config/retention.yaml):
    B  = câștigul clientului dacă pleacă = dobânda la noi − dobânda la dobânda pieței − costul mutării,
         pe graficul de rambursare, în orizontul de decizie (retention.yaml → orizont_ani), nu „gap × sold × ani"
    legături ∈ [0,1] = produse active, vechime, nivel, activitate pe cont
    V  = valoarea clientului dacă rămâne = marjă × sold × ani rămași + produse atașate × ani
    p  = sigmoid(a·B_norm + b·semnale_active − c − d·legături)

Meniul de intervenții, constrângerile și optimizarea sunt în `retention_menu.py` (M3-T2).
"""
from __future__ import annotations

import math
from datetime import date

from .common import parse_date, years_between
from .config_loader import Config
from .finance import cost_mutare_total, dobanda_perioada, luni_ramase, segmente_credit
from .signals.util import ani_ramasi, marja_efectiva


def dobanda_piata(loan: dict, market: dict, cfg: Config) -> float:
    return float(market["dobanzi_piata"][loan["produs"]][cfg.retention.piata[loan["produs"]]])


def castig_plecare(loan: dict, today: date, market: dict, cfg: Config, cost_mutare: float | None = None) -> dict:
    """B și descompunerea lui. `cost_mutare` poate veni din verificări; altfel se calculează din market.json."""
    luni = luni_ramase(loan, today)
    orizont = min(luni, round(cfg.retention.orizont_ani * 12))
    la_noi = dobanda_perioada(loan["sold_ramas"], segmente_credit(loan, today, market), orizont)
    piata_pct = dobanda_piata(loan, market, cfg)
    piata = dobanda_perioada(loan["sold_ramas"], [(luni, piata_pct)], orizont)
    if cost_mutare is None:
        cost_mutare = cost_mutare_total(loan, market)[0]
    brut = la_noi - piata - cost_mutare
    return {"B": round(max(0.0, brut), 2), "B_brut": round(brut, 2), "dobanda_la_noi": round(la_noi, 2),
            "dobanda_piata": round(piata, 2), "dobanda_pct_piata": piata_pct, "cost_mutare": round(cost_mutare, 2),
            "luni_ramase": luni, "orizont_luni": orizont}


def legaturi(client: dict, transactions: list[dict], salariu_la_alta_banca: bool, today: date, cfg: Config) -> dict:
    """Cât de legat e clientul de bancă (0..1): produse active, vechime, nivel, activitate pe cont."""
    L = cfg.retention.legaturi
    produse = list(client.get("produse_atasate", []))
    if salariu_la_alta_banca and "cont_salariu" in produse:
        produse.remove("cont_salariu")                     # contul de salariu nu mai e activ
    c_produse = min(1.0, len(produse) / L.produse_max)
    vechime = years_between(parse_date(client["client_din"]), today)
    c_vechime = min(1.0, max(0.0, vechime / L.vechime_max_ani))
    c_nivel = L.nivel_scor.get(client.get("nivel_relatie", "standard"), 0.0)
    luni = {f"{today.year:04d}-{today.month:02d}"}
    luni.add(f"{today.year - (today.month == 1):04d}-{(today.month - 2) % 12 + 1:02d}")
    iesiri = sum(t["suma"] for t in transactions if t["directie"] == "out" and t["data"][:7] in luni)
    c_activ = 1.0 if iesiri >= L.activitate_min_ron else 0.0
    comp = {"produse": round(c_produse, 3), "vechime": round(c_vechime, 3), "nivel": c_nivel, "activitate": c_activ}
    scor = sum(L.ponderi[k] * comp[k] for k in comp)
    return {"scor": round(scor, 3), "componente": comp, "produse_active": produse, "vechime_ani": round(vechime, 1),
            "iesiri_2_luni": round(iesiri, 2), "suficiente_pentru_oferta": scor >= L.min_pentru_oferta}


def valoare_client(loan: dict, client: dict, today: date, market: dict, cfg: Config) -> dict:
    """V = marjă × sold × ani rămași + Σ produse atașate × ani (plafonat la ani_max_produse)."""
    R = cfg.retention.valoare
    ani = ani_ramasi(loan, today)
    venit_marja = marja_efectiva(loan, market) / 100 * loan["sold_ramas"] * ani
    ani_p = min(ani, R.ani_max_produse)
    produse = sum(R.produse_ron_pe_an.get(p, 0.0) for p in client.get("produse_atasate", [])) * ani_p
    return {"V": round(venit_marja + produse, 2), "venit_marja": round(venit_marja, 2), "produse": round(produse, 2),
            "ani_ramasi": round(ani, 2)}


def semnale_active(semnale: list[dict], concluzii: dict, cfg: Config) -> tuple[int, list[str]]:
    """Câte semnale „active" are cazul (din retention.yaml → semnale_active) + interogările recente la BC."""
    R = cfg.retention
    lista = [s["id"] for s in semnale if s["id"] in R.semnale_active and s["scor"] >= R.semnale_active[s["id"]]]
    if (concluzii or {}).get("interogari_bc", 0) >= R.interogari_bc_min_pentru_activ:
        lista.append("interogari_bc")
    return len(lista), lista


def prob_plecare(B: float, n_active: int, legaturi_scor: float, cfg: Config, efect_scor: float = 0.0) -> float:
    R = cfg.retention
    s = R.sigmoid
    b_norm = min(max(B, 0.0) / R.B_referinta_ron, R.B_norm_max)
    x = s["a"] * b_norm + s["b"] * n_active - s["c"] - s["d"] * legaturi_scor + efect_scor
    return 1.0 / (1.0 + math.exp(-x))
