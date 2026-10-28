"""Bucla de feedback: ce a propus agentul vs. ce a decis consilierul vs. ce s-a întâmplat la 90 de zile.

    python -m retailagent.feedback [--out-dir out]        # out/feedback.json + raport în consolă

Din `approvals.json` (ultima decizie per caz, cu `consilier`, `motiv`, `rezultat`) și `recommendations.json` /
`offers.json` (ce a propus agentul, p_după prezis, nivel, produs) se calculează: rata de override pe intervenție /
nivel / produs / consilier, înlocuirile cele mai frecvente (agent → final), cuvintele-cheie din motive, rezultatele
reale la 90 de zile față de predicție (calibrare reală) și **propuneri de ajustare** — sugestii, nu modificări
automate. Rezultatele devin eticheta reală pentru `churn.train --din-approvals`.
"""
from __future__ import annotations

import argparse
import re
from collections import Counter, defaultdict
from pathlib import Path

from .common import OUT_DIR, fmt_ron, read_json, setup_console, write_json

STOP = {"si", "și", "de", "la", "cu", "pe", "in", "în", "a", "al", "ai", "ale", "e", "este", "un", "o", "nu", "ca", "că", "sa", "să",
        "pentru", "din", "are", "mai", "dar", "care", "clientul", "clientului", "vrea", "prefera", "preferă", "ne", "se", "fi"}


