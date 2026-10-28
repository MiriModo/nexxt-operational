"""Meniul de intervenții, constrângerile și optimizarea (MODEL_FINAL §3).

Pentru fiecare intervenție din config/retention.yaml se calculează, pe graficul de rambursare al creditului:
costul pentru bancă, câștigul clientului (B_după) și probabilitatea de plecare după (p_după). Constrângerile
(BNR + plafoane interne, din config/constraints.yaml și priority.yaml → buget_retentie_pp) elimină opțiunile
ÎNAINTE de optimizare. Se alege intervenția cu cost minim pentru care `p_după ≤ p_tinta` și `cost ≤ p_înainte × V`.
Dacă nu există: `informare` (dacă p_înainte ≥ p_tinta) sau `nu_interveni`. Risc de credit ≥ prag → doar
restructurare. Blocaj activ → nicio intervenție.
"""
from __future__ import annotations

from datetime import date

from .common import fmt_ron
from .config_loader import Config, InterventieCfg
from .finance import dobanda_perioada, dobanda_totala, luni_ramase, segmente_credit, varsta_la
from .retention import castig_plecare, legaturi, semnale_active, valoare_client

OFERTA = ("comision", "reducere_marja", "fix_piata", "pachet")     # tipuri care sunt o ofertă comercială


def _orizont(loan: dict, today: date, cfg: Config) -> int:
    return min(luni_ramase(loan, today), round(cfg.retention.orizont_ani * 12))


def _cost_si_castig(loan: dict, seg_nou: list[tuple[int, float]], today: date, market: dict, cfg: Config) -> tuple[float, float]:
    """(costul băncii pe toată durata, câștigul clientului în orizontul de decizie) pentru un scenariu nou de dobânzi."""
    seg = segmente_credit(loan, today, market)
    sold = loan["sold_ramas"]
    cost = max(0.0, dobanda_totala(sold, seg) - dobanda_totala(sold, seg_nou))
    k = _orizont(loan, today, cfg)
    castig = max(0.0, dobanda_perioada(sold, seg, k) - dobanda_perioada(sold, seg_nou, k))
    return cost, castig


def _reducere(loan: dict, today: date, market: dict, cfg: Config, pp: float) -> tuple[float, float]:
    """Reducere de marjă `pp` pe toată durata rămasă."""
    seg_red = [(l, max(0.0, r - pp)) for l, r in segmente_credit(loan, today, market)]
    return _cost_si_castig(loan, seg_red, today, market, cfg)


def _fix_piata(loan: dict, today: date, market: dict, cfg: Config, ani: int, cheie: str) -> tuple[float, float, float] | None:
    """Nouă perioadă fixă de `ani` la dobânda pieței, apoi IRCC + marjă → (cost, câștig client, dobânda fixă)."""
    rates = market["dobanzi_piata"].get(loan["produs"], {})
    if cheie not in rates or loan.get("marja") is None:
        return None
    luni = luni_ramase(loan, today)
    fix = float(rates[cheie])
    post = round(market["ircc"] + loan["marja"], 2)
    k = min(luni, ani * 12)
    seg_nou = [(k, fix)] + ([(luni - k, post)] if luni > k else [])
    cost, castig = _cost_si_castig(loan, seg_nou, today, market, cfg)
    return cost, castig, fix


