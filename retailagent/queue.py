"""Coada prioritizată: semnale + cereri → cazuri cu scoruri, bandă, termen, motive și acțiune propusă.

    python -m retailagent.queue          # out/queue.json + tabel în consolă

Formule (toate ponderile/pragurile din config/priority.yaml):
    plecare   = Σ pondere_i × scor_i (+ bonus simulare)          ∈ [0,1]
    valoare   = 0.6 × venit_viitor_norm + 0.4 × produse_norm      ∈ [0,1]
    actiune   = 1.0 | 0.5 | 0.0   (gap față de piață acoperibil din bugetul de retenție)
    prioritate_retentie = plecare × valoare × actiune
    risc_credit         = max(semnale risc_credit ale clientului)
    prioritate          = max(risc_credit, prioritate_retentie)   (cererile explicite pot impune un minim)
"""
from __future__ import annotations

import argparse
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from .common import (CONFIG_DIR, DATA_DIR, OUT_DIR, log_event, parse_date, plural, read_json, setup_console,
                     write_json)
from .config_loader import Config, load_config
from .intake import run_intake
from .scan import Portfolio, load_portfolio, run_scan
from .signals.util import ani_ramasi, marja_efectiva

FAMILII = ("blocaj_proces", "risc_credit", "plecare")


def venit_viitor(loan: dict, today: date, market: dict) -> float:
    """marja × sold × ani rămași (în lei, nenormalizat)."""
    return marja_efectiva(loan, market) / 100 * loan["sold_ramas"] * ani_ramasi(loan, today)


@dataclass
class CaseInput:
    """Tot ce trebuie pentru a scora un caz — separat de calcul ca explain să poată rula scenarii „ce-ar fi dacă”."""
    client: dict
    loan: dict | None
    produs: str | None
    semnale: list[dict]                 # detecții (id, familie, scor, dovada, detalii, loan_id)
    cereri: list[dict]                  # cazuri din intake atașate
    venit_max: float
    today: date
    market: dict


@dataclass
class Trace:
    """Detaliile calculului, pentru explain (nu se scriu în queue.json)."""
    contributii_plecare: list[tuple[str, float, float, float]] = field(default_factory=list)  # id, pondere, scor, contrib
    venit_viitor: float = 0.0
    venit_norm: float = 0.0
    produse_norm: float = 0.0
    gap_pp: float | None = None
    necesar_pp: float | None = None
    buget_pp: float | None = None
    actiune_eticheta: str = ""
    risc_sursa: str | None = None
    banda_motiv: str = ""
    actiune_motiv: str = ""
    deadline_motiv: str = ""
    prioritate_min_cerere: float = 0.0
    semnal_activ: str | None = None


def _motiv(cfg: Config, s: dict) -> str:
    tpl = cfg.signals.by_id()[s["id"]].motiv
    try:
        return tpl.format(**s.get("detalii", {}))
    except (KeyError, IndexError, ValueError):
        return s["dovada"]


