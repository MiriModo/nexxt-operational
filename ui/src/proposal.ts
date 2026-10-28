import { pp, ron } from "./format";
import type { RecInfo } from "./types/api";

const TYPE: Record<string, string> = {
  fix_piata: "Fixed rate at market level", reducere_marja: "Margin reduction",
  pachet: "Salary package", restructurare: "Loan restructuring",
  informare: "Information with a personalised simulation", comision: "Fee waiver",
};
const NO_OFFER: Record<string, string> = {
  blocat: "Resolve the restrictions on this case before making an offer.",
  respins_escaladat: "The request needs further review. No commercial offer is currently available.",
  nu_interveni: "Keep the current loan terms. No loan-pricing intervention is recommended at this time.",
  restructurare: "Discuss the calculated restructuring options with the advisor before communicating an offer.",
};

/** Never echo free-form backend durations, reasons or conditions into the English recommendation. */
export function offerPeriod(period: string): string {
  const years = period.trim().match(/^(\d+)\s+(?:ani?|years?)(?:\s|$)/i);
  if (years) return `${Number(years[1])} ${Number(years[1]) === 1 ? "year" : "years"}`;
  const months = period.trim().match(/^(\d+)\s+(?:luni|months?)(?:\s|$)/i);
  if (months) return `${Number(months[1])} ${Number(months[1]) === 1 ? "month" : "months"}`;
  if (/toat|remaining|entire|full/i.test(period)) return "the remaining loan term";
  return "the period specified in the calculated offer";
}

export function proposal(rec: RecInfo): string {
  const o = rec.oferta;
  if (!o) return NO_OFFER[rec.recomandare] ?? "Review the calculated recommendation with the advisor before making an offer.";
  const parts = [TYPE[o.tip] ?? "Calculated loan offer"];
  if (Number.isFinite(o.dobanda_noua) && o.dobanda_noua > 0)
    parts.push(`${pp(o.dobanda_noua)} for ${offerPeriod(o.perioada)}`);
  if (o.rata_noua < o.rata_veche) parts.push(`the monthly payment drops from ${ron(o.rata_veche)} to ${ron(o.rata_noua)}`);
  else if (o.rata_noua > o.rata_veche) parts.push(`the monthly payment rises from ${ron(o.rata_veche)} to ${ron(o.rata_noua)}`);
  if (o.economie_client > 0) parts.push(`estimated savings over the offer's calculation horizon are ${ron(o.economie_client)}`);
  if (Number.isFinite(o.cost_banca)) parts.push(`the cost to the bank is ${ron(o.cost_banca)}`);
  let text = parts.join(", ") + ".";
  if (o.conditie) text += o.tip === "pachet"
    ? " The salary-package conditions must be confirmed before activation."
    : " Additional product conditions require advisor confirmation before activation.";
  return text;
}

export function bankProductExamples(rec: RecInfo): string[] {
  if (!rec.oferta) return [];
  if (rec.oferta.tip === "pachet") return ["Salary account with salary credited to the bank, subject to the calculated package conditions."];
  if (rec.oferta.tip === "fix_piata") return [`A fixed-rate period of ${offerPeriod(rec.oferta.perioada)} on the existing loan.`];
  if (rec.oferta.tip === "comision") return ["A fee waiver or valuation-cost benefit, where included in the calculated offer."];
  return [];
}
