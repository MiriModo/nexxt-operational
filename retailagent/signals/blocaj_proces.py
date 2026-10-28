"""Familia BLOCAJ_PROCES — oprește orice alt flux până se rezolvă."""
from __future__ import annotations

from datetime import timedelta

from ..common import parse_date
from . import ZERO, Context, SignalResult, signal


@signal("ci_expirata", familie="blocaj_proces", nivel="client")
def ci_expirata(ctx: Context) -> SignalResult:
    p = ctx.params
    exp = parse_date(ctx.client.get("ci_expira_la"))
    if exp is None:
        return SignalResult(1.0, "data expirării CI lipsește", {"data": "necunoscută"})
    if exp < ctx.today:
        return SignalResult(1.0, f"CI expirată la {exp.isoformat()}", {"data": exp.isoformat()})
    if exp < ctx.today + timedelta(days=p["zile_avertizare"]):
        return SignalResult(p["scor_avertizare"], f"CI expiră la {exp.isoformat()}", {"data": exp.isoformat()})
    return ZERO


@signal("kyc_vechi", familie="blocaj_proces", nivel="client")
def kyc_vechi(ctx: Context) -> SignalResult:
    d = parse_date(ctx.client.get("kyc_actualizat_la"))
    if d is None:
        return SignalResult(1.0, "KYC fără dată de actualizare", {"data": "necunoscută", "luni": "?"})
    luni = (ctx.today.year - d.year) * 12 + (ctx.today.month - d.month) - (ctx.today.day < d.day)
    if luni <= ctx.params["luni_max"]:
        return ZERO
    return SignalResult(1.0, f"KYC actualizat ultima dată la {d.isoformat()} ({luni} luni)",
                        {"data": d.isoformat(), "luni": luni})


@signal("consimtamant_lipsa", familie="blocaj_proces", nivel="client")
def consimtamant_lipsa(ctx: Context) -> SignalResult:
    c = ctx.client
    lipsa = [n for n, k in (("ANAF", "consimtamant_anaf"), ("Biroul de Credit", "consimtamant_biroul_credit"))
             if not c.get(k)]
    if not lipsa:
        return ZERO
    txt = " și ".join(lipsa)
    return SignalResult(1.0, f"lipsește acordul {txt}", {"lipsa": txt})


@signal("asigurare_expirata", familie="blocaj_proces", nivel="credit")
def asigurare_expirata(ctx: Context) -> SignalResult:
    g = ctx.loan.get("garantie")
    if not g or not g.get("asigurare_expira_la"):
        return ZERO
    exp = parse_date(g["asigurare_expira_la"])
    if exp >= ctx.today + timedelta(days=ctx.params["zile"]):
        return ZERO
    verb = "a expirat" if exp < ctx.today else "expiră"
    return SignalResult(1.0, f"polița garanției {verb} la {exp.isoformat()}", {"data": exp.isoformat()})


@signal("flag_blocant", familie="blocaj_proces", nivel="client")
def flag_blocant(ctx: Context) -> SignalResult:
    c = ctx.client
    flags = [n for n, k in (("PEP", "flag_pep"), ("fraudă internă", "flag_frauda_interna"), ("decedat", "flag_decedat"))
             if c.get(k)]
    if not flags:
        return ZERO
    txt = ", ".join(flags)
    return SignalResult(1.0, f"client marcat {txt} — escaladare, fără ofertă", {"flag": txt})
