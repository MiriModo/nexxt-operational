"""Execuția verificărilor în trepte (MODEL_FINAL §2): intern → anaf → biroul_credit → crc → garantie.

Fiecare verificare e o funcție pură `(CheckContext, parametri) -> CheckResult`, înregistrată cu `@check(id)`;
id-ul trebuie să existe în config/checks.yaml. Verificările scriu concluzii în `ctx.concluzii` (venit, DTI,
LTV, interogări BC, salariu la altă bancă...), pe care le folosesc verificările următoare și modelul de
retenție. Sursele externe sunt mock-uri locale (data/externe/*.json).

    python -m retailagent.checks        # out/checks.json (CLI-ul e în checks.py)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable

from .common import DATA_DIR, fmt_ron, last_months, parse_date, read_json
from .config_loader import Config
from .finance import (comision_rambursare_anticipata, cost_mutare_total, dobanda_totala, dti, luni_ramase, rata_anuitate,
                      segmente_credit, varsta_la)
from .signals.util import ltv as ltv_dosar

ELIGIBILITATE = ("credit_nou", "majorare_limita_card", "refinantare")


@dataclass
class Mocks:
    """Răspunsurile simulate ale surselor externe + dosarul clientului (data/externe/*, conturi, documente)."""
    anaf: dict[str, dict]
    bc: dict[str, dict]
    crc: dict[str, dict]
    garantii: dict[str, dict]          # loan_id -> garanție
    conturi: dict[str, dict]
    documente: dict[str, list[dict]]


def load_mocks(data_dir: Path | str = DATA_DIR) -> Mocks:
    d = Path(data_dir)
    ext = d / "externe"

    def by(rows, k="client_id"):
        return {r[k]: r for r in rows}

    return Mocks(by(read_json(ext / "anaf.json")), by(read_json(ext / "biroul_credit.json")),
                 by(read_json(ext / "crc.json")), by(read_json(ext / "garantii.json"), "loan_id"),
                 by(read_json(d / "conturi.json")),
                 {r["client_id"]: r["documente"] for r in read_json(d / "documente.json")})


@dataclass
class CheckContext:
    today: date
    client: dict
    loan: dict | None
    loans: list[dict]                   # creditele clientului
    codebitor_la: list[dict]            # creditele altora pe care clientul e codebitor
    cereri: list[dict]
    motive: list[str]
    market: dict
    flows: Any                          # signals.inflows.Flows
    transactions: list[dict]
    payments: dict[str, list[dict]]
    mocks: Mocks
    cfg: Config
    concluzii: dict[str, Any] = field(default_factory=dict)


@dataclass
class CheckResult:
    status: str                         # ok | avertizare | fail
    dovada: str
    detalii: dict = field(default_factory=dict)
    sursa: str = "intern"


CheckFn = Callable[[CheckContext, dict], CheckResult]
CHECKS: dict[str, CheckFn] = {}


def check(cid: str) -> Callable[[CheckFn], CheckFn]:
    def deco(fn: CheckFn) -> CheckFn:
        CHECKS[cid] = fn
        return fn
    return deco


def _secured(ctx: CheckContext) -> dict | None:
    if ctx.loan and ctx.loan.get("garantie"):
        return ctx.loan
    return next((l for l in ctx.loans if l.get("garantie")), None)


def _loan_or_first(ctx: CheckContext) -> dict | None:
    return ctx.loan or (ctx.loans[0] if ctx.loans else None)


# ---------------------------------------------------------------- strat de bază

@check("identitate_kyc")
def identitate_kyc(ctx: CheckContext, p: dict) -> CheckResult:
    c, probleme, avert = ctx.client, [], []
    ci = parse_date(c["ci_expira_la"])
    if ci < ctx.today:
        probleme.append(f"CI expirată la {ci}")
    elif (ci - ctx.today).days < p["ci_avertizare_zile"]:
        avert.append(f"CI expiră în {(ci - ctx.today).days} zile")
    kyc_ani = (ctx.today - parse_date(c["kyc_actualizat_la"])).days / 365.25
    if kyc_ani > p["kyc_max_ani"]:
        avert.append(f"KYC vechi de {kyc_ani:.1f} ani")
    for flag in ("flag_pep", "flag_frauda_interna", "flag_decedat"):
        if c.get(flag):
            probleme.append(f"{flag} activ")
    for cons in ("consimtamant_anaf", "consimtamant_biroul_credit"):
        if not c.get(cons):
            avert.append(f"{cons} lipsă")
    status = "fail" if probleme else ("avertizare" if avert else "ok")
    txt = "; ".join(probleme + avert) or f"CI valabilă până la {ci}, KYC de {kyc_ani:.1f} ani, consimțăminte prezente"
    return CheckResult(status, txt, {"probleme": probleme, "avertizari": avert, "kyc_ani": round(kyc_ani, 1)})


@check("expuneri_interne")
def expuneri_interne(ctx: CheckContext, p: dict) -> CheckResult:
    rate = sum(l["rata_lunara"] or 0 for l in ctx.loans)
    rate_cod = sum(l["rata_lunara"] or 0 for l in ctx.codebitor_la)
    carduri = [f"{l['loan_id']} {round((l.get('utilizare_limita') or 0) * 100)}%" for l in ctx.loans if l["produs"] == "card_credit"]
    ctx.concluzii["rate_lunare_noi"] = round(rate + rate_cod, 2)
    ctx.concluzii["sold_total_noi"] = round(sum(l["sold_ramas"] for l in ctx.loans), 2)
    txt = f"{len(ctx.loans)} credite la noi, rate {fmt_ron(rate)} RON/lună"
    if carduri:
        txt += f"; carduri: {', '.join(carduri)}"
    if ctx.codebitor_la:
        txt += f"; codebitor la {', '.join(l['loan_id'] for l in ctx.codebitor_la)} (+{fmt_ron(rate_cod)} RON/lună)"
    return CheckResult("ok", txt, {"rate_lunare": round(rate, 2), "rate_codebitor": round(rate_cod, 2)})


@check("venit_observat")
def venit_observat(ctx: CheckContext, p: dict) -> CheckResult:
    fl = ctx.flows
    luni = fl.months[-p["luni"]:]
    venit = sum(fl.venit_lunar[m] for m in luni) / len(luni)
    nume = " ".join(ctx.client["nume"].upper().split())
    tp = sum(t["suma"] for t in ctx.transactions if t["directie"] == "in" and t["data"][:7] in luni
             and nume in " ".join(t["platitor_beneficiar"].upper().split())) / len(luni)
    ctx.concluzii.update(venit_lunar_observat=round(venit, 2), transferuri_proprii_lunar=round(tp, 2),
                         venit_lunar=round(venit if venit > 0 else tp, 2),       # fără salariu/pensie: transferurile proprii
                         venit_din_transferuri=venit <= 0 < tp,
                         venit_pe_luna={m: round(fl.venit_lunar[m], 2) for m in fl.months})
    if venit <= 0:
        return CheckResult("avertizare", f"nicio încasare de salariu/pensie în ultimele {p['luni']} luni"
                           + (f"; transferuri proprii {fmt_ron(tp)} RON/lună" if tp else ""),
                           {"venit": 0, "transferuri": round(tp, 2)})
    return CheckResult("ok", f"venit observat {fmt_ron(venit)} RON/lună (media ultimelor {p['luni']} luni)", {"venit": round(venit, 2)})


@check("sold_cont")
def sold_cont(ctx: CheckContext, p: dict) -> CheckResult:
    cont = ctx.mocks.conturi.get(ctx.client["client_id"])
    if not cont:
        return CheckResult("avertizare", "fără cont curent la noi", {})
    ist = cont["istoric_lunar"][-p["luni"]:]
    mediu = sum(x["sold_mediu"] for x in ist) / len(ist)
    minim = min(x["sold_minim"] for x in ist)
    iesiri = sum(x["iesiri"] for x in ist) / len(ist)
    ctx.concluzii.update(sold_curent=cont["sold_curent"], sold_mediu=round(mediu, 2), sold_minim=round(minim, 2),
                         cheltuieli_lunare=round(iesiri, 2))
    status = "avertizare" if minim < ctx.concluzii.get("rate_lunare_noi", 0) else "ok"
    return CheckResult(status, f"sold curent {fmt_ron(cont['sold_curent'])} RON; mediu {fmt_ron(mediu)}, minim {fmt_ron(minim)} "
                       f"pe {p['luni']} luni" + (" — sub o rată lunară" if status == "avertizare" else ""),
                       {"sold_curent": cont["sold_curent"], "sold_mediu": round(mediu, 2), "sold_minim": round(minim, 2)})


# ---------------------------------------------------------------- strat produse deținute

@check("ltv")
def ltv_check(ctx: CheckContext, p: dict) -> CheckResult:
    l = _secured(ctx)
    v = ltv_dosar(l) if l else None
    ctx.concluzii["ltv_dosar"] = round(v, 3) if v is not None else None
    if v is None:
        return CheckResult("avertizare", "fără evaluare în dosar", {})
    g = l["garantie"]
    return CheckResult("avertizare" if v > 1.0 else "ok",
                       f"LTV {v:.2f} ({fmt_ron(l['sold_ramas'])} / {fmt_ron(g['valoare_evaluare'])} RON, evaluare din {g['data_evaluare']})",
                       {"ltv": round(v, 3), "data_evaluare": g["data_evaluare"]})


@check("asigurare_garantie")
def asigurare_garantie(ctx: CheckContext, p: dict) -> CheckResult:
    l = _secured(ctx)
    if not l:
        return CheckResult("ok", "fără garanție", {})
    exp = parse_date(l["garantie"]["asigurare_expira_la"])
    zile = (exp - ctx.today).days
    if zile < 0:
        return CheckResult("fail", f"polița imobilului a expirat la {exp}", {"zile": zile})
    if zile < p["avertizare_zile"]:
        return CheckResult("avertizare", f"polița expiră în {zile} zile ({exp})", {"zile": zile})
    return CheckResult("ok", f"polița valabilă până la {exp}", {"zile": zile})


@check("utilizare_limita_card")
def utilizare_limita_card(ctx: CheckContext, p: dict) -> CheckResult:
    carduri = [l for l in ctx.loans if l["produs"] == "card_credit"]
    if not carduri:
        return CheckResult("ok", "fără card", {})
    top = max(carduri, key=lambda l: l.get("utilizare_limita") or 0)
    u = top.get("utilizare_limita") or 0
    minima = any(h["plata_minima_card"] for h in ctx.payments.get(top["loan_id"], [])[-2:])
    status = "avertizare" if u >= p["prag_avertizare"] or minima else "ok"
    return CheckResult(status, f"{top['loan_id']}: utilizare {round(u * 100)}% din {fmt_ron(top['limita'])} RON"
                       + ("; plata minimă recent" if minima else ""), {"utilizare": u, "plata_minima": minima})


# ---------------------------------------------------------------- strat motiv (intern)

def dobanda_piata(ctx: CheckContext, loan: dict) -> float:
    cheie = ctx.cfg.retention.piata[loan["produs"]]
    return float(ctx.market["dobanzi_piata"][loan["produs"]][cheie])


@check("scenarii_rata")
def scenarii_rata(ctx: CheckContext, p: dict) -> CheckResult:
    l = _loan_or_first(ctx)
    if not l:
        return CheckResult("ok", "fără credit existent", {})
    luni = luni_ramase(l, ctx.today)
    seg_ramai = segmente_credit(l, ctx.today, ctx.market)
    piata = dobanda_piata(ctx, l)
    d_ramai = dobanda_totala(l["sold_ramas"], seg_ramai)
    d_piata = dobanda_totala(l["sold_ramas"], [(luni, piata)])
    sc = {"luni_ramase": luni, "dobanda_ramai": round(d_ramai, 2), "dobanda_piata": round(d_piata, 2),
          "dobanda_pct_ramai": seg_ramai[-1][1], "dobanda_pct_piata": piata,
          "rata_ramai": round(rata_anuitate(l["sold_ramas"], seg_ramai[-1][1], luni), 2),
          "rata_piata": round(rata_anuitate(l["sold_ramas"], piata, luni), 2),
          "economie_bruta_plecare": round(d_ramai - d_piata, 2)}
    ctx.concluzii["scenarii"] = sc
    return CheckResult("ok", f"rămâi: {fmt_ron(d_ramai)} RON dobândă rămasă la {seg_ramai[-1][1]:.2f}% · "
                       f"piață: {fmt_ron(d_piata)} RON la {piata:.2f}% · diferență brută {fmt_ron(d_ramai - d_piata)} RON în {luni} luni", sc)


@check("cost_mutare")
def cost_mutare(ctx: CheckContext, p: dict) -> CheckResult:
    l = _loan_or_first(ctx)
    if not l:
        return CheckResult("ok", "fără credit existent", {})
    total, comp = cost_mutare_total(l, ctx.market)
    ctx.concluzii["cost_mutare"] = round(total, 2)
    return CheckResult("ok", f"costul mutării ≈ {fmt_ron(total)} RON (" + ", ".join(f"{k} {fmt_ron(v)}" for k, v in comp.items() if v) + ")",
                       {**{k: round(v, 2) for k, v in comp.items()}, "total": round(total, 2)})


@check("comision_rambursare_anticipata")
def comision_check(ctx: CheckContext, p: dict) -> CheckResult:
    l = _loan_or_first(ctx)
    if not l:
        return CheckResult("ok", "fără credit existent", {})
    suma = next((c["detalii"].get("suma") for c in ctx.cereri if c["detalii"].get("suma")), None) or round(l["sold_ramas"] * 0.1, -2)
    com, txt = comision_rambursare_anticipata(l, suma, ctx.today, ctx.cfg.retention.oug50)
    ctx.concluzii.update(suma_rambursare=suma, comision_rambursare=com)
    return CheckResult("ok", f"rambursare {fmt_ron(suma)} RON: comision {fmt_ron(com)} RON ({txt})", {"suma": suma, "comision": com})


@check("fond_urgenta")
def fond_urgenta(ctx: CheckContext, p: dict) -> CheckResult:
    ramas = ctx.concluzii.get("sold_curent", 0.0) - ctx.concluzii.get("suma_rambursare", 0.0)
    necesar = ctx.concluzii.get("cheltuieli_lunare", 0.0) * p["luni_cheltuieli"]
    status = "avertizare" if ramas < necesar else "ok"
    return CheckResult(status, f"după rambursare rămân {fmt_ron(ramas)} RON față de {fmt_ron(necesar)} RON "
                       f"({p['luni_cheltuieli']} luni de cheltuieli)" + (" — fond de urgență insuficient" if status == "avertizare" else ""),
                       {"ramas": round(ramas, 2), "necesar": round(necesar, 2)})


def _rate_externe(ctx: CheckContext) -> float:
    if "rate_alti_creditori_bc" in ctx.concluzii:
        return ctx.concluzii["rate_alti_creditori_bc"]
    return sum(f.suma_medie for f in ctx.flows.creditori)      # fără BC: ce vedem în tranzacții


@check("capacitate_plata_actuala")
def capacitate_plata(ctx: CheckContext, p: dict) -> CheckResult:
    venit = ctx.concluzii.get("venit_lunar", 0.0)
    rate = ctx.concluzii.get("rate_lunare_noi", 0.0) + _rate_externe(ctx)
    d = dti(rate, venit)
    ctx.concluzii["dti_curent"] = round(d, 3) if d is not None else None
    if d is None:
        return CheckResult("avertizare", "venit necunoscut: DTI nu se poate calcula", {"rate": round(rate, 2)})
    mx = ctx.cfg.constraints.dti.max
    status = "avertizare" if d > mx else "ok"
    return CheckResult(status, f"DTI {d:.0%} = rate {fmt_ron(rate)} / venit {fmt_ron(venit)} RON" + (f" — peste {mx:.0%}" if status == "avertizare" else ""),
                       {"dti": round(d, 3), "rate": round(rate, 2), "venit": round(venit, 2)})


@check("eligibilitate_produs_nou")
def eligibilitate_produs_nou(ctx: CheckContext, p: dict) -> CheckResult:
    C = ctx.cfg.constraints
    cerere = next((c for c in ctx.cereri if c["tip"] in ELIGIBILITATE), None)
    if not cerere:
        return CheckResult("ok", "nicio cerere de produs nou", {})
    venit = ctx.concluzii.get("venit_lunar", 0.0)
    produs = cerere["detalii"].get("produs_vizat") or cerere.get("produs")
    suma = cerere["detalii"].get("suma") or 0
    motive = []
    if venit < C.dti.venit_minim_lunar_ron:
        motive.append(f"venit {fmt_ron(venit)} RON sub minimul {fmt_ron(C.dti.venit_minim_lunar_ron)} RON")
    if produs == "card_credit":
        rata_noua = suma * 0.05
    elif produs in ("ipotecar", "imobiliar"):
        rata_noua = rata_anuitate(suma, float(ctx.market["dobanzi_piata"][produs]["fixa_3_ani"]), 300)
    else:
        rata_noua = rata_anuitate(suma, float(ctx.market["dobanda_piata_nevoi_personale"]), 60)
    if cerere["tip"] == "refinantare" and ctx.loan:
        rata_noua -= ctx.loan["rata_lunara"]                       # înlocuiește rata veche
    d = dti(ctx.concluzii.get("rate_lunare_noi", 0.0) + _rate_externe(ctx) + rata_noua, venit)
    mx = C.dti.max + (C.dti.bonus_prima_locuinta if produs == "ipotecar" else 0.0)
    if d is not None and d > mx:
        motive.append(f"DTI după rata nouă {d:.0%} > {mx:.0%}")
    ani = 25 if produs in ("ipotecar", "imobiliar") else 5
    varsta = varsta_la(ctx.client["data_nasterii"], ctx.today) + ani
    if varsta > C.varsta.max_la_scadenta:
        motive.append(f"vârsta la scadență {varsta:.0f} > {C.varsta.max_la_scadenta}")
    ctx.concluzii.update(eligibil=not motive, motiv_ineligibil="; ".join(motive) or None,
                         rata_noua=round(rata_noua, 2), dti_dupa=round(d, 3) if d is not None else None)
    if motive:
        return CheckResult("fail", "neeligibil: " + "; ".join(motive), {"motive": motive})
    return CheckResult("ok", f"eligibil pentru {produs}: rată nouă {fmt_ron(rata_noua)} RON, DTI după {d:.0%} ≤ {mx:.0%}", {"dti_dupa": round(d, 3)})


# ---------------------------------------------------------------- externe (mock-uri)

@check("venit_anaf")
def venit_anaf(ctx: CheckContext, p: dict) -> CheckResult:
    a = ctx.mocks.anaf.get(ctx.client["client_id"])
    if not a:
        return CheckResult("avertizare", "ANAF: fără răspuns pentru client", {}, "ANAF")
    if a.get("rezident_fiscal", "RO") != "RO":
        return CheckResult("avertizare", f"ANAF: nerezident fiscal ({a['rezident_fiscal']}); venitul din străinătate nu e raportat — "
                           f"se folosesc transferurile proprii ({fmt_ron(ctx.concluzii.get('transferuri_proprii_lunar', 0))} RON/lună) "
                           "și documentele clientului", {"rezident_fiscal": a["rezident_fiscal"]}, "ANAF")
    luni = last_months(a["perioada"]["pana_la"], p["luni"])
    lunar, surse_txt, salariu_recent = 0.0, [], False
    for s in a["surse"]:
        if s["frecventa"] == "lunar":
            v = sum(s["valori"].get(m, 0.0) for m in luni) / len(luni)
            if s["tip"] == "salariu" and s["valori"].get(luni[-1]):
                salariu_recent = True
            surse_txt.append(f"{s['tip']} {s['platitor']}: {fmt_ron(v)} RON/lună (ultima {max(s['valori']) if s['valori'] else '—'})")
        else:
            v = sum(s["valori"].values()) / 12
            surse_txt.append(f"{s['tip']}: {fmt_ron(v)} RON/lună (anual {fmt_ron(sum(s['valori'].values()))})")
        lunar += v
    observat = ctx.concluzii.get("venit_lunar_observat", 0.0)
    pe_luna = ctx.concluzii.get("venit_pe_luna", {})
    recent = sum(v for m, v in sorted(pe_luna.items())[-p["luni_lipsa"]:])      # ce am văzut noi în ultimele luni
    ctx.concluzii["venit_lunar_anaf"] = round(lunar, 2)
    ctx.concluzii["venit_lunar"] = round(max(lunar, observat), 2)
    ctx.concluzii["salariu_la_alta_banca"] = bool(salariu_recent and recent <= 0)
    if lunar <= 0:
        status = "fail" if any(m in ELIGIBILITATE for m in ctx.motive) else "avertizare"
        return CheckResult(status, "ANAF: niciun venit raportat în ultimele luni — venitul a încetat", {"venit": 0}, "ANAF")
    txt = f"ANAF: {fmt_ron(lunar)} RON/lună din " + "; ".join(surse_txt)
    if ctx.concluzii["salariu_la_alta_banca"]:
        txt += " → salariul continuă, dar e încasat la altă bancă"
    return CheckResult("ok", txt, {"venit": round(lunar, 2), "salariu_la_alta_banca": ctx.concluzii["salariu_la_alta_banca"]}, "ANAF")


@check("istoric_biroul_credit")
def istoric_bc(ctx: CheckContext, p: dict) -> CheckResult:
    b = ctx.mocks.bc.get(ctx.client["client_id"])
    if not b:
        return CheckResult("avertizare", "Biroul de Credit: fără răspuns", {}, "Biroul de Credit")
    active = [c for c in b["credite"] if c["stare"] == "activ"]
    rate = round(sum(c["rata_lunara"] for c in active), 2)
    ctx.concluzii.update(rate_alti_creditori=rate, rate_alti_creditori_bc=rate, interogari_bc=b["interogari_ultimele_6l"],
                         credite_externe=len(active))
    rele = [c for c in b["credite"] if c["max_zile_intarziere_24l"] >= p["max_zile_intarziere_24l"]]
    if rele:
        c = rele[0]
        return CheckResult("fail", f"Biroul de Credit: {c['max_zile_intarziere_24l']} zile întârziere la {c['institutie']} ({c['tip']}, {c['stare']})",
                           {"intarziere": c["max_zile_intarziere_24l"], "institutie": c["institutie"]}, "Biroul de Credit")
    if b["scor"] is not None and b["scor"] < p["scor_minim"]:
        return CheckResult("fail", f"Biroul de Credit: scor {b['scor']} sub {p['scor_minim']}", {"scor": b["scor"]}, "Biroul de Credit")
    scor = "fără istoric" if b["fara_istoric"] else f"scor {b['scor']}"
    txt = (f"Biroul de Credit: {scor}; {len(active)} credite active la alte instituții ({fmt_ron(rate)} RON/lună); "
           f"{b['interogari_ultimele_6l']} interogări în 6 luni")
    if b["interogari_ultimele_6l"] >= ctx.cfg.retention.interogari_bc_min_pentru_activ:
        txt += " → își caută bancă"
    return CheckResult("ok", txt, {"scor": b["scor"], "interogari": b["interogari_ultimele_6l"], "credite_active": len(active)}, "Biroul de Credit")


@check("expuneri_crc")
def expuneri_crc(ctx: CheckContext, p: dict) -> CheckResult:
    c = ctx.mocks.crc.get(ctx.client["client_id"])
    if not c:
        return CheckResult("avertizare", "CRC: fără răspuns", {}, "CRC")
    ctx.concluzii["expuneri_crc_total"] = round(sum(e["sold"] for e in c["expuneri"]), 2)
    rest = [e for e in c["expuneri"] if e["restante"] > 0]
    if rest:
        e = rest[0]
        return CheckResult("fail", f"CRC: {e['rol']} la {e['institutie']} cu restanțe {fmt_ron(e['restante'])} RON ({e['zile_restanta']} zile)", e, "CRC")
    if not c["expuneri"]:
        return CheckResult("ok", f"CRC: nicio expunere peste {fmt_ron(c['prag_raportare_ron'])} RON la alte bănci", {}, "CRC")
    return CheckResult("ok", "CRC: " + "; ".join(f"{e['rol']} {e['institutie']} {fmt_ron(e['sold'])} RON, fără restanțe" for e in c["expuneri"]),
                       {"expuneri": c["expuneri"]}, "CRC")


@check("extras_cf")
def extras_cf(ctx: CheckContext, p: dict) -> CheckResult:
    l = _secured(ctx)
    g = ctx.mocks.garantii.get(l["loan_id"]) if l else None
    if not g:
        return CheckResult("avertizare", "garanție: fără extras CF", {}, "OCPI")
    cf = g["cf"]
    probleme = [f"litigiu notat: {x['tip']} dosar {x['dosar']} ({x['notat_la']})" for x in cf["litigii"]]
    if cf["alte_sarcini"]:
        probleme.append("alte sarcini: " + ", ".join(map(str, cf["alte_sarcini"])))
    if not cf["ipoteca_rang_1_banca"]:
        probleme.append("ipoteca băncii nu e de rang 1")
    ctx.concluzii["litigii_cf"] = bool(cf["litigii"])
    if probleme:
        return CheckResult("fail", f"extras CF {cf['numar']} {cf['uat']}: " + "; ".join(probleme), {"probleme": probleme}, "OCPI")
    return CheckResult("ok", f"extras CF {cf['numar']} {cf['uat']}: ipotecă rang 1, fără sarcini sau litigii", {}, "OCPI")


@check("reevaluare_garantie")
def reevaluare_garantie(ctx: CheckContext, p: dict) -> CheckResult:
    l = _secured(ctx)
    g = ctx.mocks.garantii.get(l["loan_id"]) if l else None
    if not g:
        return CheckResult("avertizare", "garanție: fără reevaluare", {}, "evaluator")
    val = g["reevaluare"]["valoare"]
    v = l["sold_ramas"] / val if val else None
    ctx.concluzii["ltv_actual"] = round(v, 3) if v is not None else None
    mx = ctx.cfg.constraints.ltv.max.get(l["produs"], 1.0)
    status = "avertizare" if v is not None and v > mx else "ok"
    return CheckResult(status, f"reevaluare {fmt_ron(val)} RON ({g['reevaluare']['data']}, {g['reevaluare']['metoda']}) → LTV actual {v:.2f}"
                       + (f" peste {mx:.2f}" if status == "avertizare" else ""), {"valoare": val, "ltv_actual": round(v, 3)}, "evaluator")


# ---------------------------------------------------------------- rulare în trepte

CONCLUZII_IMPLICITE = {"venit_lunar": 0.0, "venit_lunar_observat": 0.0, "venit_lunar_anaf": None, "salariu_la_alta_banca": False,
                       "rate_lunare_noi": 0.0, "rate_alti_creditori": 0.0, "dti_curent": None, "ltv_dosar": None,
                       "ltv_actual": None, "interogari_bc": 0, "cost_mutare": None, "scenarii": None,
                       "eligibil": None, "motiv_ineligibil": None, "litigii_cf": False}


def run_checks(plan: dict, ctx: CheckContext) -> dict:
    """Rulează planul în trepte; se oprește la prima treaptă cu o verificare picată, restul rămân neexecutate."""
    CH = ctx.cfg.checks
    by_id = CH.by_id()
    ctx.concluzii = dict(CONCLUZII_IMPLICITE)
    rezultate: list[dict] = []
    oprit_la = picata = None
    executate = 0
    for treapta in CH.trepte:
        items = [x for x in plan["plan"] if x["treapta"] == treapta]
        if oprit_la:
            rezultate += [{**x, "status": "neexecutat", "dovada": f"neexecutat (oprit la {oprit_la})", "detalii": {}, "sursa": None}
                          for x in items]
            continue
        for x in items:
            r = CHECKS[x["id"]](ctx, by_id[x["id"]].parametri)
            executate += int(x["externa"])
            rezultate.append({**x, "status": r.status, "dovada": r.dovada, "detalii": r.detalii, "sursa": r.sursa})
            if r.status == "fail" and picata is None:
                picata = x["id"]
        if picata and not oprit_la:
            oprit_la = treapta
    return {**plan, "rezultate": rezultate, "oprit_la": oprit_la, "verificare_picata": picata, "concluzii": ctx.concluzii,
            "interogari_externe": {**plan["interogari_externe"], "executate": executate}}
