// Contractul de date = structura per caz din out/demo.html (<script id="data">),
// care e și contractul API-ului planificat (GET /cazuri, GET /cazuri/{id}, GET /metrici).

export type Banda = "P1" | "P2" | "P3";
export type Recomandare =
  | "restructurare"
  | "oferta_minima"
  | "oferta_produs"
  | "nu_interveni"
  | "blocat"
  | "respins_escaladat";
/** `indisponibil` = sursa externă nu a răspuns: fluxul continuă, cazul poartă o incertitudine */
export type StatusVerificare = "ok" | "avertizare" | "fail" | "neexecutat" | "indisponibil";
export type Decizie = "aproba" | "modifica" | "respinge";

export interface Semnal {
  id: string;
  familie: string;
  scor: number;
  dovada: string;
}

export interface CaseInfo {
  case_id: string;
  client_id: string;
  loan_id: string | null;
  produs: string;
  sursa: string;
  request_id: string | null;
  semnale: Semnal[];
  scoruri: {
    plecare: number;
    valoare: number;
    actiune: number;
    prioritate_retentie: number;
    risc_credit: number;
    prioritate: number;
  };
  banda: Banda;
  deadline: string;
  motive_top3: string[];
  actiune_propusa: string;
  blocaje: string[];
}

export interface ClientInfo {
  nume: string;
  nivel: string;
  tipologie: string;
  client_din: string;
  produse: string[];
}

export interface LoanInfo {
  sold: number;
  tip_dobanda: string;
  dobanda: number;
  expira: string | null;
  scadenta: string;
  rata: number;
  /** RON | EUR — soldul și rata sunt în RON (la cursul curent); `sold_valuta` e valoarea originală */
  moneda?: string;
  sold_valuta?: number | null;
}

export interface VerificarePlan {
  id: string;
  treapta: string;
  externa: boolean;
  motiv: string;
}

export interface VerificareRezultat {
  id: string;
  treapta: string;
  externa: boolean;
  status: StatusVerificare;
  dovada: string;
  sursa: string;
  incertitudine?: string | null;
}

/** O situație neașteptată tratată prin degradare controlată (id din checks.yaml → incertitudini_critice). */
export interface Incertitudine {
  id: string;
  text: string;
}

/** Răspunsul la POST /api/cazuri/{id}/verifica: verificările reluate, grupate pe trepte, în ordinea rulării. */
export interface Reverificare {
  case_id: string;
  motive: { motiv: string; sursa: string }[];
  plan: VerificarePlan[];
  omise: VerificarePlan[];
  trepte: { treapta: string; stare: "executata" | "oprita" | "neexecutata"; rezultate: VerificareRezultat[] }[];
  oprit_la: string | null;
  verificare_picata: string | null;
  incertitudini: Incertitudine[];
  concluzii: Record<string, unknown>;
  interogari_externe: { planificate: number; rulare_tot: number; evitate_vs_tot: number; executate: number };
}

export interface CheckInfo {
  motive: { motiv: string; sursa: string }[];
  plan: VerificarePlan[];
  omise: VerificarePlan[];
  rezultate: VerificareRezultat[];
  oprit_la: string | null;
  verificare_picata: string | null;
  interogari: { planificate: number; rulare_tot: number; evitate_vs_tot: number; executate: number };
  concluzii: {
    venit_lunar: number;
    venit_lunar_anaf: number;
    dti_curent: number;
    ltv_actual: number | null;
    salariu_la_alta_banca: boolean;
    interogari_bc: number;
  };
}

export interface Interventie {
  id: string;
  eticheta: string;
  fezabil: boolean;
  motiv_infezabil: string | null;
  cost: number;
  B_dupa: number;
  p_dupa: number;
  respecta_tinta: boolean;
  merita: boolean;
}

export interface OfferInfo {
  B: number;
  B_detalii: {
    B: number;
    B_brut: number;
    dobanda_la_noi: number;
    dobanda_piata: number;
    dobanda_pct_piata: number;
    cost_mutare: number;
    luni_ramase: number;
    orizont_luni: number;
  };
  p: number;
  p_tinta: number;
  V: number;
  legaturi: {
    scor: number;
    componente: Record<string, number>;
    produse_active: string[];
    vechime_ani: number;
    iesiri_2_luni: number;
    suficiente_pentru_oferta: boolean;
  };
  semnale_active: string[];
  aleasa: string;
  motiv_alegere: string;
  explicatie: string;
  interventii: Interventie[];
  /** modelul care a dat p: sigmoid (formula din YAML) sau antrenat (models/churn_v<N>.pkl) */
  model?: { nume: "sigmoid" | "antrenat"; versiune: string } | null;
  /** top contribuții ale feature-urilor pe logit (doar pentru modelul antrenat): [feature, delta] */
  contributii?: [string, number][] | null;
}

