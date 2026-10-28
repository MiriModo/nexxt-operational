from datetime import date
from copy import deepcopy

import pytest

from retailagent.loyalty import recommend_benefits, load_policy, current_products

TODAY = date(2026, 10, 28)

def tx(category='appliances_it'):
    return [{'directie': 'out', 'categorie': category, 'data': d, 'suma': 1000}
            for d in ['2026-08-01', '2026-08-12', '2026-09-03', '2026-09-18', '2026-10-08']]

def recommend(transactions, case=None, check=None, rec=None):
    return recommend_benefits(transactions, TODAY, case or {'scoruri': {'risc_credit': 0}},
                              check or {}, rec or {'recomandare': 'nu_interveni'}, pricing_date=date(2026, 10, 29))

def test_recurrence_partner_mapping_and_cap():
    r = recommend(tx())
    o = r['offers'][0]
    assert o['category'] == 'appliances_it' and o['transaction_count'] == 5
    assert o['active_months'] == 3 and o['spend_ron'] == 5000
    assert o['partners'] == ['Altex']
    assert 'Dedeman' not in o['partners']
    assert o['bank_subsidy_ron'] == 0 and o['kind'] == 'product_recommendation'
    assert o['products'][0]['price_ron'] == 199.99
    assert 'cashback_rate' not in o
    assert o['maximum_cost_ron'] == 0 and o['status'] == 'draft'

@pytest.mark.parametrize('category', ['restaurants', 'transport', 'cash', 'legal', 'loan_payments', 'internal_transfers', 'income_salary', 'other'])
def test_no_forced_partner_or_transfer_rewards(category):
    assert recommend(tx(category))['offers'] == []

@pytest.mark.parametrize('change', ['in', 'old', 'future', 'negative', 'single_month', 'few', 'foreign'])
def test_invalid_or_nonrecurring_transactions(change):
    rows = tx()
    if change == 'in':
        for t in rows: t['directie'] = 'in'
    if change == 'old':
        for t in rows: t['data'] = '2025-01-01'
    if change == 'future':
        for t in rows: t['data'] = '2026-10-30'
    if change == 'negative':
        for t in rows: t['suma'] = -100
    if change == 'single_month':
        for t in rows: t['data'] = '2026-10-01'
    if change == 'few': rows = rows[:3]
    if change == 'foreign':
        for t in rows: t['moneda'] = 'EUR'
    assert recommend(rows)['offers'] == []

@pytest.mark.parametrize('status', ['blocat', 'respins_escaladat', 'restructurare'])
def test_restricted_cases(status):
    assert recommend(tx(), rec={'recomandare': status})['status'] == 'ineligible'


def test_missing_documents_and_risk():
    assert recommend(tx(), rec={'documente_lipsa': [{'tip': 'ci'}]})['offers'] == []
    assert recommend(tx(), case={'scoruri': {'risc_credit': 0.3}})['offers'] == []


def test_all_21_user_partners_present_and_deterministic():
    p = load_policy()
    assert len(set(x for names in p.partners.values() for x in names)) == 21
    rows = tx('shopping') + tx('home_diy') + tx('groceries')
    original = deepcopy(rows)
    assert recommend(rows) == recommend(list(reversed(rows)))
    assert len(recommend(rows)['offers']) == 2 and rows == original


def test_products_are_category_specific_and_catalogued():
    offer = recommend(tx())['offers'][0]
    assert all(p['category'] == 'appliances_it' and p['partner'] in offer['partners'] for p in offer['products'])


def test_unverified_stale_future_and_wrong_domain_prices_are_excluded():
    p = load_policy().model_copy(deep=True)
    assert current_products(p, 'appliances_it', date(2026, 10, 29))
    assert not current_products(p, 'appliances_it', date(2026, 11, 1))
    assert not current_products(p, 'appliances_it', date(2026, 10, 28))
    p.products[0].source_url = 'https://evil.example/product'
    assert not current_products(p, 'appliances_it', date(2026, 10, 29))
    p = load_policy().model_copy(deep=True)
    p.products[0].merchant_price_verified = False
    assert not current_products(p, 'appliances_it', date(2026, 10, 29))


def test_bank_subsidy_cannot_be_enabled():
    from pydantic import ValidationError
    from retailagent.loyalty import LoyaltyPolicy
    values = load_policy().model_dump()
    values['bank_subsidy_budget_ron'] = 1
    with pytest.raises(ValidationError):
        LoyaltyPolicy.model_validate(values)


def test_groceries_without_verified_prices_are_not_fabricated():
    result = recommend(tx('groceries'))
    assert result['offers'] == [] and result['status'] == 'price_check_required'
    assert result['categories_needing_price_check'] == ['groceries']


def test_legacy_categories_are_derived_without_source_changes():
    rows = tx()
    for t in rows:
        del t['categorie']
        t.update(platitor_beneficiar='ALTEX', tip_etichetat='altele')
    before = deepcopy(rows)
    offer = recommend(rows)['offers'][0]
    assert offer['category'] == 'appliances_it'
    assert rows == before
