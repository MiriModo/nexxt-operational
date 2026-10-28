# AUDIT final Keeper — înainte de predare (joi 11:00)

Data: 28 oct 2026, seara · commit auditat: `a040948` (main = origin/main) · referință: `MODEL_FINAL.md`.
Regulă respectată: **niciun fișier din repo nu a fost modificat** (singurul fișier scris e acesta). Totul a rulat într-o
clonă proaspătă (`git clone` în scratchpad), cu date și ieșiri separate; imaginile Docker construite pentru test au fost șterse.

## Rezumat

- **Nu am găsit niciun P0 tehnic.** Toate cerințele dure au 0 încălcări, verificate independent, nu doar din contoarele
  lui `evaluate`. Pipeline-ul e determinist, testele trec 199/199, iar UI-ul are 0 erori în consolă.
- **Am ridicat la P0 un singur punct, de pitch:** cifra-vedetă. MODEL_FINAL o definește „la aceeași rată de rămânere”,
  dar nicio reducere uniformă nu atinge rata agentului. Cei 3,19 M RON „economisiți” sunt deci comparați cu o politică
  ce păstrează 78 % din clienți, față de 98 % la agent. Pe etalonul de 60 din README, aceeași cifră iese **negativă**
  (−88.852 RON). Un jurat care întreabă „la aceeași rată?” o dărâmă.
- **P1 care se văd la juriu:** README are cifre și timpi vechi; cazul principal de demo (C0001) iese „amânat, peste
  plafon”; AUC 0,984 vine dintr-o etichetă generată din aceleași variabile; pasul `recommend` rulat separat nu aplică
  bugetul de portofoliu; modelul cade tăcut pe sigmoid dacă aplicația pornește din alt folder.

## Tabel

