"""Aprobarea consilierului (MODEL_FINAL §4): agentul recomandă, omul decide.

    python -m retailagent.approve Q0001                                   # aprobă recomandarea
    python -m retailagent.approve Q0001 --decizie modifica --interventie fix_1_an --motiv "..."
    python -m retailagent.approve Q0001 --decizie respinge --motiv "..."

`modifica` și `respinge` cer obligatoriu un motiv; override-ul intră în out/audit.jsonl. Citește
out/recommendations.json și out/offers.json (produse de `recommend`). Motivul e text: se scrie ca string JSON,
nu se interpretează.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from .common import CONFIG_DIR, DATA_DIR, OUT_DIR, fmt_ron, read_json, setup_console, write_json
from .config_loader import Config, load_config
from .recommend import ETICHETA, oferta_din_interventie
from .scan import load_portfolio

DECIZII = ("aproba", "modifica", "respinge")
TITLU = {"aproba": "APROBAT", "modifica": "MODIFICAT (override)", "respinge": "RESPINS (override)"}


class ApprovalError(ValueError):
    """Decizie invalidă: lipsește motivul, intervenția nu există sau nu e fezabilă."""


REZULTATE = ("ramas", "plecat")


def decide(rec: dict, offer: dict, decizie: str, interventie: str | None, motiv: str | None, cfg: Config,
           now: datetime, data_dir: Path | str = DATA_DIR, consilier: str | None = None) -> dict:
    """Validează decizia consilierului și construiește înregistrarea de aprobare (pur, fără I/O de scriere)."""
    if decizie not in DECIZII:
        raise ApprovalError(f"decizia trebuie să fie una din {DECIZII}, nu {decizie!r}")
    ids = {c.id for c in cfg.echipa.consilieri}
    if consilier is None:
        consilier = cfg.echipa.pentru(rec["client_id"])
    elif consilier not in ids:
        raise ApprovalError(f"consilierul {consilier!r} nu e în echipa.yaml: " + ", ".join(sorted(ids)))
    motiv = (motiv or "").strip()
    if decizie in ("modifica", "respinge") and not motiv:
        raise ApprovalError(f"decizia '{decizie}' e un override: cere obligatoriu --motiv")
    by_id = {i["id"]: i for i in offer["interventii"]}
    finala, oferta, grafic = rec["interventie"], rec["oferta"], rec["grafic"]
    if decizie == "modifica":
        if not interventie:
            raise ApprovalError("decizia 'modifica' cere --interventie <id din meniu>")
        if interventie not in by_id:
            raise ApprovalError(f"intervenția {interventie!r} nu există în meniu: " + ", ".join(by_id))
        it = by_id[interventie]
        if not it["fezabil"]:
            raise ApprovalError(f"intervenția {interventie!r} nu e fezabilă: {it['motiv_infezabil']}")
        finala = interventie
        pf = load_portfolio(data_dir)
        loan = next((l for l in pf.loans if l["loan_id"] == rec["loan_id"]), None)
        oferta, grafic = oferta_din_interventie(loan, it, pf.today, pf.market, cfg) if loan else (None, None)
    elif decizie == "respinge":
        finala, oferta, grafic = None, None, None
    return {"timestamp": now.isoformat(timespec="seconds"), "case_id": rec["case_id"], "client_id": rec["client_id"],
            "loan_id": rec["loan_id"], "consilier": consilier, "decizie": decizie, "override": decizie != "aproba",
            "recomandare_agent": rec["recomandare"], "interventie_agent": rec["interventie"],
            "interventie_finala": finala, "motiv": motiv or None, "oferta": oferta, "grafic": grafic,
            "documente_lipsa": rec["documente_lipsa"], "rezultat": None, "rezultat_la": None,
            "versiune": rec.get("versiune")}


def inregistreaza_rezultat(case_id: str, rezultat: str, now: datetime, out_dir: Path | str = OUT_DIR) -> dict:
    """Rezultatul la 90 de zile (a rămas / a plecat) pe ultima decizie a cazului: închide bucla de feedback și
    devine eticheta reală pentru reantrenarea modelului de churn (`churn.train --din-approvals`)."""
    if rezultat not in REZULTATE:
        raise ApprovalError(f"rezultatul trebuie să fie unul din {REZULTATE}, nu {rezultat!r}")
    out = Path(out_dir)
    path = out / "approvals.json"
    rows = read_json(path) if path.exists() else []
    idx = next((i for i in range(len(rows) - 1, -1, -1) if rows[i]["case_id"] == case_id), None)
    if idx is None:
        raise ApprovalError(f"cazul {case_id} nu are nicio decizie înregistrată; întâi aprobă / modifică / respinge")
    rows[idx]["rezultat"] = rezultat
    rows[idx]["rezultat_la"] = now.isoformat(timespec="seconds")
    write_json(path, rows)
    row = {"timestamp": rows[idx]["rezultat_la"], "case_id": case_id, "client_id": rows[idx]["client_id"], "tip": "rezultat",
           "cheie": "rezultat_90_zile", "valoare": rezultat, "sursa": "consilier", "consilier": rows[idx].get("consilier"),
           "interventie_finala": rows[idx].get("interventie_finala")}
    with open(out / "audit.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return rows[idx]


def persist(d: dict, out_dir: Path | str = OUT_DIR) -> None:
    """Adaugă decizia în out/approvals.json și un rând de aprobare / override în out/audit.jsonl."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "approvals.json"
    rows = read_json(path) if path.exists() else []
    rows.append(d)
    write_json(path, rows)
    row = {"timestamp": d["timestamp"], "case_id": d["case_id"], "client_id": d["client_id"],
           "tip": "override" if d["override"] else "aprobare", "cheie": "interventie", "valoare": d["interventie_finala"],
           "sursa": "consilier", "consilier": d.get("consilier"), "decizie": d["decizie"], "motiv": d["motiv"],
           "versiune": d.get("versiune")}
    if d.get("propunere_llm"):
        row["propunere_llm"] = d["propunere_llm"]       # textul generat de agentul LLM pe care s-a bazat decizia
    with open(out / "audit.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def print_decision(rec: dict, d: dict) -> None:
    print(f"═══ {d['case_id']} · {d['client_id']} · {rec['loan_id'] or 'fără credit'} · {TITLU[d['decizie']]} · {d['timestamp']} · consilier {d.get('consilier')}")
    print(f"  recomandarea agentului: {ETICHETA[rec['recomandare']]}" + (f" · {rec['interventie']}" if rec["interventie"] else ""))
    if d["override"]:
        print(f"  override: {d['decizie']} → {d['interventie_finala'] or '—'} · motiv: {d['motiv']}")
    print(f"  {rec['explicatie']}")
    o = d["oferta"]
    if o:
        print("\n── Oferta")
        for k in ("tip", "produs", "suma", "dobanda_noua", "marja_noua", "perioada", "dupa_perioada", "rata_veche", "rata_noua",
                  "cost_banca", "economie_client", "conditie", "scutire_ron", "sold_dupa_pauza"):
            if o.get(k) is not None:
                v = o[k]
                print(f"  {k:<16} {fmt_ron(v) + ' RON' if k in ('suma', 'rata_veche', 'rata_noua', 'cost_banca', 'economie_client', 'scutire_ron', 'sold_dupa_pauza') else v}")
    g = d["grafic"]
    if g:
        print(f"\n── Grafic (primele 12 luni din {g['nr_rate']}; dobândă totală {fmt_ron(g['dobanda_totala'])} RON)")
        print(f"  {'nr':>3} {'luna':<8} {'rata':>10} {'dobândă':>10} {'principal':>10} {'sold rămas':>12}")
        for r in g["primele_luni"]:
            print(f"  {r['nr']:>3} {r['luna']:<8} {fmt_ron(r['rata']):>10} {fmt_ron(r['dobanda']):>10} {fmt_ron(r['principal']):>10} {fmt_ron(r['sold_ramas']):>12}")
    if d["documente_lipsa"]:
        print("\n── Documente de adus")
        for doc in d["documente_lipsa"]:
            print(f"  • {doc['tip']}: {doc['motiv']}")
    elif d["decizie"] != "respinge":
        print("\n── Documente: dosarul e complet")


def main(argv: list[str] | None = None) -> None:
    setup_console()
    ap = argparse.ArgumentParser(description="Consilierul aprobă / modifică / respinge recomandarea agentului.")
    ap.add_argument("case_id")
    ap.add_argument("--decizie", choices=DECIZII, default="aproba")
    ap.add_argument("--interventie", help="id din meniu (pentru --decizie modifica)")
    ap.add_argument("--motiv", help="obligatoriu pentru modifica / respinge")
    ap.add_argument("--consilier", help="id din config/echipa.yaml (implicit: cel alocat clientului)")
    ap.add_argument("--rezultat", choices=REZULTATE, help="doar înregistrează rezultatul la 90 de zile pe ultima decizie a cazului")
    ap.add_argument("--data-dir", default=str(DATA_DIR))
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ap.add_argument("--config-dir", default=str(CONFIG_DIR))
    a = ap.parse_args(argv)

    out = Path(a.out_dir)
    if a.rezultat:
        try:
            r = inregistreaza_rezultat(a.case_id, a.rezultat, datetime.now(), out)
        except ApprovalError as e:
            raise SystemExit(f"Rezultat refuzat: {e}") from e
        print(f"═══ {a.case_id} · rezultat la 90 de zile: {r['rezultat'].upper()} ({r['rezultat_la']}) · decizia: {r['decizie']}"
              f" → {r['interventie_finala'] or '—'} · consilier {r.get('consilier')}")
        print(f"→ {out}/approvals.json, {out}/audit.jsonl")
        return
    if not (out / "recommendations.json").exists() or not (out / "offers.json").exists():
        raise SystemExit(f"Lipsesc {out}/recommendations.json sau offers.json: rulează întâi `python -m retailagent.recommend`.")
    rec = next((r for r in read_json(out / "recommendations.json") if r["case_id"] == a.case_id), None)
    offer = next((o for o in read_json(out / "offers.json") if o["case_id"] == a.case_id), None)
    if rec is None or offer is None:
        raise SystemExit(f"Cazul {a.case_id} nu există în recomandări.")
    try:
        d = decide(rec, offer, a.decizie, a.interventie, a.motiv, load_config(a.config_dir), datetime.now(), a.data_dir, a.consilier)
    except ApprovalError as e:
        raise SystemExit(f"Decizie refuzată: {e}") from e
    persist(d, out)
    print_decision(rec, d)
    print(f"\n→ {out}/approvals.json, {out}/audit.jsonl")


if __name__ == "__main__":
    main()
