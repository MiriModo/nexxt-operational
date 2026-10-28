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