def score_case(ci: CaseInput, cfg: Config) -> tuple[dict, Trace]:
    P = cfg.priority
    tr = Trace()
    by_fam: dict[str, list[dict]] = defaultdict(list)
    for s in ci.semnale:
        by_fam[s["familie"]].append(s)

    # ---- plecare
    plecare = 0.0
    for s in by_fam["plecare"]:
        w = P.ponderi_plecare.get(s["id"])
        if w is not None:
            plecare += w * s["scor"]
            tr.contributii_plecare.append((s["id"], w, s["scor"], w * s["scor"]))
        elif s["id"] in P.bonus_plecare:
            plecare += P.bonus_plecare[s["id"]]
            tr.contributii_plecare.append((s["id"], 0.0, s["scor"], P.bonus_plecare[s["id"]]))
    plecare = min(1.0, plecare)
    tr.contributii_plecare.sort(key=lambda c: -c[3])

    # ---- valoare
    if ci.loan:
        tr.venit_viitor = venit_viitor(ci.loan, ci.today, ci.market)
        tr.venit_norm = tr.venit_viitor / ci.venit_max if ci.venit_max > 0 else 0.0
    tr.produse_norm = min(1.0, len(ci.client.get("produse_atasate", [])) / P.valoare.produse_max)
    valoare = P.valoare.venit_viitor * tr.venit_norm + P.valoare.produse_atasate * tr.produse_norm

    # ---- actiune (gap acoperibil din bugetul de retenție?)
    if ci.loan is None:
        actiune, tr.actiune_eticheta = P.actiune.imposibil, "imposibil"
    else:
        gap = next((s for s in ci.semnale if s["id"] == "gap_piata_bani" and s.get("loan_id") == ci.loan["loan_id"]), None)
        tr.gap_pp = gap["detalii"].get("gap_pp", 0.0) if gap else 0.0
        tr.necesar_pp = P.grila_retentie.spread_peste_piata_pp.get(ci.loan["produs"], 0.0)
        tr.buget_pp = P.buget_retentie_pp.get(ci.client["nivel_relatie"], 0.0)
        if tr.gap_pp <= 0 or tr.necesar_pp <= tr.buget_pp:
            actiune, tr.actiune_eticheta = P.actiune.oferta_in_grila, "oferta_in_grila"
        elif tr.necesar_pp <= tr.buget_pp * P.grila_retentie.multiplicator_partial:
            actiune, tr.actiune_eticheta = P.actiune.partial, "partial"
        else:
            actiune, tr.actiune_eticheta = P.actiune.imposibil, "imposibil"

    prioritate_retentie = plecare * valoare * actiune

    # ---- risc credit (nivel client, agregare max)
    risc_sigs = sorted(by_fam["risc_credit"], key=lambda s: -s["scor"])
    risc = risc_sigs[0]["scor"] if risc_sigs else 0.0
    tr.risc_sursa = risc_sigs[0]["id"] if risc_sigs else None

    prioritate = max(risc, prioritate_retentie)
    tr.prioritate_min_cerere = max((c["prioritate_min"] for c in ci.cereri), default=0.0)
    prioritate = max(prioritate, tr.prioritate_min_cerere)

    # ---- bandă
    for sid, prag in P.semnale_active.items():
        hit = next((s for s in ci.semnale if s["id"] == sid and s["scor"] >= prag), None)
        if hit:
            tr.semnal_activ = sid
            break
    benzi = list(P.benzi.items())
    banda = benzi[-1][0]
    for name, b in benzi:
        if prioritate >= b.prioritate_min:
            banda, tr.banda_motiv = name, f"prioritate {prioritate:.2f} ≥ {b.prioritate_min:.2f}"
            break
        if b.sau_risc_credit_min is not None and risc >= b.sau_risc_credit_min:
            banda, tr.banda_motiv = name, f"risc_credit {risc:.2f} ≥ {b.sau_risc_credit_min:.2f}"
            break
        if b.sau_semnal_activ and tr.semnal_activ:
            banda, tr.banda_motiv = name, f"semnal activ: {tr.semnal_activ}"
            break

    # ---- blocaje (nivel client) + acțiune
    ordine = {sid: i for i, sid in enumerate(P.blocaj.ordine)}
    blocaje = sorted({s["id"] for s in by_fam["blocaj_proces"] if s["scor"] >= P.blocaj.activ_de_la},
                     key=lambda sid: (ordine.get(sid, 99), sid))
    cerere_act = next((c["actiune_cerere"] for c in ci.cereri if c["actiune_cerere"]), None)
    expirare = next((s for s in ci.semnale if s["id"] == "expirare_dobanda_fixa"), None)
    if blocaje:
        act, tr.actiune_motiv = f"task_{blocaje[0]}", f"blocaj de proces activ: {', '.join(blocaje)}"
    elif risc >= P.risc_credit.blocheaza_retentia_daca:
        act, tr.actiune_motiv = "restructurare_preventiva", \
            f"risc_credit {risc:.2f} ≥ {P.risc_credit.blocheaza_retentia_daca:.2f} — fără ofertă de retenție"
    elif cerere_act:
        act, tr.actiune_motiv = cerere_act, "cerere explicită a clientului"
    elif expirare and expirare["scor"] >= P.rutare.informare_expirare_min and tr.actiune_eticheta == "imposibil":
        act, tr.actiune_motiv = "informare_client", "dobânda fixă expiră, dar oferta nu încape în buget — obligație de informare"
    elif P.rutare.retentie_la_semnal_activ and tr.semnal_activ:
        act, tr.actiune_motiv = "retentie_refinantare", f"semnal activ de plecare: {tr.semnal_activ}"
    elif prioritate_retentie >= P.rutare.retentie_min:
        act, tr.actiune_motiv = "retentie_refinantare", \
            f"prioritate_retentie {prioritate_retentie:.2f} ≥ {P.rutare.retentie_min:.2f}"
    else:
        act, tr.actiune_motiv = P.rutare.actiune_implicita, "niciun prag de acțiune atins"

    # ---- termen-limită
    sla = P.benzi[banda].sla_zile
    deadline = ci.today + timedelta(days=sla)
    tr.deadline_motiv = f"SLA {banda} = {plural(sla, 'zi', 'zile')}"
    exp_date = parse_date(ci.loan.get("dobanda_fixa_expira_la")) if ci.loan else None
    if exp_date and exp_date >= ci.today:
        inform = exp_date - timedelta(days=P.deadline.informare_inainte_de_expirare_zile)
        if inform < deadline:
            deadline = max(ci.today, inform)
            tr.deadline_motiv = (f"informare cu {P.deadline.informare_inainte_de_expirare_zile} zile înainte de "
                                 f"expirarea dobânzii fixe ({exp_date.isoformat()})"
                                 + (" — termen deja depășit, imediat" if inform < ci.today else ""))

    # ---- motive (din scorul care a decis banda)
    motive: list[str] = []
    for b in blocaje:
        s = next(x for x in by_fam["blocaj_proces"] if x["id"] == b)
        motive.append(_motiv(cfg, s))
    if tr.semnal_activ and risc < P.risc_credit.blocheaza_retentia_daca:   # semnalul care a decis banda e primul
        motive.append(_motiv(cfg, next(s for s in ci.semnale if s["id"] == tr.semnal_activ)))
    retentie_decide = prioritate_retentie > risc
    if not retentie_decide:
        motive += [_motiv(cfg, s) for s in risc_sigs]
    din_semnale = {s.get("detalii", {}).get("request_id") for s in ci.semnale}
    for c in ci.cereri:
        if c["request_id"] not in din_semnale:      # cererea e deja descrisă de semnalul derivat din ea
            motive.append(f"Cerere {c['tip'].replace('_', ' ')} din {c['data']} ({c['request_id']})")
    sig_by_id = {s["id"]: s for s in by_fam["plecare"]}
    plecare_mot = [_motiv(cfg, sig_by_id[cid]) for cid, *_ in tr.contributii_plecare if cid in sig_by_id]
    if retentie_decide:
        motive += plecare_mot[:2]
        motive.append(f"Client {ci.client['nivel_relatie']}, {len(ci.client.get('produse_atasate', []))} produse atașate")
        motive += plecare_mot[2:]
    else:
        motive += plecare_mot
    seen, motive_top3 = set(), []
    for m in motive:
        if m not in seen:
            seen.add(m)
            motive_top3.append(m)
    motive_top3 = motive_top3[:3]

    fam_rank = {f: i for i, f in enumerate(FAMILII)}
    semnale = sorted(({"id": s["id"], "familie": s["familie"], "scor": round(s["scor"], 2), "dovada": s["dovada"]}
                      for s in ci.semnale), key=lambda s: (fam_rank[s["familie"]], -s["scor"], s["id"]))
    case = {
        "case_id": None,
        "client_id": ci.client["client_id"],
        "loan_id": ci.loan["loan_id"] if ci.loan else None,
        "produs": ci.loan["produs"] if ci.loan else ci.produs,
        "sursa": None,
        "request_id": None,
        "semnale": semnale,
        "scoruri": {"plecare": round(plecare, 2), "valoare": round(valoare, 2), "actiune": actiune,
                    "prioritate_retentie": round(prioritate_retentie, 2), "risc_credit": round(risc, 2),
                    "prioritate": round(prioritate, 2)},
        "banda": banda,
        "deadline": deadline.isoformat(),
        "motive_top3": motive_top3,
        "actiune_propusa": act,
        "blocaje": blocaje,
        "creat_la": f"{ci.today.isoformat()}T00:00:00",
    }
    return case, tr


