"""Agentul LLM de ofertare (pasul 3): decide oferta în constrângeri și scrie textul în limbaj uman.

Cum lucrează, pe scurt:
1. Constrângerile rămân la motor. Agentul primește doar `optiuni`: intervențiile din meniu care sunt fezabile
   (DTI, LTV, vârstă, marjă minimă, buget pe nivel), aduc p sub țintă și costă ≤ p×V, plafonate la
   `cost_max_fata_de_motor` × costul alegerii motorului. Cazurile blocate, escaladate, cu risc de credit sau fără
   nevoie de ofertă nu primesc opțiuni: agentul doar explică decizia motorului.
2. Contextul trimis modelului conține doar fapte calculate (cifre, id-uri, etichete din config). Fără nume, fără
   texte libere din date (dovezile semnalelor pot conține nume de comercianți sau bănci), deci fără injecție de prompt.
3. Răspunsul vine ca apel de tool cu schemă strictă: `interventie` e un enum din `optiuni`. Textele sunt verificate:
   fiecare număr citat trebuie să existe în fapte (mesajul către client: doar în faptele publice ale ofertei alese),
   termenii interziși (bănci concurente, promisiuni, cifre interne) resping textul. Un răspuns respins primește
   `reincercari` încercări cu motivul respingerii; apoi agentul cade pe un text-șablon determinist.
4. Fără cheie, cu `activat: false` sau la eroare de rețea, rezultatul e tot complet, din șablon, marcat `sursa: sablon`.

Configurația stă în config/llm.yaml (validată ca restul regulilor); cheia doar în mediu sau în .env (ignorat de git).
`python -m retailagent.llm --verifica` arată furnizorul, modelul, dacă există cheia și face un apel de probă.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import quote

import httpx

from .config_loader import LlmConfig

SCHEMA_VERSIUNE = "2"                     # crește când se schimbă forma contextului sau a răspunsului
STARI_CU_OFERTA = ("oferta_minima", "oferta_produs")
CHEI = {"anthropic": "ANTHROPIC_API_KEY", "bedrock": "AWS_BEARER_TOKEN_BEDROCK", "openai": "OPENAI_API_KEY"}
NICIUNA = "niciuna"


class LLMError(ValueError):
    """Eroare la apelul către model (cheie, rețea, răspuns incomplet). Mesajul nu conține niciodată cheia."""


# ---------------------------------------------------------------- configurare (mediu + .env)

def configurare() -> dict[str, str]:
    """.env simplu KEY=VALUE din rădăcina proiectului, fără execuție sau interpolare; mediul are prioritate."""
    path = Path(__file__).resolve().parents[1] / ".env"
    values: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
            values[key.strip()] = value
    return {**values, **os.environ}


def furnizor_si_model(cfg: LlmConfig, env: dict[str, str]) -> tuple[str, str]:
    furnizor = env.get("RETAILAGENT_LLM_PROVIDER", "").strip() or cfg.furnizor
    if furnizor not in CHEI:
        raise LLMError(f"RETAILAGENT_LLM_PROVIDER must be one of {', '.join(CHEI)}.")
    model = env.get("RETAILAGENT_LLM_MODEL", "").strip()
    if not model and furnizor == "bedrock":
        model = env.get("BEDROCK_MODEL_ID", "").strip()
    return furnizor, model or cfg.modele.get(furnizor, "")


def hash_prompt(cfg: LlmConfig) -> str:
    """Versiunea promptului: intră în `versiune.prompturi` și în fiecare propunere / rând de audit."""
    return hashlib.sha256((SCHEMA_VERSIUNE + "\n" + cfg.prompt).encode("utf-8")).hexdigest()[:12]


def stare_llm(cfg: LlmConfig, env: dict[str, str] | None = None) -> dict:
    """Ce vede interfața: agentul e activ, cu ce model, și dacă există o cheie (fără s-o arate)."""
    env = configurare() if env is None else env
    try:
        furnizor, model = furnizor_si_model(cfg, env)
    except LLMError as e:
        return {"activat": False, "furnizor": None, "model": None, "cheie": False, "mod": "sablon", "motiv": str(e)}
    cheie = bool(env.get(CHEI[furnizor], "").strip())
    mod = "llm" if cfg.activat and cheie else "sablon"
    motiv = None if mod == "llm" else ("disabled in llm.yaml" if not cfg.activat else f"{CHEI[furnizor]} is not set")
    return {"activat": cfg.activat, "furnizor": furnizor, "model": model, "cheie": cheie, "mod": mod, "motiv": motiv,
            "prompt_hash": hash_prompt(cfg), "limba_client": cfg.limba_client}


# ---------------------------------------------------------------- opțiunile admisibile (constrângerile)

def optiuni_admisibile(caz: dict, offer_full: dict | None, cfg: LlmConfig) -> list[dict]:
    """Intervențiile între care agentul are voie să aleagă; alegerea motorului e prima. Listă goală = fără decizie."""
    rec = caz["rec"]
    motor = rec.get("interventie")
    if (rec.get("recomandare") not in STARI_CU_OFERTA or not motor or caz["case"].get("blocaje")
            or caz["check"].get("verificare_picata") or not offer_full):
        return []
    by_id = {i["id"]: i for i in offer_full.get("interventii", [])}
    if motor not in by_id:
        return []
    plafon = max(by_id[motor]["cost"], 0.0) * cfg.cost_max_fata_de_motor
    alte = [i for i in offer_full["interventii"]
            if i["id"] not in (motor, "nu_interveni") and i.get("fezabil") and i.get("respecta_tinta") and i.get("merita")
            and i.get("cost", 0) <= plafon]
    return [by_id[motor]] + sorted(alte, key=lambda i: i["cost"])


def _ani(perioada: str | None) -> int | None:
    m = re.match(r"^(\d+)\s+an", perioada or "")
    return int(m.group(1)) if m else None


def _oferta_fapte(o: dict | None) -> dict | None:
    """Cifrele publice ale unei oferte (cele care pot ajunge la client), rotunjite cum se citează."""
    if not o:
        return None
    f = {"tip": o.get("tip"), "dobanda_noua_pct": round(float(o.get("dobanda_noua") or 0), 2), "perioada": o.get("perioada")}
    if _ani(o.get("perioada")):
        f["ani_perioada"] = _ani(o.get("perioada"))
    # rata_veche = ce plătește clientul azi; rata_dupa_fixa = cât ar plăti fără ofertă după ce se termină fixa curentă
    for k in ("rata_veche", "rata_noua", "rata_dupa_fixa", "economie_client", "scutire_ron"):
        if isinstance(o.get(k), (int, float)) and not isinstance(o.get(k), bool):
            f[f"{k}_ron"] = round(float(o[k]))
    if f.get("rata_veche_ron") and f.get("rata_noua_ron") and f["rata_veche_ron"] > f["rata_noua_ron"]:
        f["scadere_rata_lunara_ron"] = f["rata_veche_ron"] - f["rata_noua_ron"]
    if o.get("rata_dupa_fixa") and o.get("fixa_expira"):
        f["fixa_actuala_expira"] = str(o["fixa_expira"])[:10]
        if isinstance(o.get("dobanda_dupa_fixa"), (int, float)):
            f["dobanda_dupa_fixa_actuala_pct"] = round(float(o["dobanda_dupa_fixa"]), 2)
    if o.get("economie_orizont_luni"):
        f["economie_in_ani"] = round(o["economie_orizont_luni"] / 12, 1)
    m = re.search(r"=\s*(\d+(?:\.\d+)?)%", o.get("dupa_perioada") or "")
    if m:
        f["dobanda_dupa_perioada_pct"] = float(m.group(1))
    if o.get("conditie"):
        f["conditie"] = o["conditie"]
    return f


def _oferta_pentru(it: dict, caz: dict, pf, cfg_full) -> dict | None:
    """Oferta concretă a unei intervenții: a motorului vine din recomandare, alternativele se calculează la fel ca la
    decizia „modifică” (approve.decide → recommend.oferta_din_interventie)."""
    if it["id"] == caz["rec"].get("interventie"):
        return caz["rec"].get("oferta")
    if pf is None or cfg_full is None:
        return None
    from .recommend import oferta_din_interventie
    loan = next((l for l in pf.loans if l["loan_id"] == caz["case"]["loan_id"]), None)
    return oferta_din_interventie(loan, it, pf.today, pf.market, cfg_full)[0] if loan else None


def _pct(x) -> float | None:
    return round(float(x) * 100, 1) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def context_agent(caz: dict, offer_full: dict | None, pf=None, cfg_full=None, cfg: LlmConfig | None = None) -> dict:
    """Faptele trimise modelului (și singura sursă a cifrelor din text). Fără nume, fără dovezi în text liber."""
    cfg = cfg or (cfg_full.llm if cfg_full is not None else LlmConfig(activat=False))
    rec, cs, ch, of = caz["rec"], caz["case"], caz["check"], caz["offer"]
    conc, leg, loan = ch.get("concluzii") or {}, of.get("legaturi") or {}, caz.get("loan") or {}
    sig_cfg = cfg_full.signals.by_id() if cfg_full is not None else {}
    optiuni = []
    for it in optiuni_admisibile(caz, offer_full, cfg):
        fapte = _oferta_fapte(_oferta_pentru(it, caz, pf, cfg_full))
        if fapte is None and it["id"] != rec.get("interventie"):
            continue
        optiuni.append({"id": it["id"], "eticheta": it.get("eticheta", it["id"]), "cost_banca_ron": round(it["cost"]),
                        "p_dupa_pct": _pct(it.get("p_dupa")), "oferta": fapte})
    cheltuieli = (caz.get("cheltuieli") or {}).get("categorii") or []
    p, V = of.get("p"), of.get("V")
    luni = (of.get("B_detalii") or {}).get("luni_ramase")
    zile_expirare = None
    if pf is not None and loan.get("expira"):
        from datetime import date
        try:
            zile_expirare = (date.fromisoformat(str(loan["expira"])[:10]) - pf.today).days
        except ValueError:
            zile_expirare = None
    ctx = {
        "limba_client": cfg.limba_client,
        "caz": {"stare": rec.get("recomandare"), "stare_eticheta": rec.get("eticheta"), "banda": cs.get("banda"),
                "produs": cs.get("produs"), "termen": cs.get("deadline")},
        "client": {"nivel": caz.get("client", {}).get("nivel"), "tipologie": caz.get("client", {}).get("tipologie"),
                   "vechime_ani": leg.get("vechime_ani"), "produse_active": leg.get("produse_active", []),
                   "scor_legaturi": leg.get("scor"), "venit_lunar_ron": round(conc["venit_lunar"]) if conc.get("venit_lunar") else None,
                   "dti_pct": _pct(conc.get("dti_curent")), "ltv_pct": _pct(conc.get("ltv_actual")),
                   "salariu_la_alta_banca": conc.get("salariu_la_alta_banca"),
                   "cheltuieli_top": [{"categorie": c["categorie"], "procent": _pct(c["procent"])} for c in cheltuieli[:3]]},
        "credit": {"sold_ron": loan.get("sold"), "moneda": loan.get("moneda"), "tip_dobanda": loan.get("tip_dobanda"),
                   "dobanda_curenta_pct": loan.get("dobanda"), "dobanda_fixa_expira": loan.get("expira"),
                   "rata_curenta_ron": round(loan["rata"]) if loan.get("rata") else None,
                   "luni_ramase": luni, "ani_ramasi": round(luni / 12) if luni else None,
                   "zile_pana_la_expirare_fixa": zile_expirare if zile_expirare is not None and zile_expirare >= 0 else None,
                   "scadenta": loan.get("scadenta")},
        "semnale": [{"id": s["id"], "familie": s.get("familie"), "scor": s.get("scor"),
                     "descriere": sig_cfg[s["id"]].descriere if s["id"] in sig_cfg else s["id"].replace("_", " ")}
                    for s in cs.get("semnale", [])],
        "risc_plecare": {"p_plecare_pct": _pct(p), "p_tinta_pct": _pct(of.get("p_tinta")),
                         "castig_client_daca_pleaca_ron": round(of["B"]) if of.get("B") is not None else None,
                         "valoare_client_ron": round(V) if V is not None else None,
                         "pierdere_asteptata_ron": round(p * V) if p is not None and V is not None else None},
        "decizie_motor": {"interventie": rec.get("interventie"), "regula": "cheapest admissible option that brings p under target"},
        "optiuni": optiuni,
        "atentionari": atentionari(caz),
    }
    return ctx


def atentionari(caz: dict) -> list[str]:
    """Atenționări obligatorii, calculate în cod; se afișează mereu, indiferent ce scrie modelul."""
    rec, w = caz["rec"], []
    o = rec.get("oferta") or {}
    if o.get("amanata_buget"):
        w.append("Deferred: this month's retention budget is used up; approving it does so explicitly.")
    if rec.get("documente_lipsa"):
        w.append(f"{len(rec['documente_lipsa'])} document(s) to request before the offer goes out.")
    if rec.get("incertitudini"):
        w.append(f"{len(rec['incertitudini'])} check(s) could not be completed; confirm them first.")
    if o.get("conditie"):
        w.append("The offer is conditional; confirm the condition with the client before activation.")
    return w


# ---------------------------------------------------------------- validarea răspunsului

_NUM = re.compile(r"\d+(?:[.,]\d+)*")


def _interpretari(token: str) -> set[float]:
    """„2.479” poate fi 2479 (ro) sau 2.479 (en); „4,90” poate fi 4.90 sau 490. Le păstrăm pe toate."""
    out: set[float] = set()
    for a, b in ((",", "."), (".", ",")):            # a = separator de mii, b = separator zecimal
        t = token.replace(a, "")
        if t.count(b) <= 1:
            try:
                out.add(float(t.replace(b, ".")))
            except ValueError:
                pass
    return out


def numere_din_text(text: str) -> list[tuple[str, set[float]]]:
    res = []
    for m in _NUM.finditer(text or ""):
        if m.start() > 0 and text[m.start() - 1].isalpha():       # P1, IRCC3 etc. nu sunt cifre citate
            continue
        tok = m.group(0).rstrip(".,")
        res.append((tok, _interpretari(tok)))
    return res


def numere_permise(obj) -> set[float]:
    """Toate numerele din fapte (inclusiv cele din șiruri, ex. date și perioade); fracțiile apar și ca procente."""
    out: set[float] = set()
    if isinstance(obj, bool) or obj is None:
        return out
    if isinstance(obj, (int, float)):
        v = float(obj)
        out.add(v)
        if 0 < abs(v) < 1:
            out.add(round(v * 100, 2))
        return out
    if isinstance(obj, str):
        for _, cand in numere_din_text(obj):
            out |= cand
        return out
    if isinstance(obj, dict):
        for v in obj.values():
            out |= numere_permise(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            out |= numere_permise(v)
    return out


def _potrivit(c: float, permise: set[float], tol: float) -> bool:
    for a in permise:
        lim = max(1.0, abs(a) * tol) if abs(a) >= 100 else 0.051
        if abs(c - a) <= lim:
            return True
    return False


def _termen_gasit(text: str, termen: str) -> bool:
    """Acronimele (BCR, ING, OTP) se caută ca cuvânt întreg, cu majuscule; restul, ca început de cuvânt, fără majuscule."""
    if termen.isupper() and len(termen) <= 5:
        return re.search(rf"(?<!\w){re.escape(termen)}(?!\w)", text) is not None
    return re.search(rf"(?<!\w){re.escape(termen)}", text, re.IGNORECASE) is not None


def fapte_client(ctx: dict, interventie: str | None) -> dict:
    """Ce are voie să citeze mesajul către client: creditul și oferta aleasă (fără costul băncii, p, V, scoruri)."""
    opt = next((o for o in ctx["optiuni"] if o["id"] == interventie), None)
    return {"credit": ctx["credit"], "oferta": opt["oferta"] if opt else None}


def puncte_valide(puncte, ctx: dict, cfg: LlmConfig) -> list[str]:
    """Punctele-cheie sunt doar afișare: păstrăm cele care trec aceleași verificări (lungime, termeni, cifre) și
    renunțăm la restul, în loc să respingem tot răspunsul pentru un punct greșit."""
    if not isinstance(puncte, list):
        return []
    permise, ok = numere_permise(ctx), []
    for x in puncte:
        if not isinstance(x, str) or not x.strip() or len(x) > 200:
            continue
        if any(_termen_gasit(x, t) for t in cfg.termeni_interzisi):
            continue
        if any(cand and not any(_potrivit(c, permise, cfg.toleranta_numere) for c in cand) for _, cand in numere_din_text(x)):
            continue
        ok.append(x.strip())
    return ok[:3]


def valideaza(r: dict, ctx: dict, cfg: LlmConfig) -> list[str]:
    """Probleme găsite în răspunsul modelului (listă goală = acceptat). Mesajele sunt în engleză: merg înapoi la model."""
    p: list[str] = []
    ids = [o["id"] for o in ctx["optiuni"]] or [NICIUNA]
    if r.get("interventie") not in ids:
        p.append(f"`interventie` must be one of {ids}.")
    limite = {"motiv_alegere": 600, "argument_consilier": 1200, "mesaj_client": 1500}
    for k, n in limite.items():
        v = r.get(k)
        if not isinstance(v, str) or not v.strip():
            p.append(f"`{k}` is empty.")
        elif len(v) > n:
            p.append(f"`{k}` is longer than {n} characters.")
    puncte = r.get("puncte_cheie") or []
    if not isinstance(puncte, list) or len(puncte) > 3 or any(not isinstance(x, str) or len(x) > 200 for x in puncte):
        p.append("`puncte_cheie` must be at most 3 short strings.")
        puncte = []
    toate = numere_permise(ctx)
    client = numere_permise(fapte_client(ctx, r.get("interventie")))
    texte = {"motiv_alegere": r.get("motiv_alegere") or "", "argument_consilier": r.get("argument_consilier") or "",
             "puncte_cheie": " | ".join(puncte), "mesaj_client": r.get("mesaj_client") or ""}
    for k, text in texte.items():
        for termen in cfg.termeni_interzisi + (cfg.termeni_interzisi_client if k == "mesaj_client" else []):
            if _termen_gasit(text, termen):
                p.append(f"`{k}` contains the forbidden term {termen!r}.")
        permise = client if k == "mesaj_client" else toate
        for tok, cand in numere_din_text(text):
            if cand and not any(_potrivit(c, permise, cfg.toleranta_numere) for c in cand):
                unde = "the client's loan or the chosen offer" if k == "mesaj_client" else "the facts"
                p.append(f"`{k}` cites {tok}, which is not in {unde}.")
    opt = next((o for o in ctx["optiuni"] if o["id"] == r.get("interventie")), None)
    if opt and opt.get("oferta"):
        cheie = [opt["oferta"].get(k) for k in ("rata_noua_ron", "dobanda_noua_pct") if opt["oferta"].get(k)]
        cit = {c for _, cand in numere_din_text(r.get("mesaj_client") or "") for c in cand}
        if cheie and not any(_potrivit(c, {float(x)}, cfg.toleranta_numere) for c in cit for x in cheie):
            p.append("`mesaj_client` must state the chosen offer's new monthly payment or new interest rate.")
    return p


# ---------------------------------------------------------------- textul-șablon (fallback determinist)

def _ron_ro(v) -> str:
    return f"{round(v):,}".replace(",", ".") + " lei"


def _ron_en(v) -> str:
    return f"{round(v):,} RON"


def _pct_ro(v) -> str:
    return f"{v:.2f}".replace(".", ",") + "%"


LUNI = {"ro": ["ianuarie", "februarie", "martie", "aprilie", "mai", "iunie", "iulie", "august", "septembrie", "octombrie",
               "noiembrie", "decembrie"],
        "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
               "November", "December"]}


def _luna(iso: str, limba: str) -> str:
    """„2028-01-03” → „ianuarie 2028” / „January 2028”."""
    try:
        an, luna = int(iso[:4]), int(iso[5:7])
        return f"{LUNI[limba][luna - 1]} {an}"
    except (ValueError, IndexError):
        return iso


def _descriere(o: dict, limba: str) -> str:
    tip, ani, d = o.get("tip"), o.get("ani_perioada"), o.get("dobanda_noua_pct")
    if limba == "ro":
        if tip == "fix_piata" and ani:
            return f"o nouă perioadă de dobândă fixă de {ani} {'an' if ani == 1 else 'ani'}, la {_pct_ro(d)}"
        if tip == "reducere_marja":
            return f"o reducere a marjei, cu o dobândă de {_pct_ro(d)} pe toată durata rămasă"
        if tip == "pachet":
            return f"o dobândă de {_pct_ro(d)} pe toată durata rămasă, dacă salariul este încasat la noi"
        if tip == "comision":
            return "scutirea de comision"
        return f"o ofertă cu dobânda de {_pct_ro(d)}"
    if tip == "fix_piata" and ani:
        return f"a new {ani}-year fixed-rate period at {d:.2f}%"
    if tip == "reducere_marja":
        return f"a margin reduction, at {d:.2f}% for the remaining term"
    if tip == "pachet":
        return f"{d:.2f}% for the remaining term, provided the salary is paid into an account with us"
    if tip == "comision":
        return "a fee waiver"
    return f"an offer at {d:.2f}%"


MESAJ_FARA_OFERTA = {
    "ro": {
        "nu_interveni": "Bună ziua! Am verificat creditul dumneavoastră și condițiile actuale rămân potrivite. "
                        "Dacă doriți o simulare sau aveți întrebări, consilierul dumneavoastră vă stă la dispoziție.",
        "restructurare": "Bună ziua! Am analizat situația creditului dumneavoastră și vă putem prezenta câteva variante "
                         "de ajustare a ratei. Vă invităm să discutați opțiunile cu consilierul dumneavoastră.",
        "blocat": "Bună ziua! Pentru a putea analiza creditul dumneavoastră, avem nevoie să clarificăm câteva aspecte. "
                  "Consilierul dumneavoastră vă va contacta în curând.",
        "respins_escaladat": "Bună ziua! Solicitarea dumneavoastră este în analiză la un specialist. "
                             "Consilierul dumneavoastră vă va contacta cu detaliile.",
        "oferta_minima": "Bună ziua! Am pregătit pentru creditul dumneavoastră o simulare personalizată a ratelor. "
                         "Vă invităm să o parcurgeți împreună cu consilierul dumneavoastră.",
        "oferta_produs": "Bună ziua! Am analizat solicitarea dumneavoastră și am pregătit o ofertă. "
                         "Consilierul dumneavoastră vă va prezenta detaliile.",
    },
    "en": {
        "nu_interveni": "Hello! We have reviewed your loan and your current terms remain suitable. If you would like a "
                        "simulation or have any questions, your advisor is happy to help.",
        "restructurare": "Hello! We have reviewed your loan and can present a few ways to adjust your monthly payment. "
                         "Please talk the options through with your advisor.",
        "blocat": "Hello! Before we can review your loan, we need to clarify a few details. Your advisor will be in touch soon.",
        "respins_escaladat": "Hello! Your request is being reviewed by a specialist. Your advisor will contact you with the details.",
        "oferta_minima": "Hello! We have prepared a personalised simulation of your loan payments. "
                         "Your advisor will be glad to go through it with you.",
        "oferta_produs": "Hello! We have reviewed your request and prepared an offer. Your advisor will present the details.",
    },
}

ARGUMENT_FARA_OFERTA = {
    "nu_interveni": "The engine sees no need for an offer: the client is not likely to leave, so any pricing change would cost the bank for nothing.",
    "restructurare": "The client shows credit-risk signals, so retention offers are not allowed; the engine routes the case to restructuring.",
    "blocat": "The case is blocked (a legal, fraud or process issue); no offer can be made until it is resolved.",
    "respins_escaladat": "A check failed or the case needs a specialist; there is no commercial offer until it is reviewed.",
    "oferta_produs": "The client asked for a new product; the engine prepared the product offer under the usual limits.",
    "oferta_minima": "The engine found no priced intervention to present for this case.",
}


def sablon(ctx: dict, interventie: str | None = None) -> dict:
    """Textul determinist: aceleași câmpuri ca răspunsul modelului, construit doar din fapte."""
    limba = ctx["limba_client"]
    opt = next((o for o in ctx["optiuni"] if o["id"] == interventie), ctx["optiuni"][0] if ctx["optiuni"] else None)
    stare = ctx["caz"]["stare"]
    if not opt or not opt.get("oferta"):
        mesaj = MESAJ_FARA_OFERTA[limba].get(stare, MESAJ_FARA_OFERTA[limba]["nu_interveni"])
        return {"interventie": opt["id"] if opt else NICIUNA,
                "motiv_alegere": "No priced offer: the engine's decision stands." if not opt else "The engine's choice.",
                "argument_consilier": ARGUMENT_FARA_OFERTA.get(stare, ARGUMENT_FARA_OFERTA["oferta_minima"]),
                "mesaj_client": mesaj, "puncte_cheie": []}
    o, r = opt["oferta"], ctx["risc_plecare"]
    ro = limba == "ro"
    mesaj = (f"Bună ziua! Am analizat creditul dumneavoastră și vă putem propune {_descriere(o, 'ro')}. " if ro else
             f"Hello! We have reviewed your loan and can offer you {_descriere(o, 'en')}. ")
    if o.get("rata_noua_ron") and o.get("rata_veche_ron") and o["rata_noua_ron"] < o["rata_veche_ron"]:
        mesaj += (f"Rata lunară ar scădea de la {_ron_ro(o['rata_veche_ron'])} la {_ron_ro(o['rata_noua_ron'])}. " if ro else
                  f"Your monthly payment would drop from {_ron_en(o['rata_veche_ron'])} to {_ron_en(o['rata_noua_ron'])}. ")
    elif o.get("rata_noua_ron"):
        mesaj += (f"Rata lunară ar fi de {_ron_ro(o['rata_noua_ron'])}. " if ro else
                  f"Your monthly payment would be {_ron_en(o['rata_noua_ron'])}. ")
    if o.get("rata_dupa_fixa_ron") and o.get("fixa_actuala_expira") and o["rata_dupa_fixa_ron"] > (o.get("rata_noua_ron") or 0):
        luna = _luna(o["fixa_actuala_expira"], limba)
        mesaj += (f"Fără această ofertă, după încheierea perioadei fixe actuale, din {luna}, rata ar crește la "
                  f"{_ron_ro(o['rata_dupa_fixa_ron'])}. " if ro else
                  f"Without it, once your current fixed period ends in {luna}, the payment would rise to "
                  f"{_ron_en(o['rata_dupa_fixa_ron'])}. ")
    mesaj += ("Vă invităm să discutați detaliile cu consilierul dumneavoastră." if ro else
              "Your advisor will be glad to go through the details with you.")
    descr = _descriere(o, "en")
    arg = (f"{descr[:1].upper() + descr[1:]}. The client would gain {_ron_en(r['castig_client_daca_pleaca_ron'] or 0)} by leaving "
           f"(leave probability {r['p_plecare_pct']}%), an expected loss of {_ron_en(r['pierdere_asteptata_ron'] or 0)}. "
           f"This offer costs the bank {_ron_en(opt['cost_banca_ron'])} and brings the probability to {opt['p_dupa_pct']}%.")
    return {"interventie": opt["id"],
            "motiv_alegere": "Cheapest admissible option that keeps the client (the engine's choice)."
            if opt["id"] == ctx["decizie_motor"]["interventie"] else "Alternative admissible option.",
            "argument_consilier": arg, "mesaj_client": mesaj, "puncte_cheie": []}


# ---------------------------------------------------------------- apelul către model

def schema_raspuns(ctx: dict) -> dict:
    ids = [o["id"] for o in ctx["optiuni"]] or [NICIUNA]
    return {"type": "object", "additionalProperties": False,
            "required": ["interventie", "motiv_alegere", "argument_consilier", "mesaj_client", "puncte_cheie"],
            "properties": {
                "interventie": {"type": "string", "enum": ids, "description": "The chosen option id from `optiuni`."},
                "motiv_alegere": {"type": "string", "description": "English, 1-2 sentences: why this option."},
                "argument_consilier": {"type": "string", "description": "English, 2-4 sentences for the advisor."},
                "mesaj_client": {"type": "string", "description": "Message to the client in `limba_client`, 3-5 sentences."},
                "puncte_cheie": {"type": "array", "items": {"type": "string"}, "description": "Up to 3 short English bullets."},
            }}


def _mesaj_utilizator(ctx: dict, respins: tuple[dict, list[str]] | None) -> str:
    text = "Facts for this case (JSON, computed by the engine):\n" + json.dumps(ctx, ensure_ascii=False, indent=1)
    if respins:
        prev, probleme = respins
        text += ("\n\nYour previous answer was rejected by the bank's validator:\n- " + "\n- ".join(probleme)
                 + "\nPrevious answer:\n" + json.dumps(prev, ensure_ascii=False)
                 + "\nAnswer again, fixing every problem and following all the rules.")
    return text


def apel_model(furnizor: str, cheie: str, model: str, system: str, utilizator: str, schema: dict, cfg: LlmConfig,
               env: dict[str, str]) -> dict:
    """Un apel cu răspuns structurat (tool forțat / json_schema strict). Întoarce obiectul cu câmpurile din schemă."""
    try:
        with httpx.Client(timeout=cfg.timeout_s) as client:
            if furnizor in ("anthropic", "bedrock"):
                body = {"max_tokens": cfg.max_tokens, "system": system,
                        "messages": [{"role": "user", "content": utilizator}],
                        "tools": [{"name": "propune_oferta", "description": "The retention offer decision and texts.",
                                   "input_schema": schema}],
                        "tool_choice": {"type": "tool", "name": "propune_oferta"}}
                if furnizor == "anthropic":
                    baza = env.get("ANTHROPIC_BASE_URL", "").strip().rstrip("/") or "https://api.anthropic.com"
                    if not re.fullmatch(r"https?://[\w.\-]+(?::\d+)?(?:/[\w.\-/]*)?", baza):
                        raise LLMError("ANTHROPIC_BASE_URL is not a valid http(s) URL.")
                    resp = client.post(f"{baza}/v1/messages", json={"model": model, **body}, headers={
                        "x-api-key": cheie, "anthropic-version": "2023-06-01", "content-type": "application/json"})
                else:
                    region = env.get("AWS_REGION", "us-east-1")
                    if not re.fullmatch(r"[a-z]{2}(?:-gov)?-[a-z]+-\d+", region):
                        raise LLMError("AWS_REGION is not a valid AWS region.")
                    url = f"https://bedrock-runtime.{region}.amazonaws.com/model/{quote(model, safe='')}/invoke"
                    resp = client.post(url, json={"anthropic_version": "bedrock-2023-05-31", **body},
                                       headers={"Authorization": f"Bearer {cheie}"})
                resp.raise_for_status()
                data = resp.json()
                tools = [b for b in data.get("content", []) if b.get("type") == "tool_use" and b.get("name") == "propune_oferta"]
                if data.get("stop_reason") != "tool_use" or len(tools) != 1:
                    raise LLMError(f"The model did not return a complete answer (stop_reason={data.get('stop_reason')}).")
                return tools[0]["input"]
            resp = client.post("https://api.openai.com/v1/responses", headers={"Authorization": f"Bearer {cheie}"}, json={
                "model": model, "store": False, "max_output_tokens": cfg.max_tokens, "instructions": system, "input": utilizator,
                "text": {"format": {"type": "json_schema", "name": "propune_oferta", "strict": True, "schema": schema}}})
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") != "completed":
                raise LLMError("The model did not complete the answer.")
            out = "".join(part.get("text", "") for item in data.get("output", []) for part in item.get("content", []) or []
                          if part.get("type") == "output_text")
            return json.loads(out)
    except httpx.HTTPStatusError as e:
        cod = e.response.status_code
        hint = {401: "check the API key", 403: "the key has no access to this model", 404: "unknown model id",
                429: "rate limit or quota reached"}.get(cod, "the service rejected the request")
        raise LLMError(f"HTTP {cod}: {hint}.") from e
    except httpx.TimeoutException as e:
        raise LLMError(f"No answer within {cfg.timeout_s:g} s.") from e
    except httpx.RequestError as e:
        raise LLMError(f"Network error: {type(e).__name__}.") from e
    except (ValueError, KeyError, TypeError) as e:
        if isinstance(e, LLMError):
            raise
        raise LLMError("The model's answer could not be read.") from e


# ---------------------------------------------------------------- agentul

def _rezultat(r: dict, ctx: dict, cfg: LlmConfig, sursa: str, **extra) -> dict:
    ids = [o["id"] for o in ctx["optiuni"]]
    interventie = None if r["interventie"] == NICIUNA else r["interventie"]
    opt = next((o for o in ctx["optiuni"] if o["id"] == interventie), None)
    motor = ctx["decizie_motor"]["interventie"]
    cost_motor = next((o["cost_banca_ron"] for o in ctx["optiuni"] if o["id"] == motor), None)
    w = list(ctx["atentionari"])
    if opt and interventie != motor and cost_motor is not None:
        w.insert(0, f"The AI agent chose a different option from the engine: +{_ron_en(opt['cost_banca_ron'] - cost_motor)} "
                    "for the bank. Adopting it is recorded as a change, with the agent's reason.")
    titlu = opt["eticheta"] if opt else (ctx["caz"]["stare_eticheta"] or "case review")
    return {"sursa": sursa, "interventie": interventie if ids else motor, "interventie_motor": motor,
            "acord_cu_motorul": (interventie == motor) if ids else True, "decide": bool(ids),
            "optiuni": [{"id": o["id"], "eticheta": o["eticheta"], "cost_banca_ron": o["cost_banca_ron"], "p_dupa_pct": o["p_dupa_pct"]}
                        for o in ctx["optiuni"]],
            "titlu": titlu[:1].upper() + titlu[1:], "oferta": opt["oferta"] if opt else None,
            "cost_banca": opt["cost_banca_ron"] if opt else None, "cost_motor": cost_motor,
            "motiv_alegere": r["motiv_alegere"].strip(), "argument": r["argument_consilier"].strip(),
            "mesaj_client": r["mesaj_client"].strip(), "puncte_cheie": [x.strip() for x in r.get("puncte_cheie") or []],
            "limba_client": ctx["limba_client"], "atentionari": w, "prompt_hash": hash_prompt(cfg), **extra}


def genereaza(caz: dict, offer_full: dict | None = None, pf=None, cfg_full=None, cfg: LlmConfig | None = None,
              env: dict[str, str] | None = None) -> dict:
    """Propunerea completă pentru un caz. Nu aruncă excepții la erori de model: cade pe șablon și spune de ce."""
    cfg = cfg or (cfg_full.llm if cfg_full is not None else LlmConfig(activat=False))
    env = configurare() if env is None else env
    t0 = time.monotonic()
    ctx = context_agent(caz, offer_full, pf, cfg_full, cfg)
    ms = lambda: int((time.monotonic() - t0) * 1000)          # noqa: E731
    try:
        furnizor, model = furnizor_si_model(cfg, env)
    except LLMError as e:
        return _rezultat(sablon(ctx), ctx, cfg, "sablon", furnizor=None, model=None, avertisment=str(e), incercari=0,
                         probleme=[], durata_ms=ms())
    cheie = env.get(CHEI[furnizor], "").strip()
    if not cfg.activat or not cheie:
        motiv = "The AI agent is disabled in llm.yaml." if not cfg.activat else f"{CHEI[furnizor]} is not set, so the text comes from the template."
        return _rezultat(sablon(ctx), ctx, cfg, "sablon", furnizor=furnizor, model=model, avertisment=motiv, incercari=0,
                         probleme=[], durata_ms=ms())
    schema, respins, probleme, incercari = schema_raspuns(ctx), None, [], 0
    for _ in range(1 + cfg.reincercari):
        incercari += 1
        try:
            r = apel_model(furnizor, cheie, model, cfg.prompt, _mesaj_utilizator(ctx, respins), schema, cfg, env)
        except LLMError as e:
            return _rezultat(sablon(ctx), ctx, cfg, "sablon", furnizor=furnizor, model=model,
                             avertisment=f"The AI agent is unavailable ({e}); the text comes from the template.",
                             incercari=incercari, probleme=probleme, durata_ms=ms())
        if isinstance(r, dict):
            r["puncte_cheie"] = puncte_valide(r.get("puncte_cheie"), ctx, cfg)   # doar afișare: fără reîncercare
        gasite = valideaza(r, ctx, cfg)
        if not gasite:
            return _rezultat(r, ctx, cfg, "llm", furnizor=furnizor, model=model, avertisment=None, incercari=incercari,
                             probleme=probleme, durata_ms=ms())
        probleme += gasite
        respins = (r, gasite)
    return _rezultat(sablon(ctx), ctx, cfg, "sablon", furnizor=furnizor, model=model,
                     avertisment="The AI answer failed validation; the text comes from the template.",
                     incercari=incercari, probleme=probleme, durata_ms=ms())


# ---------------------------------------------------------------- verificare din linia de comandă

def _caz_proba() -> tuple[dict, dict]:
    """Un caz sintetic minim (fără date reale) pentru verificarea cheii."""
    it = {"id": "fix_3_ani", "tip": "fix_piata", "eticheta": "nouă perioadă fixă 3 ani la dobânda pieței", "fezabil": True,
          "cost": 44681.0, "p_dupa": 0.0, "respecta_tinta": True, "merita": True}
    caz = {"case": {"case_id": "PROBA", "loan_id": "L0", "produs": "ipotecar", "banda": "P1", "deadline": "2026-10-30", "blocaje": [],
                    "semnale": [{"id": "expirare_dobanda_fixa", "familie": "plecare", "scor": 0.8}]},
           "client": {"nivel": "gold", "tipologie": "salariat"}, "loan": {"sold": 400000, "moneda": "RON", "tip_dobanda": "fixa",
                                                                          "dobanda": 5.03, "expira": "2026-12-12", "rata": 2508},
           "check": {"verificare_picata": None, "concluzii": {"venit_lunar": 9109, "dti_curent": 0.275}},
           "offer": {"p": 0.95, "p_tinta": 0.2, "V": 227414, "B": 32462, "legaturi": {"vechime_ani": 4.6}, "B_detalii": {"luni_ramase": 264}},
           "rec": {"recomandare": "oferta_minima", "eticheta": "ofertă minimă", "interventie": "fix_3_ani", "documente_lipsa": [],
                   "oferta": {"tip": "fix_piata", "dobanda_noua": 4.9, "perioada": "3 ani", "dupa_perioada": "IRCC + 2.50 pp = 8.05%",
                              "rata_veche": 2507.9, "rata_noua": 2478.59, "rata_dupa_fixa": 3237.5, "fixa_expira": "2026-12-12",
                              "dobanda_dupa_fixa": 8.05, "cost_banca": 44680.77, "economie_client": 35411.83,
                              "economie_orizont_luni": 36}}}
    return caz, {"interventii": [it]}


def main(argv: list[str] | None = None) -> None:
    from .common import CONFIG_DIR, setup_console
    from .config_loader import load_config
    setup_console()
    ap = argparse.ArgumentParser(description="Agentul LLM de ofertare: starea configurației și un apel de probă.")
    ap.add_argument("--verifica", action="store_true", help="face un apel de probă pe un caz sintetic")
    ap.add_argument("--config-dir", default=str(CONFIG_DIR))
    a = ap.parse_args(argv)
    cfg = load_config(a.config_dir).llm
    print(json.dumps(stare_llm(cfg), ensure_ascii=False, indent=1))
    if a.verifica:
        caz, offer = _caz_proba()
        r = genereaza(caz, offer, cfg=cfg)
        print(json.dumps({k: r[k] for k in ("sursa", "model", "interventie", "avertisment", "incercari", "probleme", "durata_ms",
                                            "motiv_alegere", "argument", "mesaj_client")}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
