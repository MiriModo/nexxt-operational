# Jurnal per task

## M0 — bootstrap (2026-10-28)
- git init, remote origin, .gitignore, vault inițializat; baseline 66 teste verzi, compileall OK.

## M1-T1 — finance.py (done)
- `rata_anuitate`, `luni_ramase`, `grafic`, `dobanda_totala`, `segmente_credit`, `comision_rambursare_anticipata`,
  `dti`, `varsta_la`; generator comun `_iter_scenariu` (re-amortizare la fiecare schimbare de dobândă).
- 7 teste în `tests/test_finance.py` (anuitate pe caz cunoscut, grafic stinge soldul, re-amortizare, OUG 50).
- Lecție: în heredoc-uri bash, `\N` din `C:\dev\NEXXT` sparge string-urile Python → scripturile se scriu în fișier.

## M1-T2 — constraints.yaml + retention.yaml + modele pydantic (done)
- `ConstraintsConfig` (dti, ltv, varsta, marja_minima_pp, restructurare), `RetentionConfig` (p_tinta, sigmoid a/b/c/d,
  B_referinta, semnale_active, legaturi, valoare, piata, 12 intervenții, oug50), `Config` are acum 4 config-uri.
- Validări: id-uri duplicate, p_tinta ∈ (0,1), chei de piață din `CHEI_PIATA`, tip intervenție din enum,
  ponderile legăturilor însumează 1, semnalele referite există, nivelurile au buget în priority.yaml.
- 5 teste în `tests/test_config_final.py` (copie a config-ului în tmp + rescriere YAML pentru cazurile negative).
- `checks.yaml` se adaugă la M2-T1 (câmp nou în `Config`, cu același tipar).

## M1-T3 — scenariul 14 = cazul opus lui C0013 (done)
- `S.ani_client` (vechimea relației, aplicată după apelul rng ca fluxul aleator să rămână identic),
  `plant.cont_nefolosit` (ieșirile din ultimele 2 luni se filtrează în `tx()`, tot fără să atingă rng),
  scenariul 14: salariu mutat la altă bancă, standard, 1 produs, 1,5 ani vechime → GT `nu_interveni`.
- ANAF pentru C0014 arată salariul în continuare (`anaf: salariu_continua`); `venit_disparut` plantat la 2 clienți.
- Metricile Modulului 1 rămân 100% (verificat cu `evaluate`); suita completă verde.
- Lecție: orice plantare nouă în generator trebuie să nu schimbe numărul de apeluri rng, altfel se mută
  valorile tuturor clienților următori.

## M2-T1 — checks.yaml + ChecksConfig (done)
- 18 verificări pe 5 trepte (intern, anaf, biroul_credit, crc, garantie), straturi baza / produs / motiv,
  `necesita_consimtamant` pentru ANAF și BC, `parametri` per verificare.
- `motive`: chei = semnale + tipuri de cereri + `risc` + `blocaj` (validat încrucișat în `Config`);
  `blocaj.doar = [identitate_kyc]`; `adauga` câștigă în fața lui `sare` (regula se aplică în M2-T2).
- `documente_necesare` per tip de recomandare (valabil / max_zile / tipologii / produse).
- 4 teste noi în `tests/test_config_final.py`.

## M2-T2 — checks.py: plan_checks (done)
- `motive_caz` (blocaj, risc, cereri, semnale — în această ordine) și `plan_checks(case, client, loans, cereri, cfg)`
  → `{motive, produse_detinute, plan[{id, treapta, externa, motiv}], omise[...], interogari_externe{planificate,
  rulare_tot, evitate_vs_tot}}`. Produsele deținute = toate creditele clientului, nu doar cel din caz.
- Baseline „rulează tot" = toate verificările externe aplicabile (produs + consimțământ).
- 6 teste în `tests/test_checks_plan.py` (expirare, simulare, credit nou, risc + adauga>sare, blocaj, consimțământ).

