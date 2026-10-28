"""Familia PLECARE — probabilitatea ca clientul să se refinanțeze în altă parte."""
from __future__ import annotations

from ..common import fmt_ron, parse_date, plural, years_between
from . import ZERO, Context, SignalResult, signal, step_score
from .util import ani_ramasi, cereri_pe_credit, dobanda_post_expirare, ltv, rata_relevanta


@signal("expirare_dobanda_fixa", familie="plecare", nivel="credit")
def expirare_dobanda_fixa(ctx: Context) -> SignalResult:
    loan = ctx.loan
    exp = parse_date(loan.get("dobanda_fixa_expira_la"))
    if loan["tip_dobanda"] != "fixa" or exp is None:
        return ZERO
    zile = (exp - ctx.today).days
    if zile < 0:
        return ZERO
    scor = step_score(zile, ctx.params["trepte_zile"])
    post = dobanda_post_expirare(loan, ctx.market)
    dupa = f"IRCC {ctx.market['ircc']:.2f} + {loan['marja']:.2f} = {post:.2f}%" if post is not None else "n/a"
    return SignalResult(scor, f"expiră {exp.isoformat()} (în {zile} zile); după: {dupa}",
                        {"zile": zile, "data": exp.isoformat(), "dobanda_dupa": post})


@signal("gap_piata_bani", familie="plecare", nivel="credit")
def gap_piata_bani(ctx: Context) -> SignalResult:
    p, loan = ctx.params, ctx.loan
    piata = ctx.market[p["piata_produs"][loan["produs"]]]
    rata, sursa = rata_relevanta(loan, ctx.market, ctx.today, p["fereastra_post_expirare_zile"])
    gap_pp = rata - piata
    ani = ani_ramasi(loan, ctx.today)
    economie = max(0.0, gap_pp) / 100 * loan["sold_ramas"] * ani
    scor = min(1.0, economie / p["prag_economie_ron"])
    det = {"gap_pp": round(gap_pp, 2), "economie": round(economie), "economie_txt": fmt_ron(economie),
           "rata_relevanta": rata, "sursa_rata": sursa, "piata": piata, "ani": round(ani, 1)}
    if scor <= 0:
        return SignalResult(0.0, "", det)
    eticheta = "după expirare" if sursa == "post_expirare" else "acum"
    return SignalResult(scor, f"ar economisi ~{fmt_ron(economie)} RON în {plural(ani, 'an', 'ani')} la {piata:.2f}% "
                              f"({eticheta} plătește {rata:.2f}%, gap {gap_pp:.2f} pp)", det)


@signal("cerere_adeverinta_sold", familie="plecare", nivel="credit")
def cerere_adeverinta_sold(ctx: Context) -> SignalResult:
    p = ctx.params
    cereri = cereri_pe_credit(ctx.requests, ctx.loan, p["tipuri"], p["zile"], ctx.today)
    if not cereri:
        return ZERO
    r = cereri[0]
    tip = r["tip"].replace("_", " ")
    return SignalResult(1.0, f"cerere {tip} din {r['data']} ({r['request_id']})",
                        {"data": r["data"], "request_id": r["request_id"], "tip_cerere": tip})


@signal("rata_alt_creditor", familie="plecare", nivel="client")
def rata_alt_creditor(ctx: Context) -> SignalResult:
    p, months = ctx.params, ctx.flows.months
    best = ZERO
    for f in ctx.flows.creditori:
        nou = f.luni[0] in months[-p["luni_nou"]:]
        scor = p["scor_nou"] if nou else p["scor_recurent"]
        if scor > best.scor:
            best = SignalResult(scor, f"{f.contraparte}, ~{fmt_ron(f.suma_medie)} RON/lună, {len(f.luni)} luni "
                                      f"(din {f.luni[0]}{', început recent' if nou else ''})",
                                {"beneficiar": f.contraparte, "suma": fmt_ron(f.suma_medie), "prima_luna": f.luni[0],
                                 "luni": len(f.luni)})
    return best


def _venit_lipsa(ctx: Context) -> dict | None:
    """Venit (salariu/pensie) existent istoric, dar lipsă în ultimele `luni_lipsa` luni."""
    p, fl = ctx.params, ctx.flows
    k = p["luni_lipsa"]
    if not fl.surse_venit:
        return None
    recente = fl.months[-k:]
    if any(fl.venit_lunar[m] > 0 for m in recente):
        return None
    istoric = [m for m in fl.months[:-k] if fl.venit_lunar[m] > 0]
    if len(istoric) < p["min_luni_istoric"]:
        return None
    ultima = max(f.ultima_data for f in fl.surse_venit)
    sursa = max(fl.surse_venit, key=lambda f: f.ultima_data).contraparte
    return {"luni_lipsa": k, "ultima_data": ultima, "sursa": sursa}


