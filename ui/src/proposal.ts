import { label, monthYear, pp, ron } from "./format";
import type { RecInfo } from "./types/api";

const TYPE: Record<string, string> = {
  fix_piata: "Fixed rate at market level",
  reducere_marja: "Margin cut",
  pachet: "Salary package (salary moved to us)",
  restructurare: "Restructuring",
  informare: "Information with a simulation",
  comision: "Fee waiver",
};

/** One sentence for the advisor about what the agent proposes, built from the structured offer.
 *  `rec.motiv` (the technical wording, with p and p×V) stays under "How the agent got here". */
export function proposal(rec: RecInfo): string {
  const o = rec.oferta;
  if (!o) return rec.motiv;
  const parts = [`${TYPE[o.tip] ?? label(o.tip)}: ${pp(o.dobanda_noua)} for ${o.perioada.replace(/ ani$/, " years").replace(/ an$/, " year")}`];
  if (o.rata_noua < o.rata_veche) parts.push(`the monthly payment drops from ${ron(o.rata_veche)} today to ${ron(o.rata_noua)}`);
  else if (o.rata_noua > o.rata_veche) parts.push(`the monthly payment rises from ${ron(o.rata_veche)} today to ${ron(o.rata_noua)}`);
  if (o.rata_dupa_fixa && o.fixa_expira && o.rata_dupa_fixa > o.rata_noua)
    parts.push(`instead of ${ron(o.rata_dupa_fixa)} once the current fixed rate ends in ${monthYear(o.fixa_expira)}`);
  if (o.economie_client > 0) parts.push(`the client saves ${ron(o.economie_client)} in interest${o.economie_orizont_luni ? ` over ${yearsText(o.economie_orizont_luni)}` : ""}`);
  parts.push(`it costs the bank ${ron(o.cost_banca)}`);
  let text = parts.join(", ") + ".";
  if (o.conditie) text += ` Condition: ${o.conditie}.`;
  return text;
}

const yearsText = (months: number) => (months % 12 === 0 ? `${months / 12} ${months === 12 ? "year" : "years"}` : `${months} months`);
