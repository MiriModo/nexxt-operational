"""Extensia datelor sintetice pentru modelul final (MODEL_FINAL.md): verificări, retenție, recomandare.

Pornește de la portofoliul produs de `generate.py` și adaugă ce le trebuie etapelor de după coadă:

    market.json                  dobânzi de piață pe perioade fixe de 1/3/5 ani + costurile mutării la altă bancă
    loans.json                   + prima_locuinta, codebitori
    conturi.json                 sold curent + sold mediu/minim pe 12 luni, calculat din fluxuri
    documente.json               dosarul clientului: CI, adeverințe, extrase CF, polițe, contracte
    externe/anaf.json            mock ANAF: venituri raportate pe surse (lunar sau anual)
    externe/biroul_credit.json   mock Biroul de Credit: credite la alte instituții, întârzieri, scor, interogări
    externe/crc.json             mock CRC: expuneri ≥ 20.000 RON la alte bănci, inclusiv ca garant
    externe/garantii.json        mock garanție: reevaluare, extras CF (sarcini, litigii), asigurare
    ground_truth.json            + recomandare_asteptata, verificare_picata_asteptata, comportament (ascuns)

Folosește un RNG separat, deci valorile Modulului 1 (clienți, credite, tranzacții, plăți, cereri) rămân
identice. Câmpul `comportament` din etalon descrie reacția reală a clientului la o ofertă. Agentul nu îl
citește niciodată; îl folosește doar `evaluate` ca să simuleze cine rămâne și cine pleacă.
"""
from __future__ import annotations

import math
import random
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from .common import add_years, last_months, month_key, parse_date, shift_month, write_json

# ---------------------------------------------------------------- piață (sintetic, ordin de mărime realist)

DOBANZI_PIATA = {
    "ipotecar":        {"fixa_1_an": 4.70, "fixa_3_ani": 4.90, "fixa_5_ani": 5.10, "marja_variabila": 2.00},
    "imobiliar":       {"fixa_1_an": 5.00, "fixa_3_ani": 5.20, "fixa_5_ani": 5.40, "marja_variabila": 2.30},
    "refinantare":     {"fixa_1_an": 7.90, "fixa_3_ani": 8.20, "fixa_5_ani": 8.50, "marja_variabila": 3.50},
    "nevoi_personale": {"fixa_toata_durata": 8.90},
    "card_credit":     {"fixa_toata_durata": 22.00},
}

# costuri suportate de client când își mută creditul la altă bancă (RON; *_pct = procent din sold)
_COST_GARANTAT = {"evaluare_imobil": 650, "notar_fix": 900, "notar_pct_sold": 0.15, "ocpi": 450,
                  "asigurari_noi": 350, "comision_analiza_banca_noua": 0, "comision_acordare_pct": 0.0}
_COST_NEGARANTAT = {"evaluare_imobil": 0, "notar_fix": 0, "notar_pct_sold": 0.0, "ocpi": 0,
                    "asigurari_noi": 0, "comision_analiza_banca_noua": 250, "comision_acordare_pct": 0.5}
COSTURI_MUTARE = {"ipotecar": _COST_GARANTAT, "imobiliar": _COST_GARANTAT, "refinantare": _COST_NEGARANTAT,
                  "nevoi_personale": _COST_NEGARANTAT, "card_credit": {**_COST_NEGARANTAT, "comision_acordare_pct": 0.0}}

# ---------------------------------------------------------------- rezultatul așteptat pe scenariu (1..50)
#
# recomandare: nu_interveni | oferta_minima | oferta_produs | restructurare | respins_escaladat
#              | blocat (task de proces, restul așteaptă) | None (clientul nu intră în coadă)
# verificare_picata: primul pas extern care trebuie să pice (intern → anaf → biroul_credit → crc → garantie)
# plante: anaf=salariu_continua | bc=negativ | crc=garant_restante | cf=litigiu | pachet=True | codebitor_la=<nr>

NU, MIN, PROD, RESTR, RESP, BLOC = ("nu_interveni", "oferta_minima", "oferta_produs", "restructurare",
                                    "respins_escaladat", "blocat")

