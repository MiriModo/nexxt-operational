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
