import type { PartnerBenefit } from "./types/api";

/** Cached/offline quotes must expire too; server revalidates again before recording. */
export function currentPartnerOffers(offers: PartnerBenefit[], today: string): PartnerBenefit[] {
  return offers.filter(o => o.kind === "product_recommendation" && o.maximum_cost_ron === 0 && o.bank_subsidy_ron === 0)
    .map(o => ({ ...o, products: o.products.filter(p => p.merchant_price_verified && p.checked_on <= today && today <= p.valid_until) }))
    .filter(o => o.products.length > 0);
}