FINAL: dict[int, tuple[str | None, str | None, dict, str]] = {
    1:  (MIN,   None, {}, "fixă care expiră în 15 zile, gap mare, client gold cu salariul la noi"),
    2:  (RESTR, None, {}, "capcana a: expirare + întârziere → restructurare, nicio ofertă de retenție"),
    3:  (MIN,   None, {}, "capcana e: cerere de adeverință pe un credit deja în coadă"),
    4:  (NU,    None, {}, "capcana b: sold mic, an rămas → câștigul plecării nu acoperă costul unei intervenții"),
    5:  (RESP,  "garantie", {"cf": "litigiu"}, "platinum, 750k; extrasul CF arată un litigiu notat → escaladat"),
    6:  (NU,    None, {}, "nevoi personale 40k, gap mic după expirare"),
    7:  (MIN,   None, {}, "pensionar, imobiliar 150k, expiră în 120 zile"),
    8:  (PROD,  None, {"pachet": True}, "salariul vine la altă bancă → pachet salariu la noi + reducere"),
    9:  (NU,    None, {}, "card + credit nou la alt creditor; nimic de reținut"),
    10: (NU,    None, {}, "rată veche la alt creditor"),
    11: (NU,    None, {}, "rată veche la alt creditor"),
    12: (RESTR, None, {}, "salariul nu mai vine; ANAF confirmă: nu mai are venit"),
    13: (PROD,  None, {"anaf": "salariu_continua", "pachet": True},
         "salariul vine acum la altă bancă (ANAF: același angajator; ratele le acoperă prin transfer propriu) "
         "→ risc de plecare, nu de credit. Legături rămase: gold, client din 2017, folosește contul și cardul "
         "→ fidel → merită pachet salariu la noi + reducere"),
    14: (NU,    None, {"anaf": "salariu_continua"},
         "cazul opus lui 13: salariul vine la altă bancă (ANAF: același angajator; ratele prin transfer propriu), "
         "dar fără legături rămase: standard, client de 1,5 ani, un singur produs, contul nu mai e folosit "
         "→ nu merită reducere; doar informare"),
    15: (RESTR, None, {}, "salariul nu mai vine; ANAF confirmă"),
    16: (PROD,  None, {"pachet": True}, "platinum, adeverință de sold, salariul la altă bancă"),
    17: (BLOC,  None, {}, "capcana d: CI expirată → doar task-ul, verificările așteaptă"),
    18: (RESTR, None, {}, ""), 19: (RESTR, None, {}, ""), 20: (RESTR, None, {}, "cere el restructurare"),
    21: (RESTR, None, {"codebitor_la": 1}, "venit în scădere; e și codebitor pe ipotecarul clientului 1"),
    22: (RESTR, None, {}, ""), 23: (RESTR, None, {}, ""), 24: (RESTR, None, {}, ""),
    25: (RESTR, None, {}, ""), 26: (RESTR, None, {}, ""),
    27: (RESTR, None, {}, "pensionar: prelungirea maturității încalcă limita de vârstă → doar pauză de rată"),
    28: (RESTR, None, {}, ""), 29: (RESTR, None, {}, ""),
    30: (BLOC,  None, {}, ""), 31: (BLOC, None, {}, ""), 32: (BLOC, None, {}, ""), 33: (BLOC, None, {}, ""),
    34: (BLOC,  None, {}, ""), 35: (BLOC, None, {}, ""), 36: (BLOC, None, {}, "PEP"),
    37: (RESTR, None, {}, "LTV depășit; reevaluarea confirmă"), 38: (RESTR, None, {}, "LTV depășit; reevaluarea confirmă"),
    39: (BLOC,  None, {}, ""), 40: (BLOC, None, {}, ""),
    41: (NU,    None, {}, "restructurare veche, fără risc activ"), 42: (NU, None, {}, "restructurare veche"),
    43: (RESTR, None, {}, ""), 44: (RESTR, None, {}, ""),
    45: (MIN,   None, {}, "credit nou, tânăr fără istoric: eligibil la grila standard"),
    46: (RESP,  "biroul_credit", {"bc": "negativ"}, "credit nou; BC: întârziere de 95 de zile la un IFN"),
    47: (RESP,  "crc", {"crc": "garant_restante"}, "majorare card; CRC: garant pe un credit cu restanțe"),
    48: (NU,    None, {}, "actualizare date"),
    49: (NU,    None, {}, "simulare rambursare anticipată pe variabilă (comision 0)"),
    50: (None,  None, {}, "capcana c: nu apare în coadă"),
}

