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

from .common import fmt_ron, parse_date, years_between
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


# ================================================================ oferte pe portofoliu + CLI

def _pct(x: float) -> str:
    return f"{x:.0%}"


def _descriere(i: dict) -> str:
    """Eticheta intervenției cu cifrele ei (dobânda fixă nouă, marja nouă)."""
    d = i.get("detalii") or {}
    if d.get("dobanda_fixa_noua") is not None:
        return f"{i['eticheta']} ({d['dobanda_fixa_noua']:.2f}%)"
    if d.get("marja_noua") is not None:
        return f"{i['eticheta']} (marjă {d['marja_noua']:.2f} pp)"
    return i["eticheta"]


def explicatie_oferta(o: dict) -> str:
    """Textul pentru consilier, cu cifre: câștigul clientului, p, oferta minimă, costul, alternativa, recomandarea."""
    by_id = {i["id"]: i for i in o["interventii"]}
    ales = by_id.get(o["interventie_aleasa"]) if o["interventie_aleasa"] else None
    tinta = _pct(o["p_tinta"])
    if o["interventie_aleasa"] is None:
        return f"Caz blocat: {o['motiv_alegere']}."
    if ales["tip"] == "restructurare":
        return (f"Risc de credit {o['risc_credit']:.2f}: fără ofertă de retenție. Restructurare propusă: {ales['eticheta']} "
                f"(cost administrativ {fmt_ron(ales['cost'])} RON). Alternativă: "
                + ", ".join(_descriere(by_id[a]) for a in o["alternative"] if by_id[a]["tip"] == "restructurare") + "."
                if o["alternative"] else
                f"Risc de credit {o['risc_credit']:.2f}: fără ofertă de retenție. Restructurare propusă: {ales['eticheta']} "
                f"(cost administrativ {fmt_ron(ales['cost'])} RON).")
    intro = f"Clientul ar câștiga {fmt_ron(o['B'])} RON plecând (în {o['orizont_luni'] // 12} ani); p = {_pct(o['p'])}."
    if ales["tip"] == "nimic":
        return f"{intro} Sub ținta de {tinta}: nu interveni."
    if ales["tip"] == "informare":
        return (f"{intro} Nicio intervenție fezabilă nu îl aduce sub {tinta} la un cost ≤ p×V ({fmt_ron(o['p'] * o['V'])} RON)"
                f"{' — legături insuficiente cu banca' if not o['legaturi']['suficiente_pentru_oferta'] else ''}. "
                f"Recomandare: informare + simulare personalizată (cost {fmt_ron(ales['cost'])} RON), p scade la {_pct(ales['p_dupa'])}.")
    txt = (f"{intro} Oferta minimă care îl aduce sub {tinta}: {_descriere(ales)}, cost {fmt_ron(ales['cost'])} RON "
           f"față de {fmt_ron(o['p'] * o['V'])} RON valoare pierdută (p × V, V = {fmt_ron(o['V'])} RON); p scade la {_pct(ales['p_dupa'])}.")
    alt = [by_id[a] for a in o["alternative"] if by_id[a]["tip"] not in ("nimic", "informare")][:1]
    if alt:
        txt += f" Alternativa {_descriere(alt[0])}: {fmt_ron(alt[0]['cost'])} RON, p {_pct(alt[0]['p_dupa'])}."
    else:
        txt += " Alternativă: niciuna fezabilă sub țintă."
    return txt + f" Recomandare: {ales['eticheta']}."


