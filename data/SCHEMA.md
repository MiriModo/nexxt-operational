# Schema bazei de date (`data/`)

Baza de date a proiectului nu este un SGBD, ci 14 fișiere JSON în `data/`, legate prin
`client_id` și `loan_id`. Schema de mai jos este dedusă direct din conținutul fișierelor
(tipuri + valorile enumerative întâlnite). Stare la 2026-10-28.

Convenții: datele sunt `str` în format ISO (`YYYY-MM-DD`), lunile `YYYY-MM`, sumele în RON.
Numărul din paranteze pătrate este numărul de înregistrări.

## Relații

```text
employers 1 ─── N clients
clients   1 ─── N loans, transactions, requests
clients   1 ─── 1 conturi, documente, externe/anaf, externe/biroul_credit, externe/crc, ground_truth
loans     1 ─── N payment_history
loans     1 ─── 0..1 externe/garantii        (doar creditele cu garanție imobil)
market    obiect unic (parametri de piață)
```

## Entități interne

```text
clients.json  [50]                      PK: client_id
  client_id, nume, data_nasterii, ci_expira_la, kyc_actualizat_la, client_din   (str / date ISO)
  nivel_relatie        : standard | gold | platinum
  tipologie_declarata  : salariat | independent | pensionar | antreprenor | tanar_fara_istoric | diaspora
  consimtamant_anaf, consimtamant_biroul_credit, flag_pep, flag_frauda_interna, flag_decedat : bool
  angajator_id         : FK -> employers
  produse_atasate      : [cont_salariu | cont_curent | card_debit | economii | depozit | asigurare_viata | pensie_privata]

employers.json  [17]                    PK: angajator_id
  angajator_id, nume, client_al_bancii: bool
  status                : activ | insolventa | dizolvare
  trend_plati_salarii_3l: float

conturi.json  [50]                      1:1 cu client
  client_id (FK), iban, moneda, sold_curent: float
  istoric_lunar[] : { luna "YYYY-MM", sold_mediu, sold_minim, intrari, iesiri : float }

loans.json  [68]                        PK: loan_id, FK: client_id
  produs            : ipotecar | imobiliar | refinantare | nevoi_personale | card_credit
  moneda            : RON
  suma_initiala, sold_ramas, rata_lunara, dobanda_curenta, marja : numeric
  data_acordare, data_scadenta, dobanda_fixa_expira_la : date | null
  tip_dobanda       : fixa | variabila
  indice            : IRCC | null
  restructurat_anterior : bool
  restructurari[]   : { data, tip (ex. prelungire_perioada) }
  garantie          : null | { tip: imobil, valoare_evaluare, data_evaluare, asigurare_expira_la }
  codebitori[]      : { client_id, nume, rol: codebitor }
  limita, utilizare_limita : null | (int, float 0..1)   -- doar card_credit
  prima_locuinta    : bool

payment_history.json  [1530]            FK: loan_id, cheie naturală (loan_id, luna)
  luna "YYYY-MM", zile_intarziere: int, suma_restanta: int
  plata_minima_card: bool, rambursare_anticipata: int

transactions.json  [4753]               FK: client_id
  data, suma: float, platitor_beneficiar
  directie      : in | out
  tip_etichetat : salariu | pensie | chirie_in | dividende | transfer_propriu | extern
                | utilitati | chirie_out | rata_alt_creditor | poprire | altele

documente.json  [50]                    1:1 cu client
  documente[] : { tip, referinta: str|null (loan_id), data_emitere, valabil_pana }
  tip : carte_identitate | adeverinta_venit | contract_credit | raport_evaluare | extras_cf
      | polita_asigurare_imobil | declaratie_unica | decizie_pensie

requests.json  [10]                     PK: request_id, FK: client_id
  data
  tip     : adeverinta_sold | simulare_rambursare_anticipata | refinantare | restructurare
          | credit_nou | majorare_limita_card | actualizare_date
  detalii : { produs_vizat, suma? }
```

## Surse externe (`data/externe/`)

```text
anaf.json  [50]                         1:1 cu client
  rezident_fiscal : RO | strainatate
  perioada        : { de_la, pana_la }
  surse[] : { tip: salariu | activitati_independente | pensie | cedarea_folosintei | dividende,
              platitor, frecventa: lunar | anual, valori: { "YYYY-MM": float } }

biroul_credit.json  [50]                1:1 cu client
  fara_istoric: bool, scor: int, interogari_ultimele_6l: int
  credite[] : { institutie, tip: card_credit | nevoi_personale, rol: debitor, stare: activ | inchis,
                data_acordare, data_inchidere, sold, rata_lunara, max_zile_intarziere_24l }

crc.json  [50]                          1:1 cu client
  luna_raportare, prag_raportare_ron: int
  expuneri[] : { institutie, rol, tip, sold: float, restante, zile_restanta }

garantii.json  [30]                     PK: loan_id (doar creditele cu garanție imobil), FK: client_id
  reevaluare : { valoare, data, metoda: indexare_statistica }
  cf         : { numar, uat, ipoteca_rang_1_banca: bool, alte_sarcini[],
                 litigii[]: { tip, dosar, notat_la }, interdictii[]: str }
  asigurare  : { asigurator, polita, expira_la, cesionata_bancii: bool }
```

## Referință și etalon

```text
market.json  (obiect unic)
  data, ircc, dobanda_fixa_piata_ipotecar, dobanda_piata_nevoi_personale, dobanda_piata_card
  dobanzi_piata[produs]  : { fixa_1_an, fixa_3_ani, fixa_5_ani, marja_variabila }
                           sau { fixa_toata_durata }           (nevoi_personale, card_credit)
  costuri_mutare[produs] : { evaluare_imobil, notar_fix, notar_pct_sold, ocpi, asigurari_noi,
                             comision_analiza_banca_noua, comision_acordare_pct }

ground_truth.json  [50]      1:1 cu client (etalonul folosit de evaluate.py)
  semnale_plantate[]        : expirare_dobanda_fixa | intarziere_noua | cerere_adeverinta_sold
                            | rata_alt_creditor | simulare_in_app | salariu_mutat | venit_disparut
                            | ci_expirata | venit_in_scadere | card_stres | angajator_in_dificultate
                            | consimtamant_lipsa | asigurare_expirata | flag_blocant | ltv_depasit
                            | kyc_vechi | restructurare_anterioara | poprire_activa
  banda_asteptata           : P1 | P2 | P3 | null
  actiune_asteptata         : retentie_refinantare | restructurare_preventiva | monitorizare
                            | procesare_cerere | task_ci_expirata | task_consimtamant_lipsa
                            | task_asigurare_expirata | task_flag_blocant | task_kyc_vechi | null
  recomandare_asteptata     : str
  verificare_picata_asteptata : str | null
  nota_model_final          : str
  comportament : { prag_castig_plecare_ron: float, reactioneaza_la_informare: bool,
                   accepta_pachet_salariu: bool | null }
```

## Observații

- Nu există modele pydantic pentru aceste fișiere; `config_loader.py` are modele doar pentru
  YAML-urile din `config/`. Încărcarea datelor se face direct din JSON (vezi `retailagent/common.py`).
- `garantii.json` acoperă exact creditele din `loans.json` care au `garantie.tip = imobil` (30).
- `documente[].referinta` leagă un document de un credit (`loan_id`) sau este `null` pentru
  documentele de client (CI, adeverință venit, decizie pensie, declarație unică).