## M2-T3 — checks_run.py + CLI (done)
- `checks_run.py`: `Mocks`/`load_mocks`, `CheckContext`, registru `@check(id)` cu 18 funcții, `run_checks` în trepte
  cu oprire la primul `fail`; concluzii agregate (venit observat/ANAF, salariu_la_alta_banca, DTI, LTV dosar/actual,
  interogări BC, cost mutare, scenarii, eligibil). `checks.py`: `build_context`, `check_registry`, `run_all_checks`,
  `print_plan` (planul cu motive ÎNAINTE de rezultate), CLI → `out/checks.json`.
- Pe date: C0046 → biroul_credit, C0047 → crc, C0005 → garantie (extras CF cu litigiu); C0013/C0014
  `salariu_la_alta_banca = true`; 191/289 interogări evitate (66%); 0,26 s pe 67 de cazuri.
- 8 teste de integrare în `tests/test_checks_run.py`. Suita: 97 verzi.
- Lecție: `cat >> f <<'EOF'` cu conținut Python lung a picat în shell; scrierea cu Write + patch-uri mici e sigură.
  `\n` în f-string-uri scrise prin heredoc Python trebuie dublat (`\\n`).

## M3-T1 — retention.py: B, legături, V, p (done)
- `castig_plecare` (B = dobândă la noi − dobândă piață − cost mutare, pe grafice; B = max(0, brut)),
  `legaturi` (produse active fără cont_salariu mutat, vechime, nivel, activitate = ieșiri ≥ 1.000 RON în 2 luni),
  `valoare_client`, `semnale_active` (+ interogări BC ≥ 2), `prob_plecare` (sigmoid cu B_norm plafonat).
- `finance.cost_mutare_total` extras din checks (un singur loc). Pe date: B(C0001 ipotecar) > 50k, B(card) < 500,
  legături C0013 = suficiente, C0014 = sub prag.
- 6 teste în `tests/test_retention_model.py`.

## M3-T2 — retention_menu.py: meniu + constrângeri + optimizare (done)
- `_fezabilitate` (necesita, risc, legături, buget pe nivel, marjă minimă, chei de piață, vârstă la noua scadență,
  DTI pentru pachet), `_cost_si_castig` (cost bancă pe toată durata / câștig client pe orizont), `evalueaza_interventii`,
  `alege_interventie` (regula din plan), `evalueaza_caz`. `finance.dobanda_perioada` nou.
- Distribuție pe date: ajustare_maturitate 22, pauza_rata 10, fix_3_ani 5, pachet_salariu 1, informare 3,
  nu_interveni 15, blocate 11. 8 teste în `tests/test_retention_menu.py`. Suita: 111 verzi.
- Lecție: calibrarea modelului trebuie verificată pe toate cazurile (tabel cu B, V, legături, p, alegere) înainte de
  a fixa etalonul; heredoc-urile bash lungi pică — patch-urile se scriu în fișier și se rulează.

## M3-T3 — CLI retention → out/offers.json (done)
- `build_offers` (un rând per caz: B, p, V, legături, semnale active, intervenția aleasă, cost, p după, alternative,
  meniul complet), `explicatie_oferta` (text pentru consilier, 4 forme: ofertă / informare / nu interveni / restructurare
  / blocat), `print_offer`, `main` (`--case`, `--top`). 4 teste în `tests/test_retention_cli.py`.
- Modulele de retenție: `retention.py` (model + CLI), `retention_menu.py` (meniu, constrângeri, optimizare).

## M4-T1 — recommend.py (done)
- `recomanda` (ordinea: blocat → verificare picată → risc/cerere restructurare → cerere produs nou → nu_interveni /
  oferta_minima / oferta_produs), `oferta_din_interventie` (dobândă nouă, rată nouă, perioadă, grafic 12 luni + totaluri;
  pauza de rată capitalizează dobânda), `oferta_produs_nou`, `documente_lipsa` (reguli din checks.yaml), `explicatie`
  (română, cu cifre și sursa), `audit_rows` (semnal / verificare / retentie / decizie), CLI → recommendations.json + audit.jsonl.
