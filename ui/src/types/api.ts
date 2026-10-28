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
export type StatusVerificare = "ok" | "avertizare" | "fail" | "neexecutat";
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
}

export interface Caz {
  case: CaseInfo;
  client: ClientInfo;
  loan: LoanInfo | null; // null pentru cereri de credit nou (fără credit existent)
  check: CheckInfo;
  offer: OfferInfo;
  rec: RecInfo;
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
  blocate: number;
  decise: number;
  pe_banda: Record<string, number>;
  primele: Caz[];
}

export interface ParametriCoada {
  benzi?: Banda[];
  q?: string;
  sort?: "prioritate" | "termen" | "client";
  ascundeDecise?: boolean;
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
}

export interface DecizieRecord extends DecizieInput {
  case_id: string;
  la: string;
  sursa: "local" | "api";
}