def _acoperire_transferuri_proprii(ctx: Context) -> tuple[float, float]:
    """(media lunară a transferurilor din conturile proprii ale clientului, ratele lunare la noi) pe lunile fără venit.

    Un transfer propriu are numele clientului ca plătitor: banii vin din contul lui de la altă bancă.
    """
    luni = set(ctx.flows.months[-ctx.params["luni_lipsa"]:])
    nume = " ".join(ctx.client["nume"].upper().split())
    total = sum(t["suma"] for t in ctx.transactions
                if t["directie"] == "in" and t["data"][:7] in luni
                and nume in " ".join(t["platitor_beneficiar"].upper().split()))
    rate = sum(l["rata_lunara"] or 0 for l in ctx.loans)
    return total / len(luni), rate


def venit_mutat_confirmat(ctx: Context) -> tuple[bool, float, float]:
    """Venitul lipsește, dar ratele sunt acoperite din transferuri proprii → salariul e la altă bancă, nu pierdut."""
    medie, rate = _acoperire_transferuri_proprii(ctx)
    return rate > 0 and medie >= ctx.params["acoperire_min"] * rate, medie, rate


@signal("salariu_mutat", familie="plecare", nivel="client")
def salariu_mutat(ctx: Context) -> SignalResult:
    d = _venit_lipsa(ctx)
    if not d:
        return ZERO
    ok, medie, rate = venit_mutat_confirmat(ctx)
    dovada = f"ultima încasare {d['ultima_data']} de la {d['sursa']}; lipsă în ultimele {d['luni_lipsa']} luni"
    if ok:
        return SignalResult(ctx.params["scor_confirmat"], dovada + f"; ratele ({fmt_ron(rate)} RON/lună) sunt "
                            f"acoperite din transferuri proprii de la altă bancă ({fmt_ron(medie)} RON/lună)",
                            {**d, "transfer_propriu": fmt_ron(medie),
                             "nota": "; ratele le plătește prin transfer de la altă bancă"})
    return SignalResult(ctx.params["scor"], dovada, {**d, "nota": ""})


@signal("eligibilitate_externa", familie="plecare", nivel="credit")
def eligibilitate_externa(ctx: Context) -> SignalResult:
    p, loan = ctx.params, ctx.loan
    hist = ctx.payments.get(loan["loan_id"], [])
    if any(h["zile_intarziere"] > 0 for h in hist):
        return ZERO
    scor, comp = 1.0, [f"istoric curat {len(hist)} luni"]
    v = ltv(loan)
    if v is not None:
        if v >= p["ltv_max"]:
            scor *= p["factor_ltv_mare"]
        comp.append(f"LTV {v:.2f}")
    if loan.get("restructurat_anterior"):
        scor *= p["factor_restructurat"]
        comp.append("restructurat anterior")
    else:
        comp.append("fără restructurare")
    txt = ", ".join(comp)
    return SignalResult(scor, txt, {"componente": txt})


@signal("vechime_credit", familie="plecare", nivel="credit")
def vechime_credit(ctx: Context) -> SignalResult:
    loan = ctx.loan
    if loan["tip_dobanda"] != "variabila":
        return ZERO
    ani = years_between(parse_date(loan["data_acordare"]), ctx.today)
    scor = step_score(ani, ctx.params["trepte_ani"], descending=True)
    if scor <= 0:
        return ZERO
    return SignalResult(scor, f"acordat {loan['data_acordare']} ({ani:.1f} ani), dobândă variabilă",
                        {"ani": f"{ani:.0f}"})


@signal("sold_ramas", familie="plecare", nivel="credit")
def sold_ramas(ctx: Context) -> SignalResult:
    loan = ctx.loan
    if loan["produs"] == "card_credit" or not loan.get("suma_initiala"):
        return ZERO
    ani = ani_ramasi(loan, ctx.today)
    if ani < ctx.params["ani_min"]:
        return ZERO
    scor = min(1.0, loan["sold_ramas"] / loan["suma_initiala"])
    return SignalResult(scor, f"sold {fmt_ron(loan['sold_ramas'])} RON din {fmt_ron(loan['suma_initiala'])}, "
                              f"{plural(ani, 'an rămas', 'ani rămași')}",
                        {"sold": fmt_ron(loan["sold_ramas"]), "ani": plural(ani, "an", "ani")})


@signal("simulare_in_app", familie="plecare", nivel="credit")
def simulare_in_app(ctx: Context) -> SignalResult:
    p = ctx.params
    cereri = cereri_pe_credit(ctx.requests, ctx.loan, p["tipuri"], p["zile"], ctx.today)
    if not cereri:
        return ZERO
    r = cereri[0]
    return SignalResult(p["scor"], f"simulare rambursare anticipată pe {r['data']} ({r['request_id']})",
                        {"data": r["data"], "request_id": r["request_id"]})
