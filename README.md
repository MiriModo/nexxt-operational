# retailagent — Modulul 1: scanare semnale + coadă prioritizată

Coleg virtual pentru consilierul de credite retail (Hackathon NEXXT · challenge Raiffeisen „AI for Operational
Efficiency”). Modulul 1 scanează proactiv portofoliul după semnale de **plecare**, **risc de credit** și
**blocaje de proces**, preia cererile clienților și produce o **coadă prioritizată** cu bandă (P1/P2/P3),
termen, top 3 motive și acțiunea propusă. Fiecare decizie e explicabilă cu cifre.

Rulează local și determinist: Python 3.11+, fișiere JSON/YAML, fără bază de date și fără servicii externe.

## Setup în 3 comenzi

```bash
pip install -r requirements.txt
python -m retailagent.generate --n 50 --seed 42
python -m retailagent.scan && python -m retailagent.queue
```

## Comenzi

```bash
python -m retailagent.generate --n 50 --seed 42     # data/*.json, data/externe/*.json + ground_truth.json
python -m retailagent.scan                          # out/signals_detected.json
python -m retailagent.intake                        # out/intake_cases.json (opțional, coada îl rulează intern)
python -m retailagent.queue                         # out/queue.json + tabel în consolă
python -m retailagent.evaluate                      # metrici → out/evaluation.json
python -m retailagent.evaluate --scale 5000         # + timp pe 5.000 clienți generați la cerere
python -m retailagent.explain Q0001                 # explicația completă a unui caz
python -m pytest                                    # 66 teste
```

Toate comenzile acceptă `--today AAAA-LL-ZZ`. Implicit se folosește data din `data/market.json` (2026-10-28).
Opțiunile `--data-dir`, `--out-dir` și `--config-dir` schimbă căile. Logurile structurate (JSON lines) se scriu
în `out/run.log`.

## Rezultate pe setul sintetic (50 clienți, seed 42)

| metrică | valoare |
|---|---|
| F1 detecție semnale (18 semnale evaluate) | 1.00 (55 TP, 0 FP, 0 FN) |
| tip tranzacții dedus (salariu/pensie/rată/poprire) | F1 1.00 |
| acuratețe bandă / acțiune (cazul de top al clientului) | 100% / 100% |
| ordonare (pairwise) | 708/708 |
| cerințe dure (§7) | 0 încălcări |
| cazuri-capcană (§8) | 5/5 |
| timp scan + coadă | 0.07 s / 50 clienți · ~9 s / 5.000 clienți |

> **Atenție la interpretare:** datele și etalonul sunt generate de noi, după aceleași reguli din spec.
> Scorurile perfecte arată că implementarea respectă spec-ul, nu că modelul e validat pe date reale.
> Pragurile și ponderile trebuie calibrate cu mentorul sau pe date istorice.

## Date pentru modelul final (`MODEL_FINAL.md`)

`generate` produce și datele de care au nevoie verificările, modelul de retenție și recomandarea. Le scrie
`retailagent/generate_ext.py` cu un generator aleator separat, deci datele Modulului 1 rămân identice.