| # | Verificare | Rezultat | Dovada (comandă + output scurt) | Sev. | Fix propus |
|---|---|---|---|---|---|
| 1.1 | Clonă curată + README „Setup în 3 comenzi” | OK | `git clone …` → `pip install -r requirements.txt` (deja satisfăcut) → `python -m retailagent.generate` rc=0, 31,7 s → `python -m retailagent.pipeline` rc=0 | — | — |
| 1.2 | Timpi din README vs. real | FAIL | README: „pipeline (~45 s)”. Real pe clonă: `pipeline` **3 min 40 s** (flux 57,5 s + evaluate ~90 s + demo.html 45 s) | P1 | README: „~4 min (flux ~1 min, evaluare ~1,5 min, demo ~45 s)” |
| 1.3 | Pași individuali din README | OK | `scan` 13 s, `intake` 4 s, `queue` 7 s, `checks` 16 s, `retention` 48 s, `recommend` 53 s, `explain Q0001` 101 linii, `evaluate` 91 s; toate rc=0 | — | — |
| 1.4 | UI din README (`cd ui && npm install && npm run dev`) | OK | `npm install` 29 s rc=0; `npm run build` ✓; Vite + `python -m retailagent.api` pornite din rădăcină, gata în ~65 s | — | — |
| 1.5 | Docker (README modul C) | OK | `docker compose -p keeperaudit build` → `keeperaudit-api` 587 MB, `keeperaudit-ui` 75 MB, „Built” | — | — |
| 1.6 | Chei / tokenuri / căi absolute în cod și config | OK (cu nuanțe) | `git ls-files \| xargs grep` după `C:/dev`, `/c/Users`, `modor`, email, `sk-ant`, `api_key`: **0 în cod/config**. Căi `C:/dev/NEXXT` doar în `docs/autobot/istoric/*.loop.md` (arhivă). Parole de demo în clar: `config/echipa.yaml` (`1234`), admin implicit `admin` (documentate în README) | P2 | Arhiva autobot poate ieși din repo; pentru prezentare, parolă admin din `RETAILAGENT_ADMIN_PAROLA` |
| 2.1 | Determinism date (seed 42, de 2 ori) | OK | `generate` în 2 foldere → hash-uri SHA-256 identice pentru toate fișierele din `data/` | — | — |
| 2.2 | Determinism pipeline (de 2 ori) | OK | `pipeline --out-dir out_run2` și `out_run3`: `signals_detected`, `intake_cases`, `queue`, `checks`, `offers`, `recommendations.json`, `audit.jsonl` **byte-identice**; `evaluation.json` diferă doar la `timp` | — | — |
| 2.3 | Pași individuali vs. `pipeline` | FAIL | `recommendations.json` diferă la 664 de cazuri: `recommend` rulat singur **nu aplică bugetul de portofoliu** (lipsesc `in_buget`/`amanata_buget`, 541 de motive fără „amânată”). Ex. Q2266: CLI fără marcaj, pipeline `amanata_buget: true` | P1 | `recommend.main` să apeleze `buget.aplica` ca `pipeline.run_full` (o linie), sau README: „pașii individuali nu aplică bugetul” |
| 2.4 | 5.000 de clienți | OK | `generate --n 5000` 21 s; `pipeline` 107 s rc=0; 2.945 cazuri; scan + coadă 9,1 s, flux 37,1 s; 0 erori; cerințe dure 0 | — | — |
| 3.1 | Fără ofertă de retenție la risc ≥ 0,7 | OK (0) | Script independent `hard_rules.py` pe 10k: 2.265 cazuri cu risc → restructurare 1.975, escaladat 61, blocat 229; **0 oferte comerciale** | — | — |
| 3.2 | Fără ofertă pe blocaj activ | OK (0) | 1.505 cazuri blocate (CI expirată 478, KYC vechi 408, asigurare 315, consimțământ 292, flag blocant 59) → toate `blocat`, **0 oferte / intervenții** | — | — |
| 3.3 | Limite: DTI 40/20 (+5), LTV, buget pe nivel, marjă minimă, vârstă | OK (0), un caz la limită | Recalculat din date: DTI după ofertă > limită 0; reducere peste buget nivel 0; marjă < 1,5 pp 0; intervenție infezabilă aleasă 0; 114 credite noi: DTI după ≤ 40 % (0 depășiri). **Vârstă:** Q1925 (restructurare +60 luni) atinge 70,04 ani la ultima rată (iunie 2053, născut 14.06.1983): regula verifică vârsta pe 1 a lunii de scadență | P2 | `retention_menu.py:79`: vârsta la ultima zi a lunii de scadență, nu la 1 |
| 3.4 | Expirare fixă < 30 zile ⇒ P1 | OK (0) | 92 de cazuri cu expirare < 30 zile, toate P1; 0 credite cu expirare < 30 zile fără caz | — | — |
| 3.5 | Cea mai ieftină intervenție cu p ≤ țintă și cost ≤ p × V; altfel nu interveni / informare | OK (0) | 2.300 de cazuri evaluate: 0 neoptime, 0 fallback greșite (recalculat din meniul din `offers.json`) | — | — |
| 3.6 | Cererea pe un credit deja în coadă se atașează | OK (0) | 0 credite cu 2 cazuri; 0 `request_id` dublate; 1.009 cazuri cu cerere, din care 214 atașate pe cazuri din scan | — | — |
| 4 | Cazuri-capcană | OK 5/5 | a: C0002 → Q0725 P1, restructurare_preventiva, `pauza_rata` · b: C0004 → Q4876 P3, monitorizare, nu interveni · c: C0050 (platinum fără semnale) → **niciun caz** · d: C0017 → Q2595 P1, `ci_expirata`, task, `blocat` · e: C0003 → **un singur** caz Q2301 cu R0001 atașat (fix 3 ani) | — | — |
| 5.1 | Expirare dobândă fixă (Q0001, doar acest motiv) | OK | rulează: KYC, expuneri, venit, sold, LTV, asigurare, scenarii rată, cost mutare, ANAF, BC, CRC, extras CF, reevaluare, capacitate plată; sărite: card („nu deține”), comision OUG 50, fond urgență, eligibilitate produs nou („niciun motiv nu o cere”); mock-uri apelate: ANAF 1, BC 1, CRC 1, garanție 2 | — | — |
| 5.2 | Simulare rambursare anticipată (Q0171, doar acest motiv) | OK | rulează: baza + comision OUG 50 + fond urgență; sărite: BC și CRC („sărită de motivul simulare_rambursare_anticipata”), garanție (nu deține ipotecar), ANAF; **mock-uri apelate: niciunul** | — | — |
| 5.3 | Întârziere nouă (Q0006, doar acest motiv) | OK | motiv `risc`: rulează baza + LTV + asigurare + ANAF + capacitate plată; sărite: scenarii rată, cost mutare, extras CF („sărită de motivul risc”), BC/CRC; mock-uri: ANAF 1 | — | — |
| 5.4 | Mock-urile nu sunt apelate când motivul le sare | OK (0) | Mock-uri instrumentate cu contor, pe toate cele 6.032 de cazuri: treapta a rulat la ANAF 2.891, BC 2.306, CRC 777, garanție 605 cazuri; **0 apeluri de mock** pe cazuri unde treapta era sărită sau neatinsă | — | — |
| 6 | Configurația e configurație (`buget_retentie_pp.standard = 0`, în copie) | OK | Copie `config_b0` + `pipeline --config-dir`: la standard se schimbă 14 oferte (pachet salariu → fix 3 ani/1 an, singura reducere de marjă → fix 3 ani), reduceri de marjă 1 → 0; gold și platinum: **0 schimbări**; niciun fișier de cod atins; config original neatins (`git status` curat) | — | — |
| 7.1 | Sigmoid vs. referință (testul de aur) | OK | `test_churn.py::test_sigmoid_churn_reproduce_formula` verde; etalon 60 cu `model: sigmoid` → benzi 100 %, acțiuni 100 %, recomandări 57/59 (antrenat: 58/59; diferă C0060 = scenariul nou „refinanțare externă”, calibrat pe modelul antrenat) | — | — |
| 7.2 | Fără fișierul modelului antrenat | OK | `mv models/churn_v1.pkl …` → `pipeline` rc=0, `UserWarning: modelul antrenat … lipsește: se folosește sigmoidul`, toate ofertele `model_churn: sigmoid`; fișier restaurat | — | — |
| 7.3 | Pornit din alt folder decât rădăcina | FAIL | `cd ui && python -m retailagent.pipeline --config-dir ../config` → același warning, **sigmoid în tăcere** (`churn.model.get_model` citește `models/churn_v1.pkl` relativ la cwd). README și Docker pornesc din rădăcină, deci nu apare în demo dacă respectați README | P1 | `churn/model.py:111`: rezolvă `ch.cale` față de rădăcina proiectului (ca în `versiune.py`) |
| 7.4 | AUC / Brier / leakage | ATENȚIE | `models/churn_v1.json`: **AUC 0,9845**, Brier 0,0445, ECE 0,024 (test 428). Eticheta (`churn/labels.py` → `evaluate_final.ramane`) = `B > prag`, unde `B` e **câștigul calculat chiar de agent**, iar `prag = 6000 × (1 + 0,8·vechime + 0,9·produse + 0,7·nivel + 0,4·activitate) × lognormal(0,45)`. Feature-uri suspecte: **`B_norm` (+2,36), `B_log` (+2,23)** și componentele `leg_vechime`, `leg_produse`, `leg_nivel`, `leg_activitate`, `vechime_ani`, `nr_produse`, `nivel_*`: exact intrările regulii care produce eticheta | P1 | Nu e leak din viitor, e circularitate: modelul reînvață regula generatorului. În pitch: „AUC pe date sintetice, unde eticheta e generată din aceleași variabile; valoarea reală vine din rezultatele la 90 de zile (bucla de feedback)”. Opțional: zgomot mai mare sau variabile ascunse în comportament |
| 8.1 | Cifra-vedetă: cost retenție vs. „aceeași reducere pentru toți”, la aceeași rată | FAIL (logică) | `evaluation.json → cifra_vedeta`, 10k: agent 25,79 M RON, rămân **97,9 %**; uniform 0,6 pp 28,98 M, rămân **78,1 %**; `uniform_aleasa: null` (nicio reducere uniformă nu atinge 98 %); `economie_ron` 3.188.389 = diferența față de politica cu retenție maximă, nu „la aceeași rată”. Etalon 60: agent 356.460 vs. uniform 0,4 pp 267.608 → **`economie_ron` −88.852**. Reports afișează „Saved vs. a uniform cut 3.19 M RON” | **P0** (pitch) | Reformulează metrica ca **cost per client păstrat**: agent 12.250 RON vs. uniform 0,6 pp 17.257 RON (−29 %), plus „păstrează 98 % vs. 78 %”. `evaluate_final.cifra_vedeta` + card Reports + README. Cifrele se recalculează deja din cod |
| 8.2 | % „nu interveni” | OK, din cod | 10k: 1.522 / 4.527 = 33,6 % (`model_final.nu_interveni`); etalon 60: 16/65 = 24,6 % | — | — |
| 8.3 | Interogări externe evitate | OK, din cod | 10k: 19.247 / 26.294 = 73,2 %; etalon 60: 213/339 = 62,8 % | — | — |
| 8.4 | Precizie / recall semnale | OK, din cod | `evaluation.json → detectie.per_semnal`: precizie = recall = F1 = 1,0 pe toate semnalele (ex. expirare 370 TP, 0 FP, 0 FN) | P2 | În pitch: „semnale plantate în date sintetice”, ca F1 = 1,0 să nu pară suspect |
| 8.5 | Cifrele scrise de mână în README | FAIL | `README.md:168–184` are cifrele **vechi**: etalon „agent 288.544 RON … uniform 0,6 pp 309.669”, „15 / 56 (27 %)”, „191 / 289 (66 %)”, „48 / 49”, „flux 0,65 s”; scară „27,1 M … 28,9 M … 79 %”, „19.236 / 26.260”, „flux 38,5 s”. Real acum: 25,79 M / 28,98 M / 78 %, 19.247 / 26.294, 58 / 59, 57,5 s. Plus „192 teste” (real 199), „50 de scenarii” în titlul tabelului (real 60) | P1 | Regenerează tabelele din `out/evaluation.json` (sau scrie „vezi Reports / evaluation.json”); actualizează contorii |
| 8.6 | Cifrele din UI | OK, din cod | Reports citește `/api/metrici`, `/api/model`, `/api/metrici/context` (calculate la pornire). Excepție: mockup-ul de pe landing are cifre ilustrative fixe („Q2263”, „4,117 → 3,058”, „18 % was 62 %”, „36 / 40”) | P2 | Etichetă mică „illustrative” pe mockup sau cifre din snapshot |
| 9.1 | Explain pe cazul principal (Q2313 / C0001, expirare fixă) + 2 aleatorii (Q2653, Q1236) | OK | toate rc=0; 99 / 92 / 95 de linii; cifre RON 23 / 17 / 18; surse etichetate `[ANAF]`, `[Biroul de Credit]`, `[CRC]`, `[OCPI]`, `[evaluator]`; reguli explicite („cost ≤ p×V”, „țintă ≤ 20 %”, „depășește bugetul 0,4 pp pentru gold”, „DTI 33 % = rate / venit”) | — | — |
| 9.2 | Cazul principal de demo | ATENȚIE | Q2313 (C0001, scenariul din MODEL_FINAL: expirare fixă, fix 3 ani) iese **„OFERTĂ MINIMĂ … peste plafonul lunar (2.044.896 > 2.000.000 RON) — amânată”**. Bugetul ordonează după V_reținut/cost, iar cazul vine ultimul care nu mai încape | P1 | Pentru demo: arătați un caz în buget sau prezentați amânarea ca funcționalitate („bugetul de portofoliu în acțiune”); alternativ plafon 2,1 M în `retention.yaml` |
| 9.3 | Fluxul consilierului în UI | OK | Clonă, `api` pe 8002 + Vite pe 5190, Playwright: landing → Sign in → Ana Pop / `1234` → My desk → My queue → Q0006 → Decide → Approve → toast + „decided · approved”; Q2286 → Change → `informare` + motiv → toast. `out/approvals.json`: Q0006 `aproba`, `ana.pop`, `override: false`; Q2286 `modifica`, `override: true`, motivul, versiunea; `audit.jsonl` are linia de override. Admin: Overview, Reports (graficul de calibrare randat), Rules engine. **Consola: 0 erori** | — | — |
| 9.4 | Avertismente în consolă | ATENȚIE | 2 warning-uri React Router „v7_startTransition / v7_relativeSplatPath” pe fiecare pagină | P2 | `future` flags în `BrowserRouter` |
| 9.5 | Detalii UI | ATENȚIE | (a) Un credit nou (Q2286, `oferta_minima` cu `tip: produs_nou`) apare ca badge „Keep: retention offer”. (b) În Decision la un credit nou, lista „Intervention instead” arată tot meniul de retenție cu „0 RON · p after 0 % · infeasible”. (c) Repornirea API-ului delogează pe toată lumea (sesiuni în memorie) | P2 | (a) badge „New credit” când `oferta.tip = produs_nou`; (b) ascunde intervențiile infezabile pentru credite noi; (c) de știut la demo: nu reporniți serverul în timpul prezentării |
| 10 | Suita de teste | OK | `python -m pytest -q -p no:anyio` pe clonă: **199 passed** în 126 s, 0 eșecuri | — | — |

