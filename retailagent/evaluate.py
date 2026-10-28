"""Evaluare pe ground_truth.json: detecție semnale, clasificarea tranzacțiilor, benzi, acțiuni, ordonare,
cerințe dure, cazuri-capcană și timp de rulare (50 clienți + portofoliu mare generat la cerere).

    python -m retailagent.evaluate                 # metrici pe 50 clienți
    python -m retailagent.evaluate --scale 5000    # + generează 5.000 clienți și măsoară timpul
"""
from __future__ import annotations

import argparse
import time
from collections import Counter, defaultdict
from datetime import timedelta
from pathlib import Path

from .common import CONFIG_DIR, DATA_DIR, OUT_DIR, log_event, parse_date, read_json, setup_console, write_json
from .config_loader import Config, load_config
from .generate import SCENARIOS, TRAP_INDEX, generate
from .intake import run_intake
from .queue import build_queue
from .scan import Portfolio, client_flows, load_portfolio, run_scan

TIPURI_DEDUSE = ("salariu", "pensie", "rata_alt_creditor", "poprire")


def prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    p = tp / (tp + fp) if tp + fp else 1.0
    r = tp / (tp + fn) if tp + fn else 1.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f


def eval_detection(det: list[dict], gt: list[dict], cfg: Config) -> dict:
    evaluated = [s.id for s in cfg.signals.active() if s.evaluat]
    found = defaultdict(set)
    for d in det:
        found[d["client_id"]].add(d["id"])
    per, tot = {}, Counter()
    for sid in evaluated:
        c = Counter()
        for g in gt:
            truth, pred = sid in g["semnale_plantate"], sid in found[g["client_id"]]
            c["tp"] += truth and pred
            c["fp"] += pred and not truth
            c["fn"] += truth and not pred
        p, r, f = prf(c["tp"], c["fp"], c["fn"])
        per[sid] = {"tp": c["tp"], "fp": c["fp"], "fn": c["fn"], "precizie": p, "recall": r, "f1": f}
        tot.update(c)
    p, r, f = prf(tot["tp"], tot["fp"], tot["fn"])
    return {"per_semnal": per, "global": {"tp": tot["tp"], "fp": tot["fp"], "fn": tot["fn"],
                                          "precizie": p, "recall": r, "f1": f}}


def eval_inflows(pf: Portfolio, cfg: Config) -> dict:
    """Tipul dedus din recurență + regex vs tip_etichetat (doar tipurile pe care se bazează semnalele)."""
    c = {t: Counter() for t in TIPURI_DEDUSE}
    months = None
    for cl in pf.clients:
        txs = pf.tx_by_client.get(cl["client_id"], [])
        fl = client_flows(pf, cfg, cl["client_id"])
        months = set(fl.months)
        for t, pred in zip(txs, fl.clasificare):
            if t["data"][:7] not in months:
                continue
            for k in TIPURI_DEDUSE:
                truth = t["tip_etichetat"] == k
                c[k]["tp"] += truth and pred == k
                c[k]["fp"] += pred == k and not truth
                c[k]["fn"] += truth and pred != k
    return {k: dict(zip(("precizie", "recall", "f1"), prf(v["tp"], v["fp"], v["fn"])), n=v["tp"] + v["fn"])
            for k, v in c.items()}