| fișier | conținut | folosit la |
|---|---|---|
| `market.json` → `dobanzi_piata` | dobânzi de piață pe produs: fixă 1/3/5 ani, marjă la variabilă | B, intervenția „nouă perioadă fixă” |
| `market.json` → `costuri_mutare` | evaluare, notar (fix + % din sold), OCPI, asigurări noi, comisioane la banca nouă | B (câștigul net al plecării) |
| `loans.json` → `prima_locuinta`, `codebitori` | DTI +5 pp la prima locuință; expuneri interne ca codebitor | constrângeri, verificarea de bază |
| `conturi.json` | sold curent; sold mediu/minim, intrări/ieșiri pe 12 luni | verificarea de bază, fondul de urgență |
| `documente.json` | CI, adeverință de venit, decizie de pensie, declarație unică, contracte, evaluări, extrase CF, polițe | lista documentelor lipsă |
| `externe/anaf.json` | venituri raportate pe surse (salariu și pensie lunar; independent, dividende, chirii anual); rezidență fiscală | verificarea ANAF |
| `externe/biroul_credit.json` | credite la alte instituții, întârziere maximă pe 24 de luni, scor, interogări în ultimele 6 luni | verificarea BC |
| `externe/crc.json` | expuneri ≥ 20.000 RON la alte bănci, ca debitor sau garant, cu restanțe | verificarea CRC |
| `externe/garantii.json` | reevaluare, extras CF (ipotecă, sarcini, litigii, interdicții), asigurare cesionată | verificarea garanției |
| `ground_truth.json` | `recomandare_asteptata`, `verificare_picata_asteptata`, `comportament` | doar `evaluate` |

Mock-urile spun aceeași poveste ca portofoliul:
* o rată la alt creditor văzută în tranzacții apare și în Biroul de Credit, cu aceeași sumă;
* creditele de peste 20.000 RON apar și în CRC;
* LTV-ul depășit e confirmat de reevaluare;
* clienții care cer adeverință de sold sau refinanțare au 2–3 interogări recente în Biroul de Credit, adică își caută bancă.

`tests/test_data_ext.py` verifică primele două, plus eșecurile plantate, ANAF-ul clienților cu salariu mutat,
codebitorul și poprirea.

**Scenarii plantate pentru etapele noi:**

| client | situație | ce trebuie să se întâmple |
|---|---|---|
| C0005 | extrasul CF arată un litigiu notat | verificările se opresc la garanție → `respins_escaladat` |
| C0046 | credit nou; în Biroul de Credit, 95 de zile întârziere la un IFN | se oprește la Biroul de Credit → `respins_escaladat` |
| C0047 | majorare card; în CRC e garant pe un credit cu restanțe | se oprește la CRC → `respins_escaladat` |
| C0013 | salariul nu mai vine la noi, dar ratele le plătește prin transfer din contul lui de la altă bancă, iar ANAF arată același angajator | risc de plecare, nu de credit: coada îl pune în P1 cu `retentie_refinantare`. Oferta depinde de legăturile rămase cu banca (gold, client din 2017, folosește contul și cardul) → `oferta_produs` (pachet salariu la noi) |
| C0012, C0014, C0015 | ANAF confirmă că venitul a dispărut | `restructurare` |
| C0008, C0016 | salariul vine la altă bancă | `oferta_produs` (pachet salariu la noi) |
| C0021 | codebitor pe ipotecarul lui C0001 | expunerea intră în capacitatea lui de plată |
| C0027 | pensionar, 86 de ani la scadența imobiliarului | prelungirea maturității încalcă limita de vârstă → doar pauză de rată |
| C0045 | tânăr fără istoric, credit nou | eligibil la grila standard → `oferta_minima` |

**`comportament` (ascuns).** Fiecare client are:
* un prag de câștig net peste care pleacă;
* informația dacă reacționează la informare;
* informația dacă acceptă pachetul „salariu la noi”.

Agentul nu citește aceste câmpuri. `evaluate` le va folosi ca să simuleze cine rămâne efectiv. Așa,
comparația „agent vs. aceeași reducere pentru toți” nu se reduce la propriul model al agentului.

## Cum funcționează

```
data/*.json ─► scan (registru de semnale, config/signals.yaml) ─► signals_detected.json ─┐
data/requests.json ─► intake ───────────────────────────────────────────────────────────┤
                                                    config/priority.yaml ─► queue ─► queue.json ─► explain
```

* **`signals/inflows.py`** deduce salariul, pensia, ratele la alți creditori și popririle din tranzacții.
  Se uită la recurență (aceeași contraparte, luni consecutive) și la regex-uri pe nume (`tipare` din
  `signals.yaml`). Nu citește `tip_etichetat`, pe care îl folosește doar `evaluate`.
