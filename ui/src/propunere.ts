import { eticheta, pp, ron } from "./format";
import type { RecInfo } from "./types/api";

const TIP: Record<string, string> = {
  fix_piata: "dobândă fixă la nivelul pieței",
  reducere_marja: "reducere de marjă",
  pachet: "pachet cu salariul la noi",
  restructurare: "restructurare",
  informare: "informare cu simulare",
  comision: "scutire de comision",
};

/** O propoziție pentru consilier despre ce propune agentul, din câmpurile structurate ale ofertei.
 *  `rec.motiv` (formularea tehnică, cu p și p×V) rămâne în „Cum a ajuns agentul aici”. */
export function propunere(rec: RecInfo): string {
  const o = rec.oferta;
  if (!o) return rec.motiv;
  const parti = [`${TIP[o.tip] ?? eticheta(o.tip)}: ${pp(o.dobanda_noua)} pe ${o.perioada}`];
  if (o.rata_noua < o.rata_veche) parti.push(`rata scade de la ${ron(o.rata_veche)} la ${ron(o.rata_noua)}`);
  else if (o.rata_noua > o.rata_veche) parti.push(`rata crește de la ${ron(o.rata_veche)} la ${ron(o.rata_noua)}`);
  if (o.economie_client > 0) parti.push(`clientul economisește ${ron(o.economie_client)}`);
  parti.push(`costă banca ${ron(o.cost_banca)}`);
  let text = parti.join(", ") + ".";
  if (o.conditie) text += ` Condiție: ${o.conditie}.`;
  return text.charAt(0).toUpperCase() + text.slice(1);
}