def _ultimele(approvals: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for a in approvals:
        out[a["case_id"]] = a                       # lista e cronologică: ultima rămâne
    return out


def _rata(parte: int, total: int) -> float | None:
    return round(parte / total, 4) if total else None


def raport_feedback(approvals: list[dict], recs: list[dict], offers: list[dict], min_cazuri: int = 3) -> dict:
    by_rec = {r["case_id"]: r for r in recs}
    by_offer = {o["case_id"]: o for o in offers}
    dec = _ultimele(approvals)
    n = len(dec)
    overrides = [d for d in dec.values() if d.get("override")]

    def grup(cheie):
        tot, ov = Counter(), Counter()
        for cid, d in dec.items():
            k = cheie(cid, d)
            if k is None:
                continue
            tot[k] += 1
            ov[k] += int(bool(d.get("override")))
        return {k: {"decizii": tot[k], "override": ov[k], "rata_override": _rata(ov[k], tot[k])} for k in sorted(tot, key=lambda x: -tot[x])}

    pe_interventie = grup(lambda cid, d: d.get("interventie_agent") or d.get("recomandare_agent"))
    pe_nivel = grup(lambda cid, d: by_offer.get(cid, {}).get("nivel_relatie"))
    pe_produs = grup(lambda cid, d: by_rec.get(cid, {}).get("produs"))
    pe_consilier = grup(lambda cid, d: d.get("consilier"))
    inlocuiri = Counter((d.get("interventie_agent") or d.get("recomandare_agent"), d.get("interventie_finala") or d["decizie"])
                        for d in overrides)
    cuvinte = Counter()
    for d in overrides:
        for w in re.findall(r"[a-zăâîșț]{3,}", (d.get("motiv") or "").lower()):
            if w not in STOP:
                cuvinte[w] += 1

    # rezultate la 90 de zile: rata reală de rămânere vs. predicția (1 − p_după a intervenției finale)
    cu_rez = [d for d in dec.values() if d.get("rezultat") in ("ramas", "plecat")]
    rez: dict[str, dict] = defaultdict(lambda: {"n": 0, "ramasi": 0, "p_ramanere_prezis": []})
    for d in cu_rez:
        iv = d.get("interventie_finala") or "nu_interveni"
        o = by_offer.get(d["case_id"])
        it = next((i for i in (o or {}).get("interventii", []) if i["id"] == iv), None)
        r = rez[iv]
        r["n"] += 1
        r["ramasi"] += int(d["rezultat"] == "ramas")
        if it:
            r["p_ramanere_prezis"].append(1 - it["p_dupa"])
    rezultate = {k: {"n": v["n"], "ramasi": v["ramasi"], "rata_ramanere_reala": _rata(v["ramasi"], v["n"]),
                     "rata_ramanere_prezisa": round(sum(v["p_ramanere_prezis"]) / len(v["p_ramanere_prezis"]), 4) if v["p_ramanere_prezis"] else None}
                 for k, v in rez.items()}

    propuneri = []
    for iv, g in pe_interventie.items():
        if g["decizii"] >= min_cazuri and (g["rata_override"] or 0) >= 0.5:
            inloc = Counter({b: c for (a, b), c in inlocuiri.items() if a == iv}).most_common(1)
            cu = f", cel mai des înlocuită cu {inloc[0][0]} ({inloc[0][1]}×)" if inloc else ""
            propuneri.append({"tip": "override_frecvent", "interventie": iv,
                              "text": f"{iv} e schimbată de consilieri în {g['rata_override']:.0%} din {g['decizii']} cazuri{cu}: "
                                      "revizuiește parametrii ei în retention.yaml (cost, efect_scor) sau constrângerile care o aleg"})
    for iv, g in rezultate.items():
        if g["n"] >= min_cazuri and g["rata_ramanere_prezisa"] is not None and g["rata_ramanere_reala"] is not None \
                and g["rata_ramanere_prezisa"] - g["rata_ramanere_reala"] > 0.15:
            propuneri.append({"tip": "supraestimare_retentie", "interventie": iv,
                              "text": f"pentru {iv} modelul prezicea {g['rata_ramanere_prezisa']:.0%} rămânere, real {g['rata_ramanere_reala']:.0%} "
                                      f"pe {g['n']} cazuri: reantrenează pe rezultate (churn.train --din-approvals) sau scade efect_scor"})
    if cuvinte:
        top = ", ".join(f"{w} ({c})" for w, c in cuvinte.most_common(5))
        propuneri.append({"tip": "motive", "interventie": None, "text": f"cuvintele-cheie din motivele override-urilor: {top}"})
    if len(cu_rez) < 200:
        propuneri.append({"tip": "date", "interventie": None,
                          "text": f"{len(cu_rez)} rezultate la 90 de zile înregistrate; reantrenarea pe date reale cere ≥ 200 (churn.train --din-approvals)"})

    return {"decizii": n, "override": len(overrides), "rata_override": _rata(len(overrides), n),
            "pe_interventie": pe_interventie, "pe_nivel": pe_nivel, "pe_produs": pe_produs, "pe_consilier": pe_consilier,
            "inlocuiri": [{"agent": a, "final": b, "n": c} for (a, b), c in inlocuiri.most_common()],
            "cuvinte_cheie": cuvinte.most_common(10), "rezultate_90_zile": {"n": len(cu_rez), "pe_interventie": rezultate},
            "propuneri": propuneri}


def print_feedback(f: dict) -> None:
    print(f"═══ Feedback: {f['decizii']} decizii, {f['override']} override-uri ({(f['rata_override'] or 0):.0%})")
    for nume, g in (("intervenție", f["pe_interventie"]), ("nivel", f["pe_nivel"]), ("produs", f["pe_produs"]), ("consilier", f["pe_consilier"])):
        if g:
            print(f"  pe {nume}: " + ", ".join(f"{k} {v['override']}/{v['decizii']}" for k, v in g.items()))
    if f["inlocuiri"]:
        print("  înlocuiri: " + ", ".join(f"{x['agent']}→{x['final']} ({x['n']})" for x in f["inlocuiri"][:6]))
    r = f["rezultate_90_zile"]
    if r["n"]:
        print(f"  rezultate la 90 de zile ({r['n']}): " + ", ".join(
            f"{k}: real {v['rata_ramanere_reala']:.0%} vs prezis {v['rata_ramanere_prezisa']:.0%} (n={v['n']})" if v["rata_ramanere_prezisa"] is not None
            else f"{k}: real {v['rata_ramanere_reala']:.0%} (n={v['n']})" for k, v in r["pe_interventie"].items()))
    print("  propuneri:")
    for p in f["propuneri"]:
        print(f"    • {p['text']}")


def main(argv: list[str] | None = None) -> None:
    setup_console()
    ap = argparse.ArgumentParser(description="Raportul de feedback: agent vs consilier vs rezultat la 90 de zile.")
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    a = ap.parse_args(argv)
    out = Path(a.out_dir)
    approvals = read_json(out / "approvals.json") if (out / "approvals.json").exists() else []
    recs = read_json(out / "recommendations.json") if (out / "recommendations.json").exists() else []
    offers = read_json(out / "offers.json") if (out / "offers.json").exists() else []
    if not approvals:
        print("Nicio decizie înregistrată încă (out/approvals.json lipsește sau e gol). Aprobă / modifică / respinge câteva cazuri "
              "cu `python -m retailagent.approve` sau din interfață, apoi rulează din nou.")
        return
    f = raport_feedback(approvals, recs, offers)
    write_json(out / "feedback.json", f)
    print_feedback(f)
    print(f"→ {out}/feedback.json")


if __name__ == "__main__":
    main()