def _fezabilitate(it: InterventieCfg, loan: dict | None, client: dict, concluzii: dict, risc: float, leg: dict,
                  today: date, market: dict, cfg: Config) -> str | None:
    """None dacă intervenția e fezabilă, altfel motivul (prima constrângere încălcată)."""
    C, R, P = cfg.constraints, cfg.retention, cfg.priority
    risc_activ = risc >= P.risc_credit.blocheaza_retentia_daca
    for cond in it.necesita:
        if cond == "salariu_la_alta_banca" and not concluzii.get("salariu_la_alta_banca"):
            return "salariul e deja la noi (sau nu e confirmat la altă bancă)"
        if cond == "risc" and not risc_activ:
            return "doar pentru clienți cu risc de credit activ"
        if cond == "fara_risc" and risc_activ:
            return "risc de credit activ"
    if it.tip == "nimic":
        return None
    if risc_activ and it.tip != "restructurare":
        return f"risc de credit {risc:.2f} ≥ {P.risc_credit.blocheaza_retentia_daca:.2f}: nicio ofertă de retenție, traseu de restructurare"
    if it.tip == "restructurare":
        if loan is None:
            return "fără credit existent"
        if it.id == "ajustare_maturitate":
            from .common import parse_date, shift_month
            scad = parse_date(loan["data_scadenta"])
            noua = shift_month(f"{scad.year:04d}-{scad.month:02d}", C.restructurare.prelungire_maxima_luni)
            varsta = varsta_la(client["data_nasterii"], date(int(noua[:4]), int(noua[5:7]), 1))
            if varsta > C.varsta.max_la_scadenta:
                return f"vârsta la noua scadență {varsta:.0f} > {C.varsta.max_la_scadenta} ani"
        return None
    if it.tip == "informare":
        return None
    # de aici: oferte comerciale
    if loan is None:
        return "fără credit existent: nu există ce renegocia"
    if it.tip != "pachet" and not leg["suficiente_pentru_oferta"]:
        return (f"legături insuficiente cu banca ({leg['scor']:.2f} < {R.legaturi.min_pentru_oferta:.2f}): "
                "doar informare sau ofertă condiționată de aducerea salariului")
    if it.tip == "pachet" and leg["scor"] < R.legaturi.min_pentru_pachet:
        return (f"aproape nicio legătură cu banca ({leg['scor']:.2f} < {R.legaturi.min_pentru_pachet:.2f}): "
                "nici pachetul cu salariul nu se justifică, doar informare")
    if it.tip in ("reducere_marja", "pachet"):
        if loan.get("marja") is None:
            return "produsul nu are marjă negociabilă"
        buget = P.buget_retentie_pp.get(client.get("nivel_relatie", "standard"), 0.0)
        if it.reducere_pp > buget + 1e-9:
            return f"reducerea {it.reducere_pp:.1f} pp depășește bugetul de retenție {buget:.1f} pp pentru nivelul {client.get('nivel_relatie')}"
        if loan["marja"] - it.reducere_pp < C.marja_minima_pp - 1e-9:
            return f"marja ar coborî la {loan['marja'] - it.reducere_pp:.2f} pp, sub minimul {C.marja_minima_pp:.1f} pp"
    if it.tip == "fix_piata":
        if loan.get("marja") is None or it.cheie_piata not in market["dobanzi_piata"].get(loan["produs"], {}):
            return f"produsul {loan['produs']} nu are dobândă de piață pentru {it.cheie_piata}"
        if luni_ramase(loan, today) < 12:
            return "sub un an rămas: nu are sens o nouă perioadă fixă"
    dti = concluzii.get("dti_curent")
    if it.tip == "pachet" and dti is not None and dti > C.dti.max:
        return f"DTI {dti:.0%} peste {C.dti.max:.0%}: pachetul nu se poate oferi"
    return None


def evalueaza_interventii(loan: dict | None, client: dict, transactions: list[dict], semnale: list[dict], concluzii: dict,
                          risc: float, blocat: bool, today: date, market: dict, cfg: Config) -> dict:
    R = cfg.retention
    leg = legaturi(client, transactions, bool(concluzii.get("salariu_la_alta_banca")), today, cfg)
    n_act, lista_act = semnale_active(semnale, concluzii, cfg)
    if loan is not None:
        B = castig_plecare(loan, today, market, cfg, concluzii.get("cost_mutare"))
        V = valoare_client(loan, client, today, market, cfg)
    else:
        B = {"B": 0.0, "B_brut": 0.0, "dobanda_la_noi": 0.0, "dobanda_piata": 0.0, "dobanda_pct_piata": None, "cost_mutare": 0.0, "luni_ramase": 0}
        V = {"V": 0.0, "venit_marja": 0.0, "produse": 0.0, "ani_ramasi": 0.0}
    # p din modelul de churn ales (sigmoid sau antrenat); feature-urile sunt aceleași ca la antrenare
    from .churn.features import features
    from .churn.model import get_model, sigmoid
    model = get_model(cfg)
    x0 = features(B["B"], leg, lista_act, client, loan, concluzii, today, cfg, B.get("luni_ramase"))
    p0 = sigmoid(model.predict_logit(x0))

    rows = []
    xs_dupa: list[dict] = []
    for it in R.interventii:
        motiv = "cazul e blocat de un task de proces" if blocat else \
            _fezabilitate(it, loan, client, concluzii, risc, leg, today, market, cfg)
        cost, castig_client, detalii = it.cost_fix, 0.0, {}
        if loan is not None and it.tip in ("reducere_marja", "pachet") and loan.get("marja") is not None:
            c, castig_client = _reducere(loan, today, market, cfg, it.reducere_pp)
            cost += c
            detalii = {"marja_noua": round(loan["marja"] - it.reducere_pp, 2)}
        elif loan is not None and it.tip == "fix_piata":
            r = _fix_piata(loan, today, market, cfg, it.ani, it.cheie_piata)
            if r:
                cost += r[0]
                castig_client = r[1]
                detalii = {"dobanda_fixa_noua": r[2], "ani": it.ani}
        elif it.tip == "comision":
            castig_client = it.cost_fix
        B_dupa = max(0.0, B["B"] - castig_client)
        leg_dupa = {**leg, "scor": min(1.0, leg["scor"] + it.efect_legaturi)}
        xs_dupa.append(features(B_dupa, leg_dupa, lista_act, client, loan, concluzii, today, cfg, B.get("luni_ramase")))
        rows.append({"id": it.id, "tip": it.tip, "eticheta": it.eticheta, "fezabil": motiv is None, "motiv_infezabil": motiv,
                     "cost": round(cost, 2), "castig_client": round(castig_client, 2), "B_dupa": round(B_dupa, 2),
                     "p_dupa": None, "respecta_tinta": None, "merita": cost <= p0 * V["V"], "detalii": detalii,
                     "efect_scor": it.efect_scor})
    for r, lg in zip(rows, model.predict_logit_batch(xs_dupa)):        # un singur apel la model pentru tot meniul
        p_dupa = sigmoid(lg + r.pop("efect_scor"))
        r["p_dupa"], r["respecta_tinta"] = round(p_dupa, 4), p_dupa <= R.p_tinta

    aleasa, motiv_alegere = alege_interventie(rows, p0, risc, blocat, cfg)
    alternative = sorted((r for r in rows if r["fezabil"] and r["respecta_tinta"] and r["id"] != aleasa and r["tip"] != "nimic"),
                         key=lambda r: r["cost"])[:3]
    return {"B": B, "V": V["V"], "valoare": V, "legaturi": leg, "semnale_active": lista_act, "p_inainte": round(p0, 4),
            "p_tinta": R.p_tinta, "interventii": rows, "aleasa": aleasa, "motiv_alegere": motiv_alegere,
            "alternative": [a["id"] for a in alternative], "features": x0,
            "model_churn": {"nume": model.nume, "versiune": model.versiune}}