- 8 teste în `tests/test_recommend.py` (schemă, acuratețe ≥ 90% vs etalon, respins la verificări picate, 0 oferte la risc/blocat,
  grafic, documente lipsă, audit, CLI).
- Pe date: 98% (48/49) vs etalon; diferența C0049 (diaspora, variabil cu gap 3 pp → agentul propune fixă 3 ani) e lăsată
  vizibilă, de discutat cu mentorul.

## M4-T2 — approve.py (done)
- `decide` (pur: validează decizia, motivul obligatoriu la modifica/respinge, intervenția din meniu + fezabilă, recalculează
  oferta și graficul pentru intervenția aleasă de om), `persist` (approvals.json + rând `aprobare`/`override` în audit.jsonl),
  CLI cu afișarea ofertei, graficului și documentelor lipsă; `ApprovalError` → `SystemExit` cu mesaj clar.
- `recommend` scrie acum și `offers.json`. 7 teste în `tests/test_approve.py`.

## M5-T1 — explain extins + pipeline.run_full (done)
- `pipeline.py`: `FullRun` (pf, cfg, res, mocks, checks, offers, recs, audit; `by_case`) + `run_full` — sursa unică pentru
  explain / evaluate / demo (CLI-ul vine la M6-T1).
- `explain.py`: `explain_checks` (motive, plan cu motive, omise, rezultate, interogări), `explain_retention` (B descompus,
  legături pe componente, semnale active, formula p, V, tabel intervenții cu ► pe cea aleasă), `explain_recommendation`
  (stare, motiv, ofertă, grafic, documente, text); `explain_full`; CLI cu `--scurt` pentru varianta veche.
- 4 teste în `tests/test_explain_full.py` (toate cazurile au cele 6 secțiuni).

## M5-T2 — evaluate extins: secțiunea „Model final" (done)
- `evaluate_final.py`: `ramane` (simularea comportamentului ascuns), `candidati_retentie`, `cifra_vedeta` (agent vs uniform
  0,2/0,4/0,6 pp la aceeași rată de rămânere), `procent_nu_interveni`, `interogari_evitate`, `eval_recomandari` (matrice 7×7),
  `eval_verificari`, `cerinte_dure_final` (oferte către risc, în afara limitelor — re-verificate din date —, pe cazuri blocate,
  expirări < 30 zile), `raport_model_final`, `print_model_final`. `evaluate.main` rulează `run_full` și scrie `model_final`.
- Rezultat pe date: agent 288.544 RON, 20/21 reținuți (95%); uniform 0,6 pp 309.669 RON, 71%; nu interveni 27%;
  interogări evitate 66%; recomandări 98%; verificări picate 3/3; 0 încălcări; flux complet 0,48 s.
- 6 teste în `tests/test_evaluate_final.py`.
- Lecție: `\n` în heredoc-uri bash se transformă în newline real chiar cu delimitator quotat → pentru patch-uri cu `\n`
  se folosește Edit, nu heredoc.

## M6-T1 — pipeline CLI (done)
- `run_full` rulează acum pașii explicit (scan → intake → queue → checks → retention → recommend) cu cronometrare per pas;
  `ARTEFACTE`, `write_artifacts`, `main` (`--skip-evaluate`, `--skip-demo`; demo se apelează dacă modulul există).
- Pe 50 de clienți: ~0,6 s fără evaluate (limita: 5 s). 2 teste în `tests/test_pipeline.py` (artefacte + schema queue.json
  neschimbată + timp; varianta cu evaluate).

