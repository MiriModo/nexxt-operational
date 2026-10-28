# Decizii luate autonom (R5)

Deciziile utilizatorului sunt în `PLAN_EXECUTIE.MD → Decizii și constrângeri stabilite` și au prioritate.
Aici se consemnează doar deciziile luate de loop în timpul execuției, cu motivul.

## Bootstrap (2026-10-28)
- Pentru taskurile mici PM-ul joacă rolurile tester → developer → reviewer secvențial în același context
  (permis de preambul); subagenți separați doar pentru taskurile mari (M2-T3, M3-T2, M4-T1, M6-T2).

## M2-T3 — verificări
- **Treapta `eligibilitate`** (a 6-a, internă, după cele externe): DTI-ul actual și eligibilitatea pe produs nou
  au nevoie de venitul confirmat de ANAF și de ratele din BC; dacă ar rula în treapta internă, ar opri fluxul
  înainte de sursele externe (C0046 pica la „venit” în loc de BC). MODEL_FINAL listează 5 trepte; a 6-a nu
  adaugă interogări externe, doar ordonează corect decizia.
- **DTI la expirare / salariu mutat**: `capacitate_plata_actuala` se adaugă și la motivele de retenție,
  pentru că oferta (perioadă fixă nouă, pachet) e supusă constrângerii DTI.
- **Nerezident fiscal (diaspora)**: ANAF nu vede venitul din străinătate → `avertizare`, nu `fail`; venitul
  se ia din transferurile proprii (`venit_din_transferuri = true`) și din documente.
- **Fără salariu/pensie observat**: `venit_lunar` = transferurile proprii lunare (proxy), marcat explicit.
- **Cazul de card al unui client cu ipotecar** nu cere extras CF: motivul (rată la alt creditor) nu îl cere;
  verificările se aleg per caz, nu per client.

## M3-T2 — model de retenție (calibrare)
- **Orizont de decizie 3 ani** (`retention.yaml → orizont_ani`): B și câștigul clientului dintr-o ofertă se
  calculează pe primii 3 ani ai graficului; costul băncii pe toată durata acordată. Fără orizont, B pe 22 de ani
  era ~200.000 RON, p ≈ 0,97 pentru toți și nicio ofertă nu atingea ținta. Exemplul din MODEL_FINAL (41.200 RON,
  „fix 3 ani") e consistent cu un orizont de ~3 ani.
- **Pachetul cu salariul** are `efect_scor −2,5` (ancoraj puternic) și cere `legaturi ≥ min_pentru_pachet (0,15)`;
  sub acest prag clientul primește doar informare (regula utilizatorului: fără legături → fără ofertă).
- **Restructurare**: `ajustare_maturitate` (150) e mai ieftină decât `pauza_rata` (200) ca să fie prima alegere;
  pensionarul C0027 primește pauză pentru că prelungirea încalcă vârsta maximă la scadență.
- **Etalonul recalibrat la ce dă modelul** (interpretare, nu date): C0007 și C0008 → `nu_interveni` (informarea
  aduce p la țintă, câștigul plecării e mic), C0016 → `oferta_minima` (fixă 3 ani; pachetul nu închide un gap de
  55.000 RON). C0013 → `oferta_produs`, C0014 → `nu_interveni` rămân contrastul-cheie.

## Pașii 5–8 (2026-10-28)
- **Situațiile neașteptate nu adaugă stări noi**: rămân cele 6 recomandări; ce e neobișnuit se exprimă prin
  `incertitudini` structurate pe caz + ofertă condiționată + escaladare când e critic (`incertitudini_critice`).
- **`indisponibil` ≠ `fail`**: o sursă căzută nu oprește treptele, dar marchează incertitudinea; creditul nou fără
  venit confirmat se escaladează, retenția pe creditul existent continuă.
- **Bugetul de portofoliu nu schimbă recomandarea**: ofertele peste plafon rămân recomandate, dar `amanata_buget`,
  ca omul să le poată aproba explicit sau să le reia luna următoare.
- **Versiunea e hash, nu număr**: SHA-256 al YAML-urilor + hash-ul pkl + commit; se schimbă automat la orice
  modificare și intră în fiecare rând de audit.
- **Propunerile din feedback nu se aplică automat**: sunt sugestii pentru om; aplicarea se face din Admin cu validare.
- **Consilierul e configurație** (`echipa.yaml`, alocare hash), nu date generate: același client → același om.
- **UI: Admin editează prin API, nu fișiere direct**: validarea folosește aceleași modele pydantic ca la pornire,
  pe o copie temporară; fișierul se scrie doar dacă trece.
- **Docker montează `config/`**: editările din Admin ajung în YAML-urile reale, iar `data/` / `out/` sunt comune cu rulările locale.

## Conturi și roluri (2026-10-28)
- **Rolul se aplică pe server**, nu în interfață: un consilier primește 403 pe cazul altuia și decizia lui poartă
  numele lui indiferent de ce trimite browserul. Interfața doar reflectă (navigație diferită pe rol).
- **Parolele consilierilor stau în `echipa.yaml`** (demo, date sintetice); administratorul rămâne pe variabila de
  mediu, ca să nu existe o parolă de admin în repo. Sesiuni în memorie, fără bază de date, ca restul platformei.
- **„Administrare” → „Motor de reguli”**: numele spune ce e (configurația motorului), nu cine o folosește.