def build_offers(pf, cfg: Config, res, checks: list[dict]) -> list[dict]:
    """Un rând per caz din coadă: B, p, V, legături, intervenția aleasă, alternative, explicație."""
    from .retention_menu import evalueaza_caz
    by_case = {r["case_id"]: r for r in checks}
    out = []
    for case in res.cases:
        e = evalueaza_caz(pf, cfg, case, res.inputs[case["case_id"]], by_case.get(case["case_id"], {}))
        ales = next((i for i in e["interventii"] if i["id"] == e["aleasa"]), None)
        o = {"case_id": case["case_id"], "client_id": case["client_id"], "loan_id": case["loan_id"], "produs": case["produs"],
             "nivel_relatie": e["nivel_relatie"], "risc_credit": e["risc_credit"], "blocat": e["blocat"],
             "B": e["B"]["B"], "B_detalii": e["B"], "orizont_luni": e["B"].get("orizont_luni", 0), "p": e["p_inainte"],
             "p_tinta": e["p_tinta"], "V": e["V"], "valoare": e["valoare"], "legaturi": e["legaturi"],
             "semnale_active": e["semnale_active"], "interventie_aleasa": e["aleasa"],
             "eticheta": ales["eticheta"] if ales else None, "cost": ales["cost"] if ales else 0.0,
             "p_dupa": ales["p_dupa"] if ales else e["p_inainte"], "alternative": e["alternative"],
             "motiv_alegere": e["motiv_alegere"], "interventii": e["interventii"]}
        o["explicatie"] = explicatie_oferta(o)
        out.append(o)
    return out


def print_offer(o: dict) -> None:
    print(f"\n═══ {o['case_id']} · {o['client_id']} · {o['loan_id'] or 'fără credit'} · {o['produs']} · {o['nivel_relatie']}")
    print(f"  B = {fmt_ron(o['B'])} RON (în {o['orizont_luni']} luni) · V = {fmt_ron(o['V'])} RON · legături {o['legaturi']['scor']:.2f} "
          f"· semnale active: {', '.join(o['semnale_active']) or '—'} · p = {o['p']:.0%}")
    print(f"  {'intervenție':<22} {'fezabil':<8} {'cost RON':>10} {'B după':>9} {'p după':>7}  motiv")
    for i in o["interventii"]:
        ok = "da" if i["fezabil"] else "nu"
        mark = "►" if i["id"] == o["interventie_aleasa"] else " "
        print(f"{mark} {i['id']:<22} {ok:<8} {fmt_ron(i['cost']):>10} {fmt_ron(i['B_dupa']):>9} {i['p_dupa']:>7.0%}  "
              f"{'' if i['fezabil'] else i['motiv_infezabil']}"[:160])
    print(f"  → {o['explicatie']}")


def main(argv: list[str] | None = None) -> None:
    import argparse
    import time
    from collections import Counter
    from pathlib import Path

    from .checks import load_mocks, run_all_checks
    from .common import CONFIG_DIR, DATA_DIR, OUT_DIR, log_event, setup_console, write_json
    from .queue import run_pipeline

    setup_console()
    ap = argparse.ArgumentParser(description="Modelul de retenție: cea mai ieftină implicare care păstrează clientul.")
    ap.add_argument("--today")
    ap.add_argument("--data-dir", default=str(DATA_DIR))
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ap.add_argument("--config-dir", default=str(CONFIG_DIR))
    ap.add_argument("--case", help="afișează doar acest caz")
    ap.add_argument("--top", type=int, default=5)
    a = ap.parse_args(argv)

    t0 = time.perf_counter()
    pf, cfg, res = run_pipeline(a.data_dir, a.out_dir, a.config_dir, a.today)
    checks = run_all_checks(pf, load_mocks(a.data_dir), cfg, res)
    offers = build_offers(pf, cfg, res, checks)
    write_json(Path(a.out_dir) / "offers.json", offers)
    dt = time.perf_counter() - t0

    for o in ([o for o in offers if o["case_id"] == a.case] if a.case else offers[:a.top]):
        print_offer(o)
    cnt = Counter(o["interventie_aleasa"] or "— (blocat)" for o in offers)
    cost = sum(o["cost"] for o in offers if o["interventie_aleasa"])
    print(f"\nRetenție: {len(offers)} cazuri în {dt:.2f}s → {a.out_dir}/offers.json")
    print("  intervenții alese: " + ", ".join(f"{k}={v}" for k, v in cnt.most_common()))
    print(f"  cost total propus: {fmt_ron(cost)} RON · cazuri fără cheltuială: "
          f"{sum(1 for o in offers if o['interventie_aleasa'] in ('nu_interveni', None))}/{len(offers)}")
    log_event(a.out_dir, "retention", "done", cazuri=len(offers), cost_total=round(cost, 2), secunde=round(dt, 3))


if __name__ == "__main__":
    main()