## Lista P0, în ordinea reparării

1. **Cifra-vedetă „la aceeași rată de rămânere” (8.1)** — ~45 min.
   - `evaluate_final.cifra_vedeta`: când `uniform_aleasa` e null, raportează **cost per client păstrat** (agent vs.
     uniform cu retenție maximă) și diferența de retenție, nu `economie_ron` brut.
   - Pe 10k: 12.250 vs. 17.257 RON per client păstrat (−29 %), retenție 98 % vs. 78 %.
   - Reports: primul card „Cost per client kept” cu nota „98 % kept vs. 78 % for a 0.6 pp cut for everyone”.
   - README: tabelul cifrei-vedete.
   - Un test care verifică semnul și eticheta pe etalon.

Nu am găsit alte P0: toate cerințele dure sunt la 0, demo-ul rulează cap-coadă, iar testele trec.

### Status P0 (după audit)

**Reparat.** Încercarea „cost per client păstrat” s-a dovedit și ea înșelătoare: pe etalonul de 50, agentul costă cu
94 % mai mult per client păstrat decât 0,2 pp pentru toți. Așa că afirmația aleasă e **dominanța**: față de cea mai
generoasă reducere uniformă (0,6 pp pentru toți), agentul e mai ieftin **și** păstrează mai mulți clienți. Afirmația e
adevărată pe toate cele trei seturi:

