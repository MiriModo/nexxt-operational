"""Category-based priced product suggestions with zero bank promotional subsidy."""
from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field
from .cheltuieli import luni_recente, transaction_category


class PricedProduct(BaseModel):
    id: str
    name: str
    category: str
    partner: str
    price_ron: float = Field(gt=0, allow_inf_nan=False)
    source_url: str
    checked_on: date
    valid_until: date
    merchant_price_verified: bool = False


class LoyaltyPolicy(BaseModel):
    lookback_months: int = Field(3, ge=1, le=12)
    minimum_transactions: int = Field(5, ge=1)
    minimum_active_months: int = Field(2, ge=1)
    minimum_spend_ron: float = Field(200, ge=0)
    maximum_offers: int = Field(2, ge=1, le=5)
    bank_subsidy_budget_ron: Literal[0] = 0
    max_price_age_days: int = Field(1, ge=0, le=7)
    partners: dict[str, list[str]]
    partner_domains: dict[str, str] = Field(default_factory=dict)
    products: list[PricedProduct] = Field(default_factory=list)


def current_products(p: LoyaltyPolicy, category: str, as_of: date) -> list[dict]:
    matches = []
    for product in p.products:
        url = urlparse(product.source_url)
        host = (url.hostname or '').removeprefix('www.')
        if (product.category == category and product.partner in p.partners.get(category, [])
                and product.merchant_price_verified and url.scheme == 'https'
                and host == p.partner_domains.get(product.partner)
                and product.checked_on <= as_of <= product.valid_until
                and (as_of - product.checked_on).days <= p.max_price_age_days):
            matches.append(product.model_dump(mode='json'))
    return sorted(matches, key=lambda product: (product['price_ron'], product['id']))[:3]


@lru_cache(maxsize=4)
def _policy(path: str, mtime: int) -> LoyaltyPolicy:
    return LoyaltyPolicy.model_validate(json.loads(Path(path).read_text()))


def load_policy() -> LoyaltyPolicy:
    path = Path(__file__).resolve().parents[1] / 'config' / 'loyalty.json'
    return _policy(str(path), path.stat().st_mtime_ns)


def money(value) -> float:
    return float(Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def recommend_benefits(transactions: list[dict], today: date, case: dict, check: dict,
                       rec: dict, policy: LoyaltyPolicy | None = None, pricing_date: date | None = None) -> dict:
    p = policy or load_policy()
    pricing_date = pricing_date or date.today()
    missing_prices = []
    result = {'offers': [], 'lookback_months': p.lookback_months, 'status': 'no_match',
              'reason': 'No recurring spending category meets the partner benefit criteria.'}
    if (case.get('blocaje') or check.get('verificare_picata') or rec.get('incertitudini')
            or rec.get('documente_lipsa') or case.get('scoruri', {}).get('risc_credit', 0) > 0
            or rec.get('recomandare') in ('blocat', 'respins_escaladat', 'restructurare')):
        return {**result, 'status': 'ineligible',
                'reason': 'Resolve credit risk, missing documents or case restrictions before proposing a benefit.'}
    months = luni_recente(today, p.lookback_months)
    groups = defaultdict(list)
    for t in transactions:
        category = transaction_category(t)
        if (t.get('directie') == 'out' and category in p.partners
                and t.get('data', '')[:7] in months and t['data'][:10] <= today.isoformat()
                and isinstance(t.get('suma'), (int, float)) and math.isfinite(t['suma']) and t['suma'] > 0
                and t.get('moneda', 'RON') == 'RON'):
            groups[category].append(t)
    for category, txs in groups.items():
        total = sum(Decimal(str(t['suma'])) for t in txs)
        active = len({t['data'][:7] for t in txs})
        if len(txs) < p.minimum_transactions or active < p.minimum_active_months or total < Decimal(str(p.minimum_spend_ron)):
            continue
        products = current_products(p, category, pricing_date)
        if not products:
            missing_prices.append(category)
            continue
        result['offers'].append({
            'id': f'products_{category}', 'category': category,
            'partners': sorted({product['partner'] for product in products}), 'products': products,
            'transaction_count': len(txs), 'active_months': active, 'spend_ron': money(total),
            'maximum_cost_ron': 0.0, 'bank_subsidy_ron': 0.0,
            'funding': 'customer_purchase', 'kind': 'product_recommendation', 'status': 'draft',
            'terms': 'Optional product suggestions at observed merchant prices, not a bank-funded reward. The customer pays the merchant; no cashback, bank subsidy or financing is promised. Prices and stock must be checked with the merchant before purchase. Delivery and optional services may cost extra.',
        })
    result['offers'].sort(key=lambda o: (-o['transaction_count'], -o['spend_ron'], o['category']))
    result['offers'] = result['offers'][:p.maximum_offers]
    if result['offers']:
        result.update(status='matched', reason='Recurring spending matches categories in the configured partner catalogue.')
    result['categories_needing_price_check'] = missing_prices
    if not result['offers'] and missing_prices:
        result.update(status='price_check_required', reason='Recurring spending was found, but no current merchant-verified product prices are available for that category.')
    return result