# ---------------------------------------------------------------- construirea cozii

@dataclass
class QueueResult:
    cases: list[dict]
    traces: dict[str, Trace]           # case_id -> trace
    inputs: dict[str, CaseInput]       # case_id -> input (pentru explain / what-if)


def build_case_inputs(pf: Portfolio, cfg: Config, detections: list[dict], intake_cases: list[dict]) -> list[tuple[CaseInput, str]]:
    sig_cfg = cfg.signals.by_id()
    venit_max = max((venit_viitor(l, pf.today, pf.market) for l in pf.loans), default=0.0)
    det_client: dict[str, list[dict]] = defaultdict(list)
    det_loan: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for d in detections:
        if d["loan_id"] is None:
            det_client[d["client_id"]].append(d)
        else:
            det_loan[(d["client_id"], d["loan_id"])].append(d)
    req_by_client: dict[str, list[dict]] = defaultdict(list)
    for c in intake_cases:
        req_by_client[c["client_id"]].append(c)

    out: list[tuple[CaseInput, str]] = []
    for client in pf.clients:
        cid = client["client_id"]
        loans = pf.loans_by_client.get(cid, [])
        # risc și blocaje: nivel client, propagate pe toate cazurile
        client_wide = det_client[cid] + [d for l in loans for d in det_loan[(cid, l["loan_id"])]
                                         if d["familie"] in ("risc_credit", "blocaj_proces")]
        reqs = req_by_client.get(cid, [])
        for loan in loans:
            own = [d for d in det_loan[(cid, loan["loan_id"])] if d["familie"] == "plecare"]
            semnale = own + client_wide
            cereri = [r for r in reqs if r["loan_id"] == loan["loan_id"]]
            triggers = [s for s in semnale if sig_cfg[s["id"]].declansator]
            if not triggers and not cereri:
                continue
            sursa = "scan" if any(not sig_cfg[s["id"]].sursa_cerere for s in triggers) else "client_request"
            out.append((CaseInput(client, loan, loan["produs"], semnale, cereri, venit_max, pf.today, pf.market), sursa))
        for r in reqs:
            if r["loan_id"] is None:
                out.append((CaseInput(client, None, r["produs"], list(client_wide), [r], venit_max, pf.today,
                                      pf.market), "client_request"))
    return out