* **Semnalele** sunt funcții pure `(Context) -> SignalResult(scor, dovada, detalii)`. Pragurile lor vin din
  `parametri` în YAML.
* **Coada** produce un caz pentru fiecare credit care are cel puțin un semnal *declanșator* sau o cerere.
  Riscul și blocajele se calculează la nivel de client și se propagă pe toate cazurile lui. O cerere se
  atașează cazului existent pe același credit. Dacă nu există un astfel de caz, cererea creează unul cu
  `sursa = client_request`.

### Formule (valorile din `config/priority.yaml`)

```
plecare   = Σ pondere_i × scor_i  (+0.05 dacă simulare_in_app)          ∈ [0,1]
valoare   = 0.6 × venit_viitor_norm + 0.4 × min(1, nr_produse / 4)
            venit_viitor = marja × sold × ani_rămași, normalizat la maximul din portofoliu
actiune   = 1.0 dacă gap ≤ 0 sau spread_grilă[produs] ≤ buget[nivel]
            0.5 dacă spread_grilă ≤ buget × 2;  altfel 0.0
prioritate_retentie = plecare × valoare × actiune
risc_credit         = max(semnale risc_credit ale clientului)
prioritate          = max(risc_credit, prioritate_retentie, minim_cerere)
```

**Benzi.** Un caz intră în **P1** dacă îndeplinește oricare dintre condiții:
* `prioritate ≥ 0.6`;
* `risc_credit ≥ 0.7`;
* are un *semnal activ*, adică o cerere de adeverință de sold sau refinanțare, ori o dobândă fixă care expiră în ≤ 30 de zile.

Altfel cazul intră în **P2** dacă `prioritate ≥ 0.3`, iar restul merg în **P3**. Termenele SLA sunt de 1, 5 și 20 de zile.

**Acțiune (prima regulă care se potrivește):**
1. blocaj activ → `task_<blocaj>`
2. `risc_credit ≥ 0.7` → `restructurare_preventiva`
3. cerere `credit_nou` / `majorare_limita_card` / `restructurare` / `actualizare_date` → `procesare_cerere`
4. dobânda fixă expiră (scor ≥ 0.8) și oferta e imposibilă → `informare_client`
5. `prioritate_retentie ≥ 0.3` → `retentie_refinantare`
6. altfel → `monitorizare`

**Termen-limită:** minimul dintre SLA și `expirare_dobândă_fixă − 30 zile`. Termenul nu poate fi în trecut.

**Sortare:** după bandă, apoi după prioritate descrescător, apoi după termen crescător. `case_id` se atribuie
după sortare, deci `Q0001` e primul caz din coadă.

## Cum adaugi un semnal nou

1. Adaugi o intrare în `config/signals.yaml` cu câmpurile `id`, `familie`, `nivel`, `regula`, `dovada`,
   `motiv` (șablon cu câmpuri din `detalii`) și `parametri`.
2. Scrii funcția în fișierul familiei, de exemplu `retailagent/signals/risc_credit.py`:
   ```python
   @signal("descoperit_cont", familie="risc_credit", nivel="client")
   def descoperit_cont(ctx: Context) -> SignalResult:
       prag = ctx.params["prag_ron"]
       ...
       return SignalResult(0.7, f"descoperit {sold} RON", {"sold": sold})
   ```
3. Dacă e semnal de plecare, îi dai o pondere în `priority.yaml → ponderi_plecare`.
4. Adaugi 2 teste (pozitiv și negativ) în `tests/test_signals.py`.

Scanner-ul verifică la pornire că fiecare semnal din YAML are o funcție înregistrată, cu aceeași familie
și același nivel. Ca să dezactivezi un semnal fără să-i ștergi codul, pui `activat: false`.

## Interpretări ale spec-ului (de validat cu mentorul)