| Set | Agent | 0,6 pp pentru toți | Diferență |
|---|---|---|---|
| 10.000 de clienți | 25,79 M RON, 98 % păstrați | 28,98 M RON, 78 % | −3,19 M RON, +20 pp |
| Etalon 50 | 288.494 RON, 95 % | 309.669 RON, 67 % | −21.175 RON, +29 pp |
| Etalon 60 | 356.460 RON, 96 % | 400.009 RON, 65 % | −43.549 RON, +31 pp |

Ce s-a schimbat:

- **`evaluate_final.cifra_vedeta`** are câmpurile `aceeasi_rata`, `comparator`, `domina`, `diferenta_retentie_pp`,
  `uniform_ieftina` și `cost_per_client_in_plus`. „La aceeași rată” apare doar dacă o reducere uniformă chiar ajunge la
  rata agentului. Pentru transparență se raportează și costul pe clientul păstrat în plus față de cea mai ieftină
  reducere uniformă: 30.758 RON pe etalonul de 50, 11.106 RON pe cel de 60.
- **Reports:** cardul „Cheaper than 0.6 pp for everyone · and keeps 20 pp more clients (98 % vs 78 %)”, iar nota din
  [01] nu mai pretinde aceeași rată.
- **README:** tabelele cifrei-vedete, pe etalon și la scară.
- **Teste:** `test_cifra_vedeta` actualizat, plus `test_cifra_vedeta_pe_etalon_nu_promite_aceeasi_rata`.

## P1 recomandate înainte de joi (dacă e timp)

| Ordine | Punct | Estimare |
|---|---|---|
| 1 | 8.5 + 1.2 README: cifre, timpi, contori (199 teste, 60 scenarii) | 30 min |
| 2 | 9.2 cazul principal amânat: decide scenariul de demo (alt caz sau narativ „buget în acțiune”) | 10 min (decizie) / 5 min (plafon) |
| 3 | 7.3 calea modelului relativă la proiect în `churn/model.py` | 10 min + test |
| 4 | 2.3 `recommend` CLI să aplice bugetul de portofoliu | 15 min + test |
| 5 | 7.4 o frază onestă despre AUC în pitch / README | 10 min |

Artefactele auditului (loguri, scripturile `hard_rules.py` și `checks_audit.py`, ieșirile celor 3 rulări) sunt în
scratchpad-ul sesiunii, nu în repo.