def build_queue(pf: Portfolio, cfg: Config, detections: list[dict], intake_cases: list[dict]) -> QueueResult:
    scored = []
    for ci, sursa in build_case_inputs(pf, cfg, detections, intake_cases):
        case, tr = score_case(ci, cfg)
        case["sursa"] = sursa
        if ci.cereri:
            case["request_id"] = max(ci.cereri, key=lambda c: (c["data"], c["request_id"]))["request_id"]
        scored.append((case, tr, ci))
    band_rank = {b: i for i, b in enumerate(cfg.priority.benzi)}
    scored.sort(key=lambda x: (band_rank[x[0]["banda"]], -x[0]["scoruri"]["prioritate"], x[0]["deadline"],
                               x[0]["client_id"], x[0]["loan_id"] or "", x[0]["request_id"] or ""))
    res = QueueResult([], {}, {})
    for i, (case, tr, ci) in enumerate(scored, 1):
        case["case_id"] = f"Q{i:04d}"
        res.cases.append(case)
        res.traces[case["case_id"]] = tr
        res.inputs[case["case_id"]] = ci
    return res


def load_or_scan(pf: Portfolio, cfg: Config, out_dir: Path) -> list[dict]:
    p = out_dir / "signals_detected.json"
    if p.exists():
        return read_json(p)
    det = run_scan(pf, cfg)
    write_json(p, det)
    return det


