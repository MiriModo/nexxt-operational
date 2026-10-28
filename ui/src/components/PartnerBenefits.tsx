import { currentPartnerOffers } from "../partnerProducts";
import { categoryName } from "./Categories";
import { ron } from "../format";
import type { Loyalty } from "../types/api";

export function PartnerBenefits({ loyalty, selected, onSelect, disabled }: {
  loyalty?: Loyalty; selected?: string; onSelect?: (id: string) => void; disabled?: boolean;
}) {
  if (!loyalty) return null;
  // Reject legacy cached bank-funded cashback cards.
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Bucharest", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
  const offers = currentPartnerOffers(loyalty.offers, today);
  if (!offers.length && loyalty.status !== "price_check_required") return null;
  return <section style={{ marginTop: 24 }} aria-label="Personalised partner products">
    <div className="sec-label"><span>Products to consider</span><span>No bank-funded reward</span></div>
    {offers.map(offer => <div key={offer.id} className="win" style={{ marginTop: 12 }}>
      <h3 style={{ marginTop: 0 }}>{categoryName(offer.category)}</h3>
      <p className="meta">Matched to {offer.transaction_count} payments across {offer.active_months} months, not proof that the customer needs a specific product.</p>
      {offer.products.map(product => <div key={product.id} style={{ margin: "16px 0" }}>
        <b>{product.name}</b>
        <p style={{ margin: "4px 0" }}>{product.partner} · <b>{ron(product.price_ron, 2)}</b></p>
        <p className="meta">Published price checked on {product.checked_on}. Recheck before purchase; delivery and stock may vary.</p>
        <a href={product.source_url} target="_blank" rel="noopener noreferrer">Check merchant price ↗</a>
      </div>)}
      <p><b>Bank promotional subsidy: {ron(offer.bank_subsidy_ron)}</b> · Customer pays the merchant.</p>
      <details className="meta"><summary>Purchase conditions</summary><p>{offer.terms}</p>
        <p>No cashback, free product, instalment plan or special bank discount is promised. Operational costs and any separate loan-retention intervention are not included in this figure.</p>
      </details>
      {onSelect && <label className={`opt ${selected === offer.id ? "on" : ""}`}>
        <input type="checkbox" checked={selected === offer.id} disabled={disabled} onChange={() => onSelect(selected === offer.id ? "" : offer.id)} />
        <span>Attach these optional product suggestions to the decision</span>
      </label>}
    </div>)}
    {!!loyalty.categories_needing_price_check?.length && <p className="notice warn">
      {loyalty.categories_needing_price_check.map(categoryName).join(", ")}: a current merchant price must be verified before suggesting a specific product.
    </p>}
  </section>;
}