def alege_interventie(rows: list[dict], p0: float, risc: float, blocat: bool, cfg: Config) -> tuple[str | None, str]:
    R, P = cfg.retention, cfg.priority
    if blocat:
        return None, "cazul e blocat de un task de proces: nicio intervenție până la rezolvare"
    by_id = {r["id"]: r for r in rows}
    if risc >= P.risc_credit.blocheaza_retentia_daca:
        cand = [r for r in rows if r["tip"] == "restructurare" and r["fezabil"]]
        if not cand:
            return None, "risc de credit activ, dar nicio restructurare fezabilă: escaladare"
        best = min(cand, key=lambda r: r["cost"])
        return best["id"], f"risc de credit {risc:.2f}: fără ofertă de retenție; restructurarea cu costul minim"
    cand = [r for r in rows if r["fezabil"] and r["respecta_tinta"] and r["merita"]]
    if cand:
        best = min(cand, key=lambda r: r["cost"])
        if best["tip"] == "nimic":
            return best["id"], f"p = {p0:.0%} ≤ țintă {R.p_tinta:.0%}: clientul e deja păstrat, nu cheltuim nimic"
        return best["id"], (f"cea mai ieftină intervenție care aduce p sub {R.p_tinta:.0%} "
                            f"({best['p_dupa']:.0%}) și costă {fmt_ron(best['cost'])} RON ≤ p×V")
    inf = by_id.get("informare")
    if p0 >= R.p_tinta and inf and inf["fezabil"]:
        return "informare", (f"nicio intervenție nu aduce p sub {R.p_tinta:.0%} la un cost ≤ p×V: "
                             "doar informare + simulare personalizată")
    return "nu_interveni", f"nicio intervenție nu merită (p = {p0:.0%}); nu interveni"


def evalueaza_caz(pf, cfg: Config, case: dict, ci, check_result: dict) -> dict:
    """Evaluarea completă a unui caz din coadă, cu concluziile verificărilor."""
    risc = case["scoruri"]["risc_credit"]
    ev = evalueaza_interventii(ci.loan, ci.client, pf.tx_by_client.get(case["client_id"], []), ci.semnale,
                               check_result.get("concluzii", {}), risc, bool(case["blocaje"]), pf.today, pf.market, cfg)
    return {"case_id": case["case_id"], "client_id": case["client_id"], "loan_id": case["loan_id"], "produs": case["produs"],
            "nivel_relatie": ci.client.get("nivel_relatie"), "risc_credit": risc, "blocat": bool(case["blocaje"]), **ev}