def run_pipeline(data_dir=DATA_DIR, out_dir=OUT_DIR, config_dir=CONFIG_DIR, today: str | None = None,
                 cfg: Config | None = None, rescan: bool = False) -> tuple[Portfolio, Config, QueueResult]:
    cfg = cfg or load_config(config_dir)
    pf = load_portfolio(data_dir, today)
    det = run_scan(pf, cfg) if rescan else load_or_scan(pf, cfg, Path(out_dir))
    return pf, cfg, build_queue(pf, cfg, det, run_intake(pf, cfg))


def print_table(cases: list[dict], n: int = 20) -> None:
    hdr = f"{'case_id':<7} {'client':<6} {'produs':<15} {'banda':<5} {'prio':>4} {'deadline':<10}  {'motiv principal':<58} {'acțiune':<26} {'sursă':<14}"
    print(hdr)
    print("-" * len(hdr))
    for c in cases[:n]:
        motiv = (c["motive_top3"][0] if c["motive_top3"] else "")
        motiv = motiv if len(motiv) <= 58 else motiv[:57] + "…"
        blocat = " [BLOCAT]" if c["blocaje"] else ""
        print(f"{c['case_id']:<7} {c['client_id']:<6} {c['produs'] or '—':<15} {c['banda']:<5} "
              f"{c['scoruri']['prioritate']:>4.2f} {c['deadline']:<10}  {motiv:<58} "
              f"{(c['actiune_propusa'] + blocat):<26} {c['sursa']:<14}")


def main(argv: list[str] | None = None) -> None:
    setup_console()
    ap = argparse.ArgumentParser(description="Construiește coada prioritizată.")
    ap.add_argument("--today")
    ap.add_argument("--data-dir", default=str(DATA_DIR))
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ap.add_argument("--config-dir", default=str(CONFIG_DIR))
    ap.add_argument("--rescan", action="store_true", help="rulează scanarea chiar dacă există signals_detected.json")
    ap.add_argument("--top", type=int, default=20)
    a = ap.parse_args(argv)

    t0 = time.perf_counter()
    pf, cfg, res = run_pipeline(a.data_dir, a.out_dir, a.config_dir, a.today, rescan=a.rescan)
    write_json(Path(a.out_dir) / "queue.json", res.cases)
    dt = time.perf_counter() - t0

    print(f"Coadă: {len(res.cases)} cazuri pentru {len({c['client_id'] for c in res.cases})} clienți "
          f"(din {len(pf.clients)}), azi = {pf.today}, {dt:.2f}s → {a.out_dir}/queue.json\n")
    print_table(res.cases, a.top)
    bands = Counter(c["banda"] for c in res.cases)
    acts = Counter(c["actiune_propusa"] for c in res.cases)
    print(f"\nBenzi:   " + "  ".join(f"{b}={bands.get(b, 0)}" for b in cfg.priority.benzi))
    print("Acțiuni: " + "  ".join(f"{k}={v}" for k, v in acts.most_common()))
    print(f"Blocate: {sum(1 for c in res.cases if c['blocaje'])}   "
          f"Din cereri: {sum(1 for c in res.cases if c['request_id'])}")
    log_event(a.out_dir, "queue", "done", cazuri=len(res.cases), benzi=dict(bands), secunde=round(dt, 3))


if __name__ == "__main__":
    main()