## M6-T2 — demo.html (done)
- `demo.py`: `_case_payload` (doar câmpurile necesare din case / check / offer / rec), `build_html` (JSON încorporat în
  `<script id="data" type="application/json">`, `</script` escapat), `TEMPLATE` (CSS cu tokeni + dark mode, JS vanilla:
  KPI-uri, filtre pe bandă / cu ofertă / blocate, căutare, panou caz cu semnale, verificări planificate / omise / rezultate,
  tabel intervenții, recomandare, ofertă, grafic, documente, butoane Aprobă / Modifică / Respinge → comanda `approve`).
- Fără resurse externe; ~700 KB. 4 teste în `tests/test_demo.py` (parser HTML: fără `<script src>`, date încorporate, UI, CLI).

## M6-T3 — README + zip final (done)
- README rescris integral: schema fluxului, setup în 3 comenzi (`generate` → `pipeline`), toate comenzile, tabelul de
  rezultate cu cifra-vedetă, cele 4 secțiuni ale modelului cu formulele B / legături / p / V, constrângeri, optimizare,
  exemplul C0013 vs C0014, datele, „cum adaugi ceva nou", tabelul de interpretări (12 rânduri), structura.
- `tests/test_readme.py` (2 teste). Arhiva `NEXXT_retailagent_2026-10-28_final.zip` (87 fișiere, 0,5 MB, cu `out/`,
  fără cache / PDF / .git).

## Upgrade pasul 1 — portofoliu realist la scară (2026-10-28, după loop)
- `config/portofoliu.yaml` + `profil.py` (pydantic); `generate.sample_scenario` produce obiecte S/L/R din distribuții
  (triunghiular), semnale cu probabilități și corelații, cereri, plante externe; `Generator` cu RNG separat după cei 50,
  bazin de angajatori, zgomot de tranzacții din profil; `generate_ext` cu plante per client, comportament cu structură;
  `evaluate` filtrează pe `etalon`, `--scale N` rulează fluxul complet + metrici; `demo --max-cazuri`; `churn/labels.py`.
- `checks.build_context` avea o căutare liniară pe toate creditele per caz (81 s la 10.000) → index de codebitori (5,9 s).
- Plantări corectate: salariu_mutat / venit_scadere doar la SL (tinerii au 4 luni de istoric); cont_nefolosit exclude
  rata la alt creditor și poprirea (ieșirile dispar). F1 la 10.000: 1,000.
- Rezultate: generare 31 s, flux 38,5 s, F1 1,000, 0 încălcări, agent 98% vs uniform 79%; 11 teste noi (159 total).

## Upgrade pasul 2 — model de churn antrenat (2026-10-28)
- `churn/features.py` (33 feature-uri, ordine fixă, schema v1), `churn/model.py` (`ChurnModel`, `SigmoidChurn`, `TrainedChurn`,
  `get_model` cu fallback), `churn/train.py` (split pe clienți, logistic vs boosting, Brier decide, calibrare ECE, artefact
  pkl + json, `--din-approvals` schelet), `retention.yaml → churn`, `retention_menu` folosește modelul (batch pe meniu),
  `evaluate` → „sigmoid vs antrenat", `explain`/demo → contribuții pe logit. `scikit-learn` în requirements.
- Test de aur: cu `sigmoid`, cifrele sunt identice. Model v1: logistic, AUC 0,98, Brier 0,045, ECE 0,024 (învață generatorul).
- Lecție: `build_offers` copiază explicit câmpurile din evaluare; un câmp nou în `evalueaza_interventii` trebuie adăugat și acolo.

## Upgrade pasul 4 + merge UI (2026-10-28)
- Utilizatorul a adus `ui/` (Vite + React + TS, 5 ecrane) scris pe contractul din demo.html, cu strat `src/api/client.ts`
  pregătit pentru API. Merge: `demo.build_data` (snapshot comun), `demo.sync_ui` → `ui/public/data`, `api.py` (FastAPI,
  rutele așteptate de UI, decizii prin `approve.decide/persist`), tipuri + Caz.tsx cu modelul antrenat și contribuțiile,
  `ui/` intră în git (scos din `.git/info/exclude`; `public/data`, `dist`, `node_modules` ignorate). 5 teste API (TestClient).
