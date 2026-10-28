import type { Caz, VerificareRezultat } from "./types/api";
import { englishLabel } from "./language";
import { pct, ron } from "./format";

const outcome: Record<string, string> = { ok: "Passed", fail: "Failed", avertizare: "Requires review", indisponibil: "Source unavailable", neexecutat: "Not executed" };
export function englishCheck(r: VerificareRezultat): VerificareRezultat {
  return { ...r, dovada: `${englishLabel(r.id)}: ${outcome[r.status] ?? r.status}. Source: ${englishLabel(r.sursa)}.`,
    incertitudine: r.incertitudine ? "The source result requires confirmation before communicating an offer." : r.incertitudine };
}
export function englishCase(c: Caz): Caz {
  const cl = c.check.concluzii;
  const reason = c.rec.recomandare === "blocat" ? "Resolve the case restrictions before making an offer."
    : c.rec.recomandare === "respins_escaladat" ? "No eligible commercial recommendation is available; refer the request for further review."
    : c.rec.recomandare === "nu_interveni" ? "The calculated recommendation is to keep the current loan terms."
    : `Calculated recommendation: ${englishLabel(c.rec.interventie)}. Advisor confirmation is required.`;
  const signals = c.case.semnale.map(s => ({ ...s, dovada: `${englishLabel(s.id)} detected; signal score ${s.scor.toFixed(2)}.` }));
  const facts = [reason, ...signals.slice(0, 2).map(s => s.dovada)];
  if (c.case.request_id) facts[0] = `Customer request ${c.case.request_id}. ${reason}`;
  return { ...c,
    case: { ...c.case, semnale: signals, motive_top3: facts },
    check: { ...c.check,
      plan: c.check.plan.map(p => ({ ...p, motiv: `${englishLabel(p.id)} required for the case assessment.` })),
      omise: c.check.omise.map(p => ({ ...p, motiv: "Not required for the current case assessment." })),
      motive: c.check.motive.map(m => ({ motiv: englishLabel(m.motiv), sursa: "Calculated case assessment" })),
      rezultate: c.check.rezultate.map(r => {
        const x = englishCheck(r);
        if (r.id === "venit_observat") x.dovada += ` Observed monthly income: ${ron(cl.venit_lunar)}.`;
        if (r.id === "venit_anaf") x.dovada += ` Reported monthly income: ${ron(cl.venit_lunar_anaf)}.`;
        if (r.id === "capacitate_plata_actuala") x.dovada += ` Debt-to-income: ${pct(cl.dti_curent)}.`;
        return x;
      }),
    },
    offer: { ...c.offer,
      interventii: c.offer.interventii.map(i => ({ ...i, eticheta: englishLabel(i.id), motiv_infezabil: i.fezabil ? null : "Does not satisfy the configured eligibility rules or retention limits." })),
      motiv_alegere: `Calculated departure probability ${pct(c.offer.p)}; target ${pct(c.offer.p_tinta)}. Recommended intervention: ${englishLabel(c.rec.interventie)}.`,
      explicatie: reason,
    },
    rec: { ...c.rec, eticheta: englishLabel(c.rec.recomandare), motiv: reason,
      explicatie: `${reason} Income: ${ron(cl.venit_lunar)}/month. Debt-to-income: ${pct(cl.dti_curent)}. Departure probability: ${pct(c.offer.p)}.`,
      documente_lipsa: c.rec.documente_lipsa.map(d => ({ ...d, motiv: "Required to complete the case assessment." })),
      incertitudini: c.rec.incertitudini?.map(i => ({ ...i, text: `Confirmation required: ${englishLabel(i.id)}.` })),
      oferta: c.rec.oferta ? { ...c.rec.oferta,
        conditie: c.rec.oferta.conditie ? "The calculated offer has additional conditions. Verify the underlying product terms before communicating or activating it." : undefined,
        conditii_de_confirmat: c.rec.oferta.conditii_de_confirmat?.map(() => "Confirm the outstanding eligibility condition before proceeding."),
      } : null,
    },
  };
}
/** Apply English presentation to API and static case payloads without changing API enum values. */
export function englishData<T>(value: T): T {
  if (Array.isArray(value)) return value.map(v => englishData(v)) as T;
  if (value && typeof value === "object") {
    const obj = value as Record<string, unknown>;
    if (obj.case && obj.client && obj.offer && obj.rec) return englishCase(value as unknown as Caz) as unknown as T;
    return Object.fromEntries(Object.entries(obj).map(([k, v]) => [k, v && typeof v === "object" ? englishData(v) : v])) as T;
  }
  return value;
}