def eval_queue(cases: list[dict], gt: list[dict], pf: Portfolio, cfg: Config) -> dict:
    bands = list(cfg.priority.benzi)
    top: dict[str, tuple[int, dict]] = {}
    for pos, c in enumerate(cases):
        top.setdefault(c["client_id"], (pos, c))
    labels = bands + ["—"]
    conf = {e: {p: 0 for p in labels} for e in labels}
    ok_band = ok_act = 0
    for g in gt:
        exp_b = g["banda_asteptata"] or "—"
        got = top.get(g["client_id"])
        got_b = got[1]["banda"] if got else "—"
        conf[exp_b][got_b] += 1
        ok_band += exp_b == got_b
        ok_act += (got[1]["actiune_propusa"] if got else None) == g["actiune_asteptata"]

    # ordonare: perechi de clienți cu benzi așteptate diferite trebuie să apară în ordinea corectă
    rank = {b: i for i, b in enumerate(bands)}
    items = [(rank[g["banda_asteptata"]], top[g["client_id"]][0]) for g in gt
             if g["banda_asteptata"] and g["client_id"] in top]
    pairs = correct = 0
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            (ea, pa), (eb, pb) = items[i], items[j]
            if ea == eb:
                continue
            pairs += 1
            correct += (pa < pb) == (ea < eb)

    # cerințe dure
    prag = cfg.priority.risc_credit.blocheaza_retentia_daca
    loans = {l["loan_id"]: l for l in pf.loans}
    hard = {
        "risc_mare_cu_retentie": [c["case_id"] for c in cases
                                  if c["scoruri"]["risc_credit"] >= prag and c["actiune_propusa"] == "retentie_refinantare"],
        "blocate_cu_oferta": [c["case_id"] for c in cases
                              if c["blocaje"] and not c["actiune_propusa"].startswith("task_")],
        "expirare_sub_30_zile_nu_P1": [],
    }
    for c in cases:
        l = loans.get(c["loan_id"])
        exp = parse_date(l.get("dobanda_fixa_expira_la")) if l else None
        if exp and l["tip_dobanda"] == "fixa" and pf.today <= exp < pf.today + timedelta(days=30) and c["banda"] != bands[0]:
            hard["expirare_sub_30_zile_nu_P1"].append(c["case_id"])

    return {"benzi": {"acuratete": ok_band / len(gt), "matrice_confuzie": conf},
            "actiuni": {"acuratete": ok_act / len(gt)},
            "ordonare": {"perechi": pairs, "corecte": correct, "pairwise_accuracy": correct / pairs if pairs else 1.0},
            "cerinte_dure": {k: {"incalcari": len(v), "cazuri": v} for k, v in hard.items()}}


def check_traps(cases: list[dict], pf: Portfolio) -> dict:
    """Cazurile-capcană din §8 (pozițiile din primul bloc de 50 de scenarii)."""
    cid = {k: f"C{i + 1:04d}" for k, i in TRAP_INDEX.items()}
    by_client = defaultdict(list)
    for c in cases:
        by_client[c["client_id"]].append(c)
    out = {}
    a = by_client[cid["capcana_a"]]
    out["a_expirare_si_intarziere_restructurare"] = bool(a) and all(
        c["actiune_propusa"] == "restructurare_preventiva" for c in a)
    b = by_client[cid["capcana_b"]]
    out["b_plecare_mare_sold_mic_P3"] = bool(b) and all(c["banda"] == "P3" for c in b)
    out["c_platinum_fara_semnale_absent"] = not by_client[cid["capcana_c"]]
    d = by_client[cid["capcana_d"]]
    out["d_ci_expirata_cerere_P1_blocat"] = bool(d) and all(
        c["banda"] == "P1" and "ci_expirata" in c["blocaje"] and c["actiune_propusa"] == "task_ci_expirata" for c in d)
    e = by_client[cid["capcana_e"]]
    req = next((r for r in pf.requests if r["client_id"] == cid["capcana_e"] and r["tip"] == "adeverinta_sold"), None)
    out["e_cerere_atasata_fara_dublura"] = bool(req) and len(e) == 1 and e[0]["request_id"] == req["request_id"]
    return {"clienti": cid, "rezultate": out}


def timed_run(data_dir: Path | str, cfg: Config) -> tuple[float, int, int, list[dict], list[dict], Portfolio]:
    t0 = time.perf_counter()
    pf = load_portfolio(data_dir)
    det = run_scan(pf, cfg)
    res = build_queue(pf, cfg, det, run_intake(pf, cfg))
    return time.perf_counter() - t0, len(pf.clients), len(res.cases), det, res.cases, pf