export interface RataGrafic {
  nr: number;
  luna: string;
  rata: number;
  dobanda: number;
  principal: number;
  sold_ramas: number;
  dobanda_pct: number;
}

export interface RecInfo {
  recomandare: Recomandare;
  eticheta: string;
  interventie: string;
  motiv: string;
  oferta: {
    tip: string;
    dobanda_noua: number;
    perioada: string;
    luni_noi: number;
    rata_veche: number;
    rata_noua: number;
    cost_banca: number;
    economie_client: number;
    conditie?: string;
    /** incertitudini de lămurit înainte ca oferta să fie comunicată */
    conditii_de_confirmat?: string[];
    /** bugetul lunar de retenție pe portofoliu: false = recomandată, dar amânată („peste plafon luna asta") */
    in_buget?: boolean;
    amanata_buget?: boolean;
  } | null;
  grafic: {
    primele_luni: RataGrafic[];
    nr_rate: number;
    dobanda_totala: number;
    total_de_plata: number;
    ultima_luna: string;
  } | null;
  documente_lipsa: { tip: string; motiv: string }[];
  explicatie: string;
  incertitudini?: Incertitudine[];
  buget?: { rang: number; scor_v_pe_cost: number | null; valoare_retinuta: number; cost: number; in_buget: boolean } | null;
  /** rezervat pasului 3 (agentul LLM): argumentul și textul ofertei generate; apare doar când există */
  llm?: { argument: string; text_client: string; model?: string } | null;
}

/** Spending profile over the last months, by payment category (as in the bank's app). */
export interface Cheltuieli {
  luni: number;
  total_out: number;
  total_in: number;
  venit_lunar: number;
  categorii: { categorie: string; suma: number; procent: number; nr: number }[];
  loan_payments: number;
  internal_transfers: number;
}

export interface Caz {
  case: CaseInfo;
  client: ClientInfo;
  cheltuieli?: Cheltuieli;
  loan: LoanInfo | null; // null pentru cereri de credit nou (fără credit existent)
  check: CheckInfo;
  offer: OfferInfo;
  rec: RecInfo;
  /** consilierul alocat (config/echipa.yaml) și versiunea config/model care a produs decizia */
  consilier?: string | null;
  versiune?: string | null;
  /** true pentru rândurile din GET /api/coada (fără liste mari); detaliul vine din GET /api/cazuri/{id} */
  compact?: boolean;
}

export interface Consilier {
  id: string;
  nume: string;
}

/** Biroul consilierului (GET /api/eu/birou): coada lui + activitatea lui. */
export interface Birou {
  utilizator: { id: string; nume: string; rol: "consilier" | "admin" };
  coada: {
    total: number;
    deschise: number;
    p1_azi: number;
    peste_plafon: number;
    de_confirmat: number;
    pe_banda: Record<string, number>;
    distributie: Record<string, number>;
  };
  activitate: {
    decizii: number;
    decizii_azi: number;
    override: number;
    rezultate: { n: number; ramasi: number; plecati: number };
    ultimele: DecizieServer[];
  };
  primele: Caz[];
}

export interface Versiune {
  config: { hash: string; fisiere: Record<string, string> };
  model: { model: string; versiune: string | null; hash: string | null; tip?: string; antrenat_la?: string; n?: number };
  prompturi: null | Record<string, string>;
  cod: string | null;
  scurt: string;
}

export interface BugetPortofoliu {
  plafon_lunar_ron: number;
  ordonare: string;
  oferte: number;
  in_buget: number;
  amanate: number;
  cost_in_buget: number;
  cost_total_oferte: number;
}

export interface ModelInfo {
  activ: Versiune["model"];
  antrenat: {
    versiune?: string;
    tip?: string;
    n?: number;
    n_antrenare?: number;
    n_test?: number;
    antrenat_la?: string;
    metrici?: { auc: number | null; brier: number; ece: number; log_loss: number; bins: { interval: string; n: number; p_medie: number; rata_reala: number }[] };
    coeficienti?: Record<string, number>;
    candidati?: Record<string, { test: { auc: number | null; brier: number; ece: number } }>;
  };
}

