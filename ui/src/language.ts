/** Presentation labels only. API identifiers and audit data retain their original values. */
const labels: Record<string, string> = {
  vechime_credit: "Loan history", intarziere_noua: "New payment arrears", venit_in_scadere: "Declining income",
  venit_disparut: "Income no longer observed", card_stres: "Credit card stress", angajator_in_dificultate: "Employer under financial stress",
  restructurare_anterioara: "Previous restructuring", poprire_activa: "Active garnishment", ltv_depasit: "Loan-to-value limit exceeded",
  expunere_valutara: "Foreign currency exposure", codebitor_cu_risc: "Co-borrower risk", ci_expirata: "Expired identity document",
  kyc_vechi: "KYC update required", consimtamant_lipsa: "Missing consent", asigurare_expirata: "Expired insurance", flag_blocant: "Blocking restriction",
  carte_identitate: "Identity card", decizie_pensie: "Pension statement", declaratie_unica: "Annual tax declaration",
  polita_asigurare_imobil: "Property insurance policy", tanar_fara_istoric: "New borrower", independent: "Self-employed",
  antrenat: "Trained model", portofoliu: "Portfolio", echipa: "Team", actiune: "Actionability", valoare: "Client value",
  prioritate_retentie: "Retention priority", prioritate: "Priority", simulat: "Simulated", adeverinta_sold: "Balance certificate",

  ipotecar: "Mortgage", imobiliar: "Property loan", refinantare: "Refinancing", nevoi_personale: "Personal loan",
  card_credit: "Credit card", cont_salariu: "Salary account", cont_curent: "Current account", economii: "Savings",
  depozit: "Term deposit", card_debit: "Debit card", asigurare_viata: "Life insurance", pensie_privata: "Private pension",
  restructurare: "Restructuring", oferta_minima: "Retention offer", oferta_produs: "Offer with a product", nu_interveni: "Keep current terms",
  blocat: "Blocked", respins_escaladat: "Escalated for review", informare: "Information and personalised simulation",
  scutire_comision: "Fee waiver / free valuation", fix_1_an: "Fixed rate for 1 year", fix_3_ani: "Fixed rate for 3 years",
  fix_5_ani: "Fixed rate for 5 years", reducere_marja_0_2: "Margin reduction of 0.2 pp", reducere_marja_0_4: "Margin reduction of 0.4 pp",
  reducere_marja_0_6: "Margin reduction of 0.6 pp", pachet_salariu: "Salary package with a margin reduction", ajustare_maturitate: "Term extension",
  pauza_rata: "Payment holiday (interest capitalised)", salariat: "Employee", pensionar: "Pensioner", antreprenor: "Business owner",
  firma: "Business income", mixt: "Mixed income", standard: "Standard", gold: "Gold", platinum: "Platinum",
  identitate_kyc: "Identity and KYC", expuneri_interne: "Internal credit exposure", venit_observat: "Observed income",
  sold_cont: "Account balance", ltv: "Loan-to-value", asigurare_garantie: "Collateral insurance", utilizare_limita_card: "Card utilisation",
  scenarii_rata: "Payment scenarios", cost_mutare: "Switching costs", venit_anaf: "Tax-reported income",
  capacitate_plata_actuala: "Current repayment capacity", istoric_biroul_credit: "Credit bureau history", expuneri_crc: "Credit register exposure",
  extras_cf: "Land registry extract", reevaluare_garantie: "Collateral revaluation", fond_urgenta: "Emergency fund",
  eligibilitate_produs_nou: "New product eligibility", comision_rambursare_anticipata: "Early repayment fee",
  gap_piata_bani: "Cost gap against the market", eligibilitate_externa: "External refinancing eligibility", sold_ramas: "Outstanding balance",
  expirare_dobanda_fixa: "Fixed-rate period expiry", salariu_mutat: "Salary moved away", cerere_adeverinta_sold: "Balance certificate request",
  simulare_in_app: "In-app simulation", rata_alt_creditor: "Payment to another lender", risc_credit: "Credit risk", plecare: "Departure risk",
  blocaj_proces: "Process restriction", procesare_cerere: "Process customer request", intern: "Internal records", anaf: "Tax authority",
  biroul_credit: "Credit bureau", crc: "Credit register", garantie: "Collateral", eligibilitate: "Eligibility", fixa: "Fixed", variabila: "Variable",
  aproba: "Approved", modifica: "Changed", respinge: "Rejected", ramas: "Stayed", plecat: "Left", client_request: "Customer request",
  ci: "Identity document", adeverinta_venit: "Income certificate", acord_anaf: "Tax authority consent", acord_bc: "Credit bureau consent",
};
export const englishLabel = (id: string | null | undefined): string => {
  if (!id) return "–";
  return labels[id] ?? id.replace(/_/g, " ");
};
export const englishError = (message: string): string => {
  if (/[ăâîșțĂÂÎȘȚ]/.test(message) || /sesiunea|cazul|decizie refuz|consilier|parola|nu exist/i.test(message))
    return "The request could not be completed. Check access, input values and server configuration, then try again.";
  return message;
};