def main(argv: list[str] | None = None) -> None:
    setup_console()
    ap = argparse.ArgumentParser(description="Evaluează scanarea și coada față de ground truth.")
    ap.add_argument("--data-dir", default=str(DATA_DIR))
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ap.add_argument("--config-dir", default=str(CONFIG_DIR))
    ap.add_argument("--scale", type=int, default=0, help="nr. clienți pentru testul de scalare (ex. 5000; 0 = fără)")
    a = ap.parse_args(argv)

    cfg = load_config(a.config_dir)
    secs, n_cli, n_cases, det, cases, pf = timed_run(a.data_dir, cfg)
    gt = read_json(Path(a.data_dir) / "ground_truth.json")

    detection = eval_detection(det, gt, cfg)
    inflows = eval_inflows(pf, cfg)
    queue = eval_queue(cases, gt, pf, cfg)
    traps = check_traps(cases, pf) if len(pf.clients) >= len(SCENARIOS) else {"rezultate": {}}
    timing = {"clienti_50": {"clienti": n_cli, "cazuri": n_cases, "secunde": round(secs, 3)}}

    if a.scale:
        sdir = Path(a.out_dir) / f"scale_{a.scale}"
        t0 = time.perf_counter()
        generate(a.scale, 42, pf.today.isoformat(), sdir)
        gen_s = time.perf_counter() - t0
        s_secs, s_cli, s_cases, *_ = timed_run(sdir, cfg)
        timing[f"clienti_{a.scale}"] = {"clienti": s_cli, "cazuri": s_cases, "secunde": round(s_secs, 3),
                                        "generare_secunde": round(gen_s, 3)}

    report = {"detectie": detection, "clasificare_tranzactii": inflows, **queue, "capcane": traps, "timp": timing}
    write_json(Path(a.out_dir) / "evaluation.json", report)

    # ---------------- consolă
    print("═══ Detecție semnale (precizie / recall / F1)")
    print(f"  {'semnal':<26} {'TP':>3} {'FP':>3} {'FN':>3} {'P':>6} {'R':>6} {'F1':>6}")
    for sid, m in detection["per_semnal"].items():
        print(f"  {sid:<26} {m['tp']:>3} {m['fp']:>3} {m['fn']:>3} {m['precizie']:>6.2f} {m['recall']:>6.2f} {m['f1']:>6.2f}")
    g = detection["global"]
    print(f"  {'GLOBAL':<26} {g['tp']:>3} {g['fp']:>3} {g['fn']:>3} {g['precizie']:>6.2f} {g['recall']:>6.2f} "
          f"{g['f1']:>6.2f}   (țintă F1 ≥ 0.90: {'OK' if g['f1'] >= 0.9 else 'NU'})")

    print("\n═══ Tipul tranzacțiilor dedus din recurență + regex (vs tip_etichetat)")
    for k, m in inflows.items():
        print(f"  {k:<20} n={m['n']:<4} P={m['precizie']:.2f} R={m['recall']:.2f} F1={m['f1']:.2f}")

    print(f"\n═══ Benzi (cazul de top al fiecărui client): acuratețe {queue['benzi']['acuratete']:.0%}")
    labels = list(queue["benzi"]["matrice_confuzie"])
    print("  așteptat \\ obținut  " + " ".join(f"{l:>4}" for l in labels))
    for e, row in queue["benzi"]["matrice_confuzie"].items():
        print(f"  {e:<19} " + " ".join(f"{row[l]:>4}" for l in labels))
    print(f"═══ Acțiuni: acuratețe {queue['actiuni']['acuratete']:.0%}")
    o = queue["ordonare"]
    print(f"═══ Ordonare: {o['corecte']}/{o['perechi']} perechi corecte (pairwise accuracy {o['pairwise_accuracy']:.0%})")

    print("\n═══ Cerințe dure")
    for k, v in queue["cerinte_dure"].items():
        print(f"  {k:<30} încălcări: {v['incalcari']}" + (f"  {v['cazuri']}" if v["cazuri"] else ""))
    if traps["rezultate"]:
        print("═══ Cazuri-capcană")
        for k, v in traps["rezultate"].items():
            print(f"  {'✔' if v else '✘'} {k}")

    print("\n═══ Timp (generare exclusă; scan + intake + coadă)")
    for k, v in timing.items():
        extra = f", generare {v['generare_secunde']:.1f}s" if "generare_secunde" in v else ""
        print(f"  {v['clienti']:>5} clienți → {v['cazuri']:>5} cazuri în {v['secunde']:.2f}s{extra}")
    print(f"\n→ {a.out_dir}/evaluation.json")
    log_event(a.out_dir, "evaluate", "done", f1=round(g["f1"], 4), acuratete_benzi=queue["benzi"]["acuratete"],
              timp=timing)


if __name__ == "__main__":
    main()