INSTITUTIE = {"BCR RATA CREDIT": "BCR", "BRD GROUPE SOCIETE GENERALE RATA": "BRD",
              "BANCA TRANSILVANIA RATA CREDIT": "Banca Transilvania", "ING BANK RATA": "ING Bank",
              "IFN PROVIDENT FINANCIAL": "Provident Financial IFN", "CREDIUM IFN RATA": "Credium IFN",
              "CEC BANK RATA": "CEC Bank"}
BANCI_CRC = ["BCR", "BRD", "Banca Transilvania", "ING Bank", "CEC Bank", "UniCredit Bank", "Libra Internet Bank"]
ASIGURATORI = ["Groupama Asigurari", "Allianz-Tiriac", "Omniasig", "Generali Romania", "Asirom"]
SECURED = ("ipotecar", "imobiliar")


class Extension:
    def __init__(self, g, seed: int):
        self.g = g
        self.rng = random.Random(seed * 1_000_003 + 7)
        self.today: date = g.today
        self.cur_month = month_key(self.today)
        self.tx_months = last_months(self.cur_month, 12)
        self.anaf_months = last_months(shift_month(self.cur_month, -1), 12)   # ANAF raportează lunile închise
        self.loans_by_client: dict[str, list[dict]] = defaultdict(list)
        for l in g.loans:
            self.loans_by_client[l["client_id"]].append(l)
        self.tx_by_client: dict[str, list[dict]] = defaultdict(list)
        for t in g.transactions:
            self.tx_by_client[t["client_id"]].append(t)
        self.employer = {e["angajator_id"]: e for e in g.employers}
        self.conturi, self.documente, self.anaf, self.bc, self.crc, self.garantii = [], [], [], [], [], []

    # ---------------- helpers
    def scen(self, idx0: int) -> tuple[int, int]:
        """(numărul scenariului 1..50, blocul) pentru clientul cu indexul 0-based idx0."""
        return idx0 % len(FINAL) + 1, idx0 // len(FINAL)

    def d(self, days: int) -> date:
        return self.today + timedelta(days=days)

    def monthly(self, cid: str, tip: str) -> dict[str, float]:
        out: dict[str, float] = defaultdict(float)
        for t in self.tx_by_client[cid]:
            if t["tip_etichetat"] == tip:
                out[t["data"][:7]] += t["suma"]
        return out

    # ---------------- credite: prima locuință, codebitori
    def extend_loans(self) -> None:
        for l in self.g.loans:
            l["prima_locuinta"] = True if l["produs"] == "ipotecar" else (False if l["produs"] == "imobiliar" else None)
        for idx0, c in enumerate(self.g.clients):
            nr, block = self.scen(idx0)
            target = FINAL[nr][2].get("codebitor_la")
            if target:
                owner = self.g.clients[block * len(FINAL) + target - 1]["client_id"]
                loan = next(l for l in self.loans_by_client[owner] if l["produs"] in SECURED)
                loan["codebitori"].append({"client_id": c["client_id"], "nume": c["nume"], "rol": "codebitor"})
        for l in self.g.loans:
            if l["produs"] in SECURED and not l["codebitori"] and self.rng.random() < 0.3:
                nume = f"{self.rng.choice(['Maria', 'Ana', 'Ioana', 'Mihai', 'Andrei', 'Elena'])} " \
                       f"{self.g.clients[int(l['client_id'][1:]) - 1]['nume'].split()[-1]}"
                l["codebitori"].append({"client_id": None, "nume": nume, "rol": "codebitor"})

    # ---------------- conturi: sold mediu / minim din fluxuri
    def make_account(self, c: dict) -> None:
        cid, rng = c["client_id"], self.rng
        rate = sum(l["rata_lunara"] for l in self.loans_by_client[cid])
        flows = {m: [0.0, 0.0] for m in self.tx_months}
        for t in self.tx_by_client[cid]:
            m = t["data"][:7]
            if m in flows:
                flows[m][0 if t["directie"] == "in" else 1] += t["suma"]
        avg_in = sum(v[0] for v in flows.values()) / len(flows) or 3_000
        bal = rng.uniform(0.5, 2.5) * avg_in
        poprire = any(t["tip_etichetat"] == "poprire" for t in self.tx_by_client[cid])
        istoric = []
        for m in self.tx_months:
            inc, out = flows[m]
            out += rate
            end = bal + inc - out
            if end < 0:                       # descoperitul nu e modelat: contul e readus aproape de zero
                end = rng.uniform(50, 400)
            elif end > 3 * avg_in:            # excedentul pleacă lunar în economii (nemodelate)
                end = 3 * avg_in * rng.uniform(0.8, 1.0)
            minim = max(0.0, min(bal, end) - 0.2 * out)
            if poprire and m >= self.tx_months[-2]:   # poprirea golește contul
                end, minim = rng.uniform(0, 150), 0.0
            istoric.append({"luna": m, "sold_mediu": round((bal + end) / 2, 2), "sold_minim": round(minim, 2),
                            "intrari": round(inc, 2), "iesiri": round(out, 2)})
            bal = end
        self.conturi.append({"client_id": cid, "iban": f"RO{rng.randint(10, 99)}RZBR{rng.randint(10**15, 10**16 - 1)}",
                             "moneda": "RON", "sold_curent": round(bal, 2), "istoric_lunar": istoric})

    # ---------------- documente din dosar
    def make_documents(self, c: dict) -> None:
        cid, rng, typ = c["client_id"], self.rng, c["tipologie_declarata"]
        ci = parse_date(c["ci_expira_la"])
        docs = [{"tip": "carte_identitate", "referinta": None,
                 "data_emitere": add_years(ci, -10).isoformat(), "valabil_pana": ci.isoformat()}]
        if typ in ("salariat", "tanar_fara_istoric") and c["angajator_id"]:
            docs.append({"tip": "adeverinta_venit", "referinta": c["angajator_id"],
                         "data_emitere": self.d(-rng.randint(5, 220)).isoformat(), "valabil_pana": None})
        if typ == "pensionar":
            docs.append({"tip": "decizie_pensie", "referinta": None,
                         "data_emitere": add_years(self.today, -rng.uniform(1, 8)).isoformat(), "valabil_pana": None})
        if typ in ("independent", "antreprenor"):
            docs.append({"tip": "declaratie_unica", "referinta": "2025", "data_emitere": "2026-05-25",
                         "valabil_pana": None})
        for l in self.loans_by_client[cid]:
            docs.append({"tip": "contract_credit", "referinta": l["loan_id"], "data_emitere": l["data_acordare"],
                         "valabil_pana": l["data_scadenta"]})
            g = l["garantie"]
            if g:
                docs.append({"tip": "raport_evaluare", "referinta": l["loan_id"], "data_emitere": g["data_evaluare"],
                             "valabil_pana": None})
                docs.append({"tip": "extras_cf", "referinta": l["loan_id"],
                             "data_emitere": self.d(-rng.randint(10, 400)).isoformat(), "valabil_pana": None})
                docs.append({"tip": "polita_asigurare_imobil", "referinta": l["loan_id"],
                             "data_emitere": add_years(parse_date(g["asigurare_expira_la"]), -1).isoformat(),
                             "valabil_pana": g["asigurare_expira_la"]})
        self.documente.append({"client_id": cid, "documente": docs})

    # ---------------- ANAF
    def make_anaf(self, c: dict, plante: dict) -> None:
        cid, rng, typ = c["client_id"], self.rng, c["tipologie_declarata"]
        months = self.anaf_months
        surse = []

        def lunar(tip: str, platitor: str, valori: dict[str, float]) -> None:
            valori = {m: round(valori[m], 2) for m in months if valori.get(m)}
            if valori:
                surse.append({"tip": tip, "platitor": platitor, "frecventa": "lunar", "valori": valori})

        sal = self.monthly(cid, "salariu")
        if sal:
            emp = self.employer[c["angajator_id"]]
            if plante.get("anaf") == "salariu_continua":     # salariul e mutat la altă bancă, nu pierdut
                medie = sum(sal.values()) / len(sal)
                for m in months:
                    sal.setdefault(m, medie * rng.uniform(0.99, 1.02))
            lunar("salariu", emp["nume"], sal)
        elif typ == "salariat" and c["angajator_id"]:       # salariul vine la altă bancă: ANAF îl vede, noi nu
            emp = self.employer[c["angajator_id"]]
            baza = rng.uniform(6_000, 16_000)
            lunar("salariu", emp["nume"], {m: baza * rng.uniform(0.98, 1.03) for m in months})
        pen = self.monthly(cid, "pensie")
        if pen:
            platitor = next(t["platitor_beneficiar"] for t in self.tx_by_client[cid] if t["tip_etichetat"] == "pensie")
            lunar("pensie", platitor, pen)
        if typ == "independent":
            total = sum(t["suma"] for t in self.tx_by_client[cid] if t["tip_etichetat"] == "extern")
            surse.append({"tip": "activitati_independente", "platitor": None, "frecventa": "anual",
                          "valori": {"2025": round(total * rng.uniform(0.85, 0.95), -2)}})
        div = sum(t["suma"] for t in self.tx_by_client[cid] if t["tip_etichetat"] == "dividende")
        if div:
            surse.append({"tip": "dividende", "platitor": None, "frecventa": "anual", "valori": {"2025": round(div, -2)}})
        chirie = [t["suma"] for t in self.tx_by_client[cid] if t["tip_etichetat"] == "chirie_in"]
        if chirie:
            surse.append({"tip": "cedarea_folosintei", "platitor": None, "frecventa": "anual",
                          "valori": {"2025": round(chirie[0] * 12, -2)}})
        self.anaf.append({"client_id": cid, "rezident_fiscal": "strainatate" if typ == "diaspora" else "RO",
                          "perioada": {"de_la": months[0], "pana_la": months[-1]}, "surse": surse})

    # ---------------- Biroul de Credit + CRC
    def make_bc_crc(self, c: dict, plante: dict) -> None:
        cid, rng, typ = c["client_id"], self.rng, c["tipologie_declarata"]
        credite = []
        rate_alt = [t for t in self.tx_by_client[cid] if t["tip_etichetat"] == "rata_alt_creditor"]
        if rate_alt:
            luni = len({t["data"][:7] for t in rate_alt})
            rata = rate_alt[0]["suma"]
            vechi = luni > 3
            acordat = add_years(self.today, -rng.uniform(2, 5)) if vechi else self.d(-rng.randint(95, 120))
            inst = INSTITUTIE.get(rate_alt[0]["platitor_beneficiar"], rate_alt[0]["platitor_beneficiar"])
            credite.append({"institutie": inst, "tip": "nevoi_personale", "rol": "debitor", "stare": "activ",
                            "data_acordare": acordat.isoformat(), "data_inchidere": None,
                            "sold": round(rata * (rng.uniform(10, 40) if vechi else rng.uniform(35, 55)), -2),
                            "rata_lunara": rata, "max_zile_intarziere_24l": 0})
        if typ != "tanar_fara_istoric" and rng.random() < 0.35:
            inchis = add_years(self.today, -rng.uniform(1, 6))
            credite.append({"institutie": rng.choice(BANCI_CRC), "tip": rng.choice(["nevoi_personale", "card_credit"]),
                            "rol": "debitor", "stare": "inchis", "data_acordare": add_years(inchis, -rng.uniform(2, 5)).isoformat(),
                            "data_inchidere": inchis.isoformat(), "sold": 0, "rata_lunara": 0,
                            "max_zile_intarziere_24l": 0})
        if plante.get("bc") == "negativ":
            credite.append({"institutie": "Provident Financial IFN", "tip": "nevoi_personale", "rol": "debitor",
                            "stare": "inchis", "data_acordare": add_years(self.today, -2.5).isoformat(),
                            "data_inchidere": self.d(-180).isoformat(), "sold": 0, "rata_lunara": 0,
                            "max_zile_intarziere_24l": 95})
        scor = 480 if plante.get("bc") == "negativ" else rng.randint(610, 820)
        cereri = {r["tip"] for r in self.g.requests if r["client_id"] == cid}
        interogari = rng.randint(2, 3) if cereri & {"adeverinta_sold", "refinantare"} else rng.randint(0, 1)
        self.bc.append({"client_id": cid, "fara_istoric": typ == "tanar_fara_istoric" and not credite,
                        "scor": None if typ == "tanar_fara_istoric" and not credite else scor,
                        "interogari_ultimele_6l": interogari, "credite": credite})

        expuneri = [{"institutie": cr["institutie"], "rol": "debitor", "tip": cr["tip"], "sold": cr["sold"],
                     "restante": 0, "zile_restanta": 0}
                    for cr in credite if cr["stare"] == "activ" and cr["sold"] >= 20_000]
        if plante.get("crc") == "garant_restante":
            expuneri.append({"institutie": rng.choice(BANCI_CRC), "rol": "garant", "tip": "ipotecar", "sold": 185_000,
                             "restante": 4_200, "zile_restanta": 62})
        self.crc.append({"client_id": cid, "luna_raportare": self.anaf_months[-1], "prag_raportare_ron": 20_000,
                         "expuneri": expuneri})

    # ---------------- garanții: reevaluare, CF, asigurare
    def make_guarantees(self, c: dict, plante: dict) -> None:
        rng = self.rng
        for l in self.loans_by_client[c["client_id"]]:
            g = l["garantie"]
            if not g:
                continue
            ani = (self.today - parse_date(g["data_evaluare"])).days / 365.25
            if l["sold_ramas"] > g["valoare_evaluare"]:        # LTV depășit: reevaluarea confirmă scăderea
                val = g["valoare_evaluare"] * rng.uniform(0.95, 1.0)
            else:
                val = g["valoare_evaluare"] * (1 + min(0.30, ani * rng.uniform(0.01, 0.04)))
            litigii = []
            if plante.get("cf") == "litigiu":
                litigii = [{"tip": "actiune_partaj", "dosar": f"{rng.randint(1000, 9999)}/3/2026",
                            "notat_la": self.d(-rng.randint(20, 60)).isoformat()}]
            self.garantii.append({
                "loan_id": l["loan_id"], "client_id": c["client_id"],
                "reevaluare": {"valoare": round(val, -3), "data": self.d(-rng.randint(5, 60)).isoformat(),
                               "metoda": "indexare_statistica"},
                "cf": {"numar": f"{rng.randint(100000, 399999)}", "uat": rng.choice(["Bucuresti S1", "Bucuresti S3",
                       "Cluj-Napoca", "Iasi", "Timisoara", "Brasov", "Constanta", "Ploiesti"]),
                       "ipoteca_rang_1_banca": True, "alte_sarcini": [], "litigii": litigii, "interdictii": [
                           "interdictie_instrainare_grevare_in_favoarea_bancii"]},
                "asigurare": {"asigurator": rng.choice(ASIGURATORI), "polita": f"PAD-{rng.randint(10**7, 10**8 - 1)}",
                              "expira_la": g["asigurare_expira_la"], "cesionata_bancii": True},
            })

    # ---------------- etalon: rezultatul așteptat + comportamentul ascuns
    def extend_ground_truth(self, c: dict, gt: dict, nr: int, plante: dict) -> None:
        rec, picata, _, nota = FINAL[nr]
        rng = self.rng
        recent = set(self.tx_months[-2:])
        salariu_aici = any(t["tip_etichetat"] == "salariu" and t["data"][:7] in recent
                           for t in self.tx_by_client[c["client_id"]])
        gt["recomandare_asteptata"] = rec
        gt["verificare_picata_asteptata"] = picata
        gt["nota_model_final"] = nota
        gt["comportament"] = {
            # pleacă doar dacă banii câștigați net (după costul mutării și după oferta noastră) depășesc pragul
            "prag_castig_plecare_ron": round(math.exp(rng.gauss(math.log(12_000), 0.5)), -2),
            "reactioneaza_la_informare": rng.random() < 0.35,
            "accepta_pachet_salariu": None if salariu_aici else (True if plante.get("pachet") else rng.random() < 0.4),
        }

    def run(self) -> "Extension":
        self.extend_loans()
        gt_by_client = {gt["client_id"]: gt for gt in self.g.ground_truth}
        for idx0, c in enumerate(self.g.clients):
            nr, _ = self.scen(idx0)
            plante = FINAL[nr][2]
            self.make_account(c)
            self.make_documents(c)
            self.make_anaf(c, plante)
            self.make_bc_crc(c, plante)
            self.make_guarantees(c, plante)
            self.extend_ground_truth(c, gt_by_client[c["client_id"]], nr, plante)
        return self

    def market(self) -> dict:
        return {"dobanzi_piata": DOBANZI_PIATA, "costuri_mutare": COSTURI_MUTARE}

    def write(self, out: Path) -> None:
        write_json(out / "conturi.json", self.conturi)
        write_json(out / "documente.json", self.documente)
        write_json(out / "externe" / "anaf.json", self.anaf)
        write_json(out / "externe" / "biroul_credit.json", self.bc)
        write_json(out / "externe" / "crc.json", self.crc)
        write_json(out / "externe" / "garantii.json", self.garantii)


def extend(g, seed: int) -> Extension:
    return Extension(g, seed).run()
