import test from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';

const result = await build({ stdin: { contents: 'export * from "./src/presentation.ts"; export * from "./src/proposal.ts"; export * from "./src/partnerProducts.ts";', resolveDir: process.cwd() }, bundle: true, write: false, format: 'esm', platform: 'node' });
const { englishCase, englishData, proposal, offerPeriod, bankProductExamples, currentPartnerOffers } = await import(`data:text/javascript;base64,${Buffer.from(result.outputFiles[0].text).toString('base64')}`);

function sourceCase() {
  return {
    case: { semnale: [{ id: 'gap_piata_bani', scor: 0.8, dovada: 'Diferență față de piață' }], motive_top3: ['Cerere restructurare'], request_id: 'R1', blocaje: [] },
    client: { nume: 'Alina Cristea' }, loan: null,
    check: { concluzii: { venit_lunar: 6000, venit_lunar_anaf: 5900, dti_curent: 0.3 },
      plan: [{ id: 'venit_anaf', motiv: 'cerută de motiv' }], omise: [{ id: 'extras_cf', motiv: 'sărită' }], motive: [],
      rezultate: [{ id: 'venit_anaf', status: 'ok', dovada: 'Venit din salariu', sursa: 'anaf' }] },
    offer: { p: 0.4, p_tinta: 0.2, interventii: [{ id: 'fix_1_an', fezabil: true, eticheta: 'dobândă fixă', cost: 700 }], motiv_alegere: 'cea mai ieftină', explicatie: 'explicație' },
    rec: { recomandare: 'oferta_minima', interventie: 'fix_1_an', motiv: 'ofertă', eticheta: 'ofertă minimă', explicatie: 'recomandare',
      oferta: { rata_noua: 1200, cost_banca: 700, conditie: 'condiție necesară', conditii_de_confirmat: ['venit'] },
      documente_lipsa: [{ tip: 'ci', motiv: 'necesar' }], incertitudini: [{ id: 'venit_anaf', text: 'Date lipsă' }] },
    loyalty: { offers: [{ id: 'cashback_shopping', partners: ['Fashion Days'], cashback_rate: 0.02 }] },
  };
}

test('English case presentation preserves money, identifiers and partner eligibility', () => {
  const source = sourceCase();
  const translated = englishCase(source);
  assert.equal(translated.rec.oferta.rata_noua, 1200);
  assert.equal(translated.offer.interventii[0].cost, 700);
  assert.equal(translated.rec.interventie, 'fix_1_an');
  assert.equal(translated.rec.recomandare, 'oferta_minima');
  assert.deepEqual(translated.loyalty, source.loyalty);
  assert.match(translated.check.rezultate[0].dovada, /5,900 RON/);
  assert.match(translated.offer.interventii[0].eticheta, /Fixed rate/);
  assert.equal(/[ăâîșț]/i.test(JSON.stringify(translated)), false);
  assert.equal(source.rec.motiv, 'ofertă');
});

test('API pages and offline nested snapshots get the same English presentation', () => {
  const c = sourceCase();
  const page = englishData({ items: [c], primele: [c], total: 1 });
  assert.equal(page.items[0].rec.motiv, page.primele[0].rec.motiv);
  assert.match(page.items[0].rec.motiv, /Advisor confirmation/);
});


test('Recommendation never echoes Romanian reasons or additional conditions', () => {
  const c = sourceCase();
  assert.match(proposal({ ...c.rec, oferta: null, recomandare: 'respins_escaladat' }), /further review/);
  c.rec.oferta = { ...c.rec.oferta, tip: 'fix_piata', dobanda_noua: 4.7,
    rata_veche: 1500, perioada: '3 ani apoi dobândă variabilă', economie_client: 2000 };
  const text = proposal(c.rec);
  assert.match(text, /3 years/);
  assert.equal(/[ăâîșț]/i.test(text), false);
  assert.equal(text.includes('condiție'), false);
  assert.match(bankProductExamples(c.rec)[0], /3 years/);
  assert.equal(offerPeriod('toată durata'), 'the remaining loan term');
  assert.equal(offerPeriod('până la final'), 'the period specified in the calculated offer');
});


test('Expired quotes and bank-funded cached rewards never appear as zero-cost products', () => {
  const offer = { kind: 'product_recommendation', maximum_cost_ron: 0, bank_subsidy_ron: 0,
    products: [{ merchant_price_verified: true, checked_on: '2026-10-29', valid_until: '2026-10-30' }] };
  assert.equal(currentPartnerOffers([offer], '2026-10-29').length, 1);
  assert.equal(currentPartnerOffers([offer], '2026-11-01').length, 0);
  assert.equal(currentPartnerOffers([{ ...offer, maximum_cost_ron: 90 }], '2026-10-29').length, 0);
  assert.equal(currentPartnerOffers([{ ...offer, kind: undefined }], '2026-10-29').length, 0);
});
