"""Familia RISC_CREDIT — probabilitatea de neplată. Agregare la nivel de client: max(semnale)."""
from __future__ import annotations

from ..common import fmt_ron, parse_date, years_between
from . import ZERO, Context, SignalResult, signal, step_score
from .plecare import _venit_lipsa, venit_mutat_confirmat
from .util import ltv


@signal("intarziere_noua", familie="risc_credit", nivel="credit")
def intarziere_noua(ctx: Context) -> SignalResult:
    p = ctx.params
    hist = ctx.payments.get(ctx.loan["loan_id"], [])
    if not hist:
        return ZERO
    last = hist[-1]
    prev_zile = hist[-2]["zile_intarziere"] if len(hist) > 1 else 0
    zile = last["zile_intarziere"]
    if zile <= 0:
        return ZERO
    grav = zile > p["prag_grav_zile"]
    if prev_zile > 0 and not grav:
        return ZERO                       # întârziere veche, nu nouă
    scor = p["scor_grav"] if grav else p["scor"]
    return SignalResult(scor, f"{zile} zile întârziere în {last['luna']} (luna anterioară: {prev_zile}), "
                              f"restanță {fmt_ron(last['suma_restanta'])} RON",
                        {"zile": zile, "luna": last["luna"], "suma": fmt_ron(last["suma_restanta"])})


@signal("venit_in_scadere", familie="risc_credit", nivel="client")
def venit_in_scadere(ctx: Context) -> SignalResult:
    p, fl = ctx.params, ctx.flows
    k = p["luni_recente"]
    recente = [fl.venit_lunar[m] for m in fl.months[-k:] if fl.venit_lunar[m] > 0]
    anterioare = [fl.venit_lunar[m] for m in fl.months[:-k] if fl.venit_lunar[m] > 0]
    if not recente or len(anterioare) < p["min_luni_anterioare"]:
        return ZERO                       # lipsa totală a venitului e tratată de venit_disparut
    m_rec, m_ant = sum(recente) / len(recente), sum(anterioare) / len(anterioare)
    raport = m_rec / m_ant
    scor = step_score(raport, p["trepte_raport"])
    if scor <= 0:
        return ZERO
    return SignalResult(scor, f"media ultimelor {k} luni {fmt_ron(m_rec)} RON vs {fmt_ron(m_ant)} RON în lunile "
                              f"anterioare ({raport:.0%})",
                        {"procent": f"{raport * 100:.0f}", "medie_recenta": fmt_ron(m_rec),
                         "medie_anterioara": fmt_ron(m_ant)})


@signal("venit_disparut", familie="risc_credit", nivel="client")
def venit_disparut(ctx: Context) -> SignalResult:
    d = _venit_lipsa(ctx)
    if not d or venit_mutat_confirmat(ctx)[0]:      # salariul s-a mutat, clientul plătește în continuare
        return ZERO
    return SignalResult(ctx.params["scor"], f"nicio încasare de venit în ultimele {d['luni_lipsa']} luni; "
                                            f"ultima {d['ultima_data']} ({d['sursa']})", d)


@signal("card_stres", familie="risc_credit", nivel="credit")
def card_stres(ctx: Context) -> SignalResult:
    p, loan = ctx.params, ctx.loan
    if loan["produs"] != "card_credit" or loan.get("utilizare_limita") is None:
        return ZERO
    k = p["luni_plata_minima"]
    hist = ctx.payments.get(loan["loan_id"], [])[-k:]
    if loan["utilizare_limita"] < p["utilizare_min"] or len(hist) < k or not all(h["plata_minima_card"] for h in hist):
        return ZERO
    util = round(loan["utilizare_limita"] * 100)
    return SignalResult(p["scor"], f"utilizare {util}% din limita de {fmt_ron(loan['limita'])} RON; "
                                   f"plata minimă {k} luni la rând ({hist[0]['luna']}–{hist[-1]['luna']})",
                        {"utilizare": util, "luni": k})


@signal("angajator_in_dificultate", familie="risc_credit", nivel="client")
def angajator_in_dificultate(ctx: Context) -> SignalResult:
    p, e = ctx.params, ctx.employer
    if not e:
        return ZERO
    if e["status"] in p["statusuri_grave"]:
        return SignalResult(1.0, f"{e['nume']}: status {e['status']}", {"angajator": e["nume"], "status": e["status"]})
    if e["trend_plati_salarii_3l"] <= p["prag_trend"]:
        return SignalResult(p["scor_trend"], f"{e['nume']}: plăți salarii {e['trend_plati_salarii_3l']:+.0%} în 3 luni",
                            {"angajator": e["nume"], "status": f"scădere {e['trend_plati_salarii_3l']:+.0%} a plăților"})
    return ZERO