export interface Feedback {
  decizii: number;
  override: number;
  rata_override: number | null;
  pe_interventie: Record<string, { decizii: number; override: number; rata_override: number | null }>;
  pe_nivel: Record<string, { decizii: number; override: number; rata_override: number | null }>;
  pe_produs: Record<string, { decizii: number; override: number; rata_override: number | null }>;
  pe_consilier: Record<string, { decizii: number; override: number; rata_override: number | null }>;
  inlocuiri: { agent: string; final: string; n: number }[];
  cuvinte_cheie: [string, number][];
  rezultate_90_zile: { n: number; pe_interventie: Record<string, { n: number; ramasi: number; rata_ramanere_reala: number | null; rata_ramanere_prezisa: number | null }> };
  propuneri: { tip: string; interventie: string | null; text: string }[];
}

export interface ConfigFisier {
  nume: string;
  fisier: string;
  hash: string | null;
  exista: boolean;
}

/** O decizie înregistrată de server (approvals.json). */
export interface DecizieServer {
  timestamp: string;
  case_id: string;
  client_id: string;
  consilier: string | null;
  decizie: Decizie;
  override: boolean;
  recomandare_agent: Recomandare;
  interventie_agent: string | null;
  interventie_finala: string | null;
  motiv: string | null;
  rezultat: "ramas" | "plecat" | null;
  rezultat_la: string | null;
  versiune?: string | null;
}

export interface Strategie {
  cost: number;
  retinuti: number;
  rata_ramanere: number;
  cost_per_retinut: number;
}

export interface Metrici {
  cifra_vedeta: {
    candidati: number;
    agent: Strategie;
    uniform: Record<string, Strategie>;
    uniform_aleasa: string | null;
    economie_ron: number;
    economie_pct: number | null;
    concluzie: string;
  };
  nu_interveni: { nu_interveni: number; altele: number; total: number; procent: number };
  interogari_externe: { rulare_tot: number; executate: number; evitate: number; procent: number };
  recomandari: { acuratete: number; corecte: number; total: number };
  cerinte_dure: Record<string, number>;
  distributie: Record<string, number>;
}

export interface Snapshot {
  azi: string;
  clienti: number;
  metrici: Metrici;
  benzi: Banda[];
  p_tinta: number;
  model_churn?: { nume: string; versiune: string } | null;
  /** numărul total de cazuri din coadă (în snapshot pot intra doar primele N) */
  total_cazuri?: number;
  cazuri: Caz[];
}

/** O pagină din coadă (GET /api/coada): filtrată, sortată și paginată pe server. */
export interface PaginaCoada {
  total: number;
  offset: number;
  limit: number;
  pe_banda: Record<string, number>;
  items: Caz[];
}

/** Contoarele paginii de start (GET /api/cazuri/sumar), pe toată coada. */
export interface Sumar {
  total: number;
  deschise: number;
  p1: number;
  scadente_azi: number;
  /** briefing-ul zilei: P1 cu termen azi, oferte amânate peste plafon, cazuri cu ceva de confirmat */
  p1_azi?: number;
  peste_plafon?: number;
  de_confirmat?: number;
  blocate: number;
  decise: number;
  pe_banda: Record<string, number>;
  primele: Caz[];
}

export interface ParametriCoada {
  benzi?: Banda[];
  recomandari?: Recomandare[];
  consilier?: string;
  q?: string;
  sort?: "prioritate" | "termen" | "client";
  ascundeDecise?: boolean;
  /** listele briefing-ului de pe Acasă */
  doar?: "termen_azi" | "peste_plafon" | "de_confirmat";
  limit?: number;
  offset?: number;
}

export interface PropunereLLM {
  id: string;
  case_id: string;
  interventie: string | null;
  titlu: string;
  motiv: string;
  indicii: string[];
  mesaj_client: string;
  atentionari: string[];
  model: string;
}

export interface DecizieInput {
  propunere_id?: string;
  decizie: Decizie;
  interventie?: string;
  motiv?: string;
  consilier?: string;
}

export interface DecizieRecord extends DecizieInput {
  case_id: string;
  la: string;
  sursa: "local" | "api";
}