| subiect | ce am ales | de ce |
|---|---|---|
| `actiune` (gap acoperibil) | grila băncii e cu `spread_peste_piata_pp[produs]` peste piață; diferența trebuie acoperită din `buget_retentie_pp[nivel]` | bugetul (0.2–0.6 pp) nu poate acoperi un gap brut de ~3 pp, iar exemplul din spec are `actiune = 1.0` la gap 3.15 pp |
| „semnal activ” pentru P1 | `cerere_adeverinta_sold = 1.0` sau `expirare_dobanda_fixa = 1.0` (≤ 30 zile) | cerința dură „expirare < 30 zile ⇒ P1” trebuie garantată indiferent de valoarea clientului |
| `gap_piata_bani` | formula literală (gap × sold × ani), fără amortizare | supraestimează economia (de exemplu 277.217 RON), dar scorul e plafonat la 30.000 RON, deci clasamentul nu se schimbă |
| `venit_in_scadere` vs `venit_disparut` | scăderea se calculează doar pe lunile cu venit; lipsa totală e tratată de `venit_disparut` | altfel cele două semnale s-ar declanșa mereu împreună |
| salariu mutat vs venit pierdut | dacă salariul lipsește, dar ratele sunt acoperite din transferuri proprii de la altă bancă, `venit_disparut` nu se declanșează, iar `salariu_mutat` primește 1.0. Asta îl face semnal activ → P1 + `retentie_refinantare` | clientul nu are risc de credit, doar risc de plecare. Validat cu echipa: oferta se face în funcție de legăturile rămase cu banca (fidel sau nu) |
| „salariu” | salariu sau pensie recurentă | pensia mutată la altă bancă e același semnal |
| `ltv_depasit` | bonusul +0.2 pentru evaluare veche se aplică doar dacă LTV > 1 | o evaluare veche fără LTV depășit nu e un risc |
| `eligibilitate_externa` | istoric necurat → 0 | spec-ul dă doar factorul 1.0 pentru istoric curat |
| blocaj vs risc | blocajul are prioritate la acțiune; blocajul e activ doar de la scorul 1.0 (CI care expiră în < 30 zile = 0.5 = doar avertizare) | „oprește orice alt flux până se rezolvă” |
| semnale de context | `gap_piata_bani`, `eligibilitate_externa`, `vechime_credit` și `sold_ramas` contează în scor, dar nu creează caz singure | altfel aproape orice credit ar intra în coadă (capcana c) |
| „luna curentă” în istoricul de plăți | ultima lună închisă (septembrie, pentru azi = 28 octombrie) | istoricul are rânduri doar pentru lunile încheiate |
| `creat_la` | `<azi>T00:00:00` | determinism: aceeași intrare dă același output |

## Structura

```
retailagent/
  generate.py        # 50 de scenarii explicite (SCENARIOS) + etalon; --n > 50 repetă blocuri
  generate_ext.py    # date pentru modelul final: piață, conturi, documente, mock-uri externe, etalon
  intake.py          # cereri → cazuri (situațiile neașteptate se marchează și se loghează)
  scan.py            # încarcă portofoliul și rulează registrul
  signals/           # __init__ (registru), inflows, util, plecare, risc_credit, blocaj_proces
  queue.py           # score_case (pur) + build_queue
  explain.py         # formula cu cifre, motive, scenarii „ce-ar fi dacă”
  evaluate.py        # P/R/F1, matrice de confuzie, pairwise, cerințe dure, capcane, timp
  config_loader.py   # validare pydantic + verificări încrucișate între YAML-uri
config/              # signals.yaml, priority.yaml
tests/               # 44 teste de semnale (22 × pozitiv/negativ) + registru + capcane + criterii de acceptare
                     # + consistența datelor pentru modelul final (test_data_ext.py)
```

`queue.json` respectă exact schema din §5 a spec-ului. Modulul 2 o poate consuma direct.