@signal("restructurare_anterioara", familie="risc_credit", nivel="credit")
def restructurare_anterioara(ctx: Context) -> SignalResult:
    loan = ctx.loan
    if not loan.get("restructurat_anterior"):
        return ZERO
    data = loan["restructurari"][0]["data"] if loan.get("restructurari") else "dată necunoscută"
    return SignalResult(ctx.params["scor"], f"restructurat la {data}", {"data": data})


@signal("poprire_activa", familie="risc_credit", nivel="client")
def poprire_activa(ctx: Context) -> SignalResult:
    p, fl = ctx.params, ctx.flows
    recente = set(fl.months[-p["luni"]:])
    active = [f for f in fl.popriri if recente & set(f.luni)]
    if not active:
        return ZERO
    f = active[0]
    return SignalResult(p["scor"], f"{fmt_ron(f.suma_totala)} RON reținuți către {f.contraparte} "
                                   f"({', '.join(f.luni)})", {"suma": fmt_ron(f.suma_totala), "beneficiar": f.contraparte})


@signal("ltv_depasit", familie="risc_credit", nivel="credit")
def ltv_depasit(ctx: Context) -> SignalResult:
    p, loan = ctx.params, ctx.loan
    v = ltv(loan)
    if v is None or v <= p["prag_ltv"]:
        return ZERO
    data_eval = parse_date(loan["garantie"]["data_evaluare"])
    vechime = years_between(data_eval, ctx.today)
    scor = p["scor"] + (p["bonus_evaluare_veche"] if vechime > p["ani_evaluare_veche"] else 0)
    return SignalResult(min(1.0, scor), f"LTV {v:.2f} (sold {fmt_ron(loan['sold_ramas'])} / evaluare "
                                        f"{fmt_ron(loan['garantie']['valoare_evaluare'])} din {data_eval.isoformat()})",
                        {"ltv": f"{v:.2f}", "data_evaluare": data_eval.isoformat()})


@signal("expunere_valutara", familie="risc_credit", nivel="client")
def expunere_valutara(ctx: Context) -> SignalResult:
    """Ratele creditelor în valută (exprimate în RON, vezi scan.normalizeaza_valuta) depășesc pragul din venit."""
    p, fl = ctx.params, ctx.flows
    rate_valuta = sum(l["rata_lunara"] or 0 for l in ctx.loans if l.get("moneda", "RON") != "RON")
    if rate_valuta <= 0:
        return ZERO
    luni = fl.months[-p["luni_venit"]:]
    venit = sum(fl.venit_lunar[m] for m in luni) / len(luni)
    if venit <= 0:
        return SignalResult(p["scor"], f"rate în valută {fmt_ron(rate_valuta)} RON/lună, fără venit observat",
                            {"procent": "n/a", "rate_valuta": fmt_ron(rate_valuta)})
    pondere = rate_valuta / venit
    if pondere <= p["prag_din_venit"]:
        return ZERO
    monede = sorted({l["moneda"] for l in ctx.loans if l.get("moneda", "RON") != "RON"})
    return SignalResult(p["scor"], f"ratele în {'/'.join(monede)} ({fmt_ron(rate_valuta)} RON/lună la cursul curent) sunt "
                                   f"{pondere:.0%} din venit, peste {p['prag_din_venit']:.0%} (DTI valută)",
                        {"procent": f"{pondere * 100:.0f}", "rate_valuta": fmt_ron(rate_valuta)})


@signal("codebitor_cu_risc", familie="risc_credit", nivel="client")
def codebitor_cu_risc(ctx: Context) -> SignalResult:
    """Clientul e codebitor pe un credit al altcuiva care are întârziere: răspunde solidar, riscul e și al lui."""
    p = ctx.params
    for l in ctx.codebitor_la:
        hist = ctx.payments.get(l["loan_id"], [])
        if hist and hist[-1]["zile_intarziere"] >= p["zile_min"]:
            h = hist[-1]
            return SignalResult(p["scor"], f"codebitor pe {l['loan_id']} ({l['client_id']}, {l['produs']}): {h['zile_intarziere']} zile "
                                           f"întârziere în {h['luna']}, restanță {fmt_ron(h['suma_restanta'])} RON",
                                {"credit": l["loan_id"], "debitor": l["client_id"], "zile": h["zile_intarziere"]})
    return ZERO