- Dependențe noi: fastapi, uvicorn, httpx (teste).

## Platforma pe 10.000 de clienți implicit (2026-10-28)
- `generate --n` implicit 10.000; `data/` scos din git (regenerabil din seed, ~150 MB). `GET /api/cazuri` compact
  (`compact_caz`: aceeași formă, fără liste mari) + `?limit`, `?banda`, `?q`; detaliul din `GET /api/cazuri/{id}`.
  `api.py` inițializează starea în lifespan, nu la import (importul citea `data/` pe jumătate scris în timpul generării).
  `evaluate` face comparația sigmoid vs antrenat doar ≤ 500 clienți sau cu `--compara-churn`.

## Raport final — OBIECTIV ATINS (2026-10-28)
- 16/16 taskuri done; 148 teste verzi; compileall OK; metricile Modulului 1 neschimbate (F1 1,00, 100%, 708/708, 0, 5/5).
- Model final: agent 288.544 RON / 95% reținuți vs uniform 0,6 pp 309.669 RON / 71%; nu interveni 27%; interogări evitate 66%;
  recomandări 98%; verificări picate 3/3; 0 încălcări; flux complet 0,65 s; demo.html verificat în browser.
- Deschise pentru mentor: calibrarea parametrilor (orizont, sigmoid, efect pachet), C0049, validarea pe date reale.

## Pașii 5–8 din roadmap (2026-10-28)
- **M6 situații neașteptate**: etalonul crește la 60 de scenarii (51–60: valută, codebitor cu risc, semnale
  contradictorii, cerere duplicată, fără cont, ANAF indisponibil, surse contradictorii, decedat, PEP, refinanțare
  externă în curs); status `indisponibil`, `CheckResult.incertitudine`, `rec.incertitudini`, `incertitudini_critice`
  → escaladare, ofertă condiționată; EUR normalizat în RON (`curs_eur`), semnale `expunere_valutara`, `codebitor_cu_risc`;
  `buget.py` (plafon 2 M RON / lună, ordonare V_reținut / cost). `tests/test_situatii.py` (12).
- **M7 feedback + versionare**: `versiune.py` (hash YAML + model + commit) în recs / audit / evaluation / context;
  `echipa.yaml` + `consilier` pe decizii; `--rezultat ramas|plecat`; `feedback.py` (override pe intervenție / nivel /
  produs / consilier, rămânere reală vs prezisă, propuneri). `tests/test_feedback.py` (5).
- **M5 UI**: React Query, Admin (YAML cu validare pe server, diff git, re-rulare), trepte „în timp real" cu
  Reverifică, filtre recomandare / consilier, istoric + rezultat 90 zile în Decizie, Dashboard cu calibrare / feedback /
  versiune; `npm run types` (openapi-typescript). Verificat în browser pe fiecare ecran (Playwright). Suita: 192 teste.
- **M8 ambalare**: `Dockerfile.api` (+ `docker/entrypoint.sh`: generează date / antrenează la prima pornire),
  `ui/Dockerfile` (Vite → nginx cu proxy /api), `docker-compose.yml`, `Makefile`, `docs/REGULI.md`, README cu cele
  trei moduri de rulare.
- Lecții: modelele pydantic pentru body-uri trebuie la nivel de modul (în `create_app` FastAPI le tratează ca query → 422);
  `vite.config.ts` nu poate folosi `process` fără `@types/node` → `loadEnv`; `.treapta` ca bloc, nu pilulă.
- Neterminat din roadmap: pasul 3 (agentul LLM pentru ofertă; cere `ANTHROPIC_API_KEY` în mediul utilizatorului) și
  introducerea de date noi prin API (`POST /api/cereri`, `POST /api/evenimente`).
