"""Pagina de demo: out/demo.html — statică, autonomă (JSON-urile încorporate, fără rețea, fără dependențe).

    python -m retailagent.demo        # după pipeline; rulează singur fluxul dacă e nevoie

Conținut: metricile-vedetă → coada cu filtre pe bandă → panoul cazului (semnale cu dovezi, verificări planificate /
omise / rezultate, meniul de intervenții, recomandarea cu ofertă, grafic și documente) → butoane Aprobă / Modifică /
Respinge care afișează comanda `approve` echivalentă (pagina nu scrie nimic pe disc).
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from .common import CONFIG_DIR, DATA_DIR, OUT_DIR, log_event, read_json, setup_console
from .evaluate_final import raport_model_final
from .pipeline import FullRun, run_full


def _contributii(full: FullRun, offer: dict) -> list[list] | None:
    """Top 6 contribuții ale feature-urilor la p (doar pentru modelul antrenat)."""
    mc = offer.get("model_churn")
    if not mc or mc["nume"] != "antrenat" or not offer.get("features"):
        return None
    from .churn.model import get_model
    return [[f, round(v, 3)] for f, v in get_model(full.cfg).explain(offer["features"])[:6]]


def _case_payload(full: FullRun, case: dict) -> dict:
    a = full.by_case(case["case_id"])
    ci, check, offer, rec = a["input"], a["check"], a["offer"], a["rec"]
    cl = ci.client
    return {
        "case": {k: case[k] for k in ("case_id", "client_id", "loan_id", "produs", "sursa", "request_id", "semnale", "scoruri",
                                      "banda", "deadline", "motive_top3", "actiune_propusa", "blocaje")},
        "consilier": rec.get("consilier"), "versiune": rec.get("versiune"),
        "client": {"nume": cl["nume"], "nivel": cl["nivel_relatie"], "tipologie": cl["tipologie_declarata"],
                   "client_din": cl["client_din"], "produse": cl.get("produse_atasate", [])},
        "loan": ({"sold": ci.loan["sold_ramas"], "tip_dobanda": ci.loan["tip_dobanda"], "dobanda": ci.loan["dobanda_curenta"],
                  "expira": ci.loan.get("dobanda_fixa_expira_la"), "scadenta": ci.loan["data_scadenta"], "rata": ci.loan["rata_lunara"],
                  "moneda": ci.loan.get("moneda", "RON"), "sold_valuta": ci.loan.get("sold_valuta")}
                 if ci.loan else None),
        "check": {"motive": check["motive"], "plan": check["plan"], "omise": check["omise"],
                  "rezultate": [{k: x.get(k) for k in ("id", "treapta", "externa", "status", "dovada", "sursa")} for x in check["rezultate"]],
                  "oprit_la": check["oprit_la"], "verificare_picata": check["verificare_picata"],
                  "interogari": check["interogari_externe"], "concluzii": {k: check["concluzii"].get(k) for k in
                                                                            ("venit_lunar", "venit_lunar_anaf", "dti_curent", "ltv_actual", "salariu_la_alta_banca", "interogari_bc")}},
        "offer": {"B": offer["B"], "B_detalii": offer["B_detalii"], "p": offer["p"], "p_tinta": offer["p_tinta"], "V": offer["V"],
                  "legaturi": offer["legaturi"], "semnale_active": offer["semnale_active"], "aleasa": offer["interventie_aleasa"],
                  "motiv_alegere": offer["motiv_alegere"], "explicatie": offer["explicatie"],
                  "model": offer.get("model_churn"), "contributii": _contributii(full, offer),
                  "interventii": [{k: i[k] for k in ("id", "eticheta", "fezabil", "motiv_infezabil", "cost", "B_dupa", "p_dupa", "respecta_tinta", "merita")}
                                  for i in offer["interventii"]]},
        "rec": {**{k: rec[k] for k in ("recomandare", "eticheta", "interventie", "motiv", "oferta", "grafic", "documente_lipsa", "explicatie")},
                "incertitudini": rec.get("incertitudini", []), "buget": rec.get("buget")},
    }


def build_data(full: FullRun, gt: list[dict], max_cazuri: int | None = None) -> dict:
    """Snapshot-ul comun pentru demo.html, ui/public/data/demo.json și API: metrici pe tot portofoliul + cazuri.

    Contractul (chei, tipuri) e cel din ui/src/types/api.ts; în pagină intră primele `max_cazuri` din coadă.
    """
    metrici = raport_model_final(full, gt)
    cazuri = full.res.cases if max_cazuri is None else full.res.cases[:max_cazuri]
    mc = full.offers[0].get("model_churn") if full.offers else None
    return {"azi": full.pf.today.isoformat(), "clienti": len(full.pf.clients),
            "metrici": {"cifra_vedeta": metrici["cifra_vedeta"], "nu_interveni": metrici["nu_interveni"],
                        "interogari_externe": metrici["interogari_externe"], "recomandari": {k: metrici["recomandari"][k] for k in ("acuratete", "corecte", "total")},
                        "cerinte_dure": {k: v["incalcari"] for k, v in metrici["cerinte_dure"].items()},
                        "distributie": metrici["distributie_recomandari"]},
            "benzi": list(full.cfg.priority.benzi), "p_tinta": full.cfg.retention.p_tinta, "model_churn": mc,
            "total_cazuri": len(full.res.cases),
            "cazuri": [_case_payload(full, c) for c in cazuri]}


def build_html(full: FullRun, gt: list[dict], max_cazuri: int | None = None, data: dict | None = None) -> str:
    data = data or build_data(full, gt, max_cazuri)
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</script", "<\\/script")
    return TEMPLATE.replace("__DATA__", payload)


UI_DIR = Path("ui")
# copiile vechi ale out/*.json (~120 MB la 10.000 de clienți) nu mai sunt citite de interfață: doar demo.json
UI_COPII_VECHI = ("queue.json", "checks.json", "offers.json", "recommendations.json", "evaluation.json")


def sync_ui(data: dict, out_dir: Path, ui_dir: Path = UI_DIR) -> Path | None:
    """Scrie snapshot-ul în ui/public/data/demo.json (sursa statică a interfeței React, când API-ul nu rulează)."""
    if not (ui_dir / "package.json").exists():
        return None
    dest = ui_dir / "public" / "data"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "demo.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    for name in UI_COPII_VECHI:
        (dest / name).unlink(missing_ok=True)
    return dest


TEMPLATE = r"""<!doctype html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>retailagent — coada consilierului</title>
<style>
:root{--bg:#f6f7f9;--card:#fff;--ink:#1c2430;--muted:#66707d;--line:#e3e7ec;--acc:#0b6e4f;--acc2:#d9a400;--bad:#b3261e;--p1:#b3261e;--p2:#d9a400;--p3:#5b7083;--sel:#eaf4f0}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#121619;--card:#1b2127;--ink:#e8ecf0;--muted:#9aa5b1;--line:#2b333c;--sel:#1f2d27}}
:root[data-theme="dark"]{--bg:#121619;--card:#1b2127;--ink:#e8ecf0;--muted:#9aa5b1;--line:#2b333c;--sel:#1f2d27}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,Segoe UI,Roboto,sans-serif}
header{padding:16px;border-bottom:1px solid var(--line);background:var(--card)}
h1{font-size:18px;margin:0 0 4px}h2{font-size:15px;margin:18px 0 8px}h3{font-size:13px;margin:14px 0 6px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
.sub{color:var(--muted);font-size:13px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px;padding:14px 16px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px}
.kpi .v{font-size:22px;font-weight:600}.kpi .l{color:var(--muted);font-size:12px}.kpi .d{font-size:12px;margin-top:4px}
main{display:grid;grid-template-columns:minmax(360px,520px) 1fr;gap:14px;padding:0 16px 24px}
@media(max-width:900px){main{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px}
.filters{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px}
.filters button,.acts button{border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:8px;padding:6px 10px;cursor:pointer}
.filters button.on{background:var(--acc);color:#fff;border-color:var(--acc)}
input[type=search]{width:100%;padding:7px 9px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink);margin-bottom:8px}
table{width:100%;border-collapse:collapse;font-size:13px}th,td{padding:6px 6px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{color:var(--muted);font-weight:500;font-size:12px}tr.row{cursor:pointer}tr.row:hover{background:var(--sel)}tr.row.sel{background:var(--sel);outline:2px solid var(--acc)}
.num{text-align:right;font-variant-numeric:tabular-nums}
.b{display:inline-block;padding:1px 7px;border-radius:999px;color:#fff;font-size:11px;font-weight:600}.b.P1{background:var(--p1)}.b.P2{background:var(--p2);color:#222}.b.P3{background:var(--p3)}
.tag{display:inline-block;padding:1px 7px;border-radius:6px;border:1px solid var(--line);font-size:11px;color:var(--muted);margin-right:4px}
.st{font-weight:600}.st.ok{color:var(--acc)}.st.avertizare{color:var(--acc2)}.st.fail{color:var(--bad)}.st.neexecutat{color:var(--muted)}
.rec{font-size:16px;font-weight:600;padding:8px 10px;border-radius:8px;background:var(--sel);border-left:4px solid var(--acc)}
.rec.respins_escaladat,.rec.blocat{border-left-color:var(--bad)}.rec.restructurare{border-left-color:var(--acc2)}
.muted{color:var(--muted)}.mono{font-family:ui-monospace,Consolas,monospace;font-size:12px}
.chosen{background:var(--sel);font-weight:600}
.acts{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0}.acts button.ok{background:var(--acc);color:#fff;border-color:var(--acc)}
pre{white-space:pre-wrap;background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:8px;font-size:12px}
textarea{width:100%;min-height:50px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink);padding:6px}
details summary{cursor:pointer;color:var(--muted)}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:10px}@media(max-width:700px){.grid2{grid-template-columns:1fr}}
.empty{color:var(--muted);padding:40px;text-align:center}
</style>
</head>
<body>
<header>
  <h1>retailagent — colegul virtual al consilierului de credite retail</h1>
  <div class="sub" id="sub"></div>
</header>
<section class="kpis" id="kpis"></section>
<main>
  <div class="card">
    <h2>Coada prioritizată</h2>
    <div class="filters" id="filters"></div>
    <input type="search" id="q" placeholder="caută client, produs, recomandare…">
    <table><thead><tr><th>caz</th><th>client</th><th>produs</th><th>bandă</th><th class="num">prio</th><th>termen</th><th>recomandare</th></tr></thead><tbody id="rows"></tbody></table>
  </div>
  <div class="card" id="panel"><div class="empty">Alege un caz din coadă.</div></div>
</main>
<script id="data" type="application/json">__DATA__</script>
<script>
const D=JSON.parse(document.getElementById('data').textContent);
const ron=x=>Math.round(x).toLocaleString('ro-RO');const pct=x=>Math.round(x*100)+'%';
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const LBL={nu_interveni:'nu interveni',oferta_minima:'ofertă minimă',oferta_produs:'ofertă + produs',restructurare:'restructurare',respins_escaladat:'respins / escaladat',blocat:'blocat'};
let band='toate',query='',sel=null;const decided={};
function kpis(){const m=D.metrici,h=m.cifra_vedeta,a=h.agent,u=h.uniform_aleasa?h.uniform[h.uniform_aleasa]:null;
 const best=Object.entries(h.uniform).sort((x,y)=>y[1].rata_ramanere-x[1].rata_ramanere)[0];
 const cards=[
  {l:'Cifra-vedetă: cost retenție agent',v:ron(a.cost)+' RON',d:`reține ${a.retinuti}/${h.candidati} candidați (${pct(a.rata_ramanere)})`},
  {l:u?`Aceeași reducere pentru toți (${h.uniform_aleasa} pp)`:`Reducere uniformă pentru toți (${best[0]} pp)`,v:ron((u||best[1]).cost)+' RON',d:u?`aceeași rată de rămânere · economie ${ron(h.economie_ron)} RON`:`reține doar ${pct(best[1].rata_ramanere)} — nu atinge rata agentului`},
  {l:'Cazuri „nu interveni”',v:pct(m.nu_interveni.procent),d:`${m.nu_interveni.nu_interveni} din ${m.nu_interveni.total} cazuri active — bani necheltuiți`},
  {l:'Interogări externe evitate',v:pct(m.interogari_externe.procent),d:`${m.interogari_externe.evitate} din ${m.interogari_externe.rulare_tot} față de „rulează tot”`},
  {l:'Recomandări vs etalon',v:pct(m.recomandari.acuratete),d:`${m.recomandari.corecte}/${m.recomandari.total} clienți`},
  {l:'Cerințe dure',v:Object.values(m.cerinte_dure).reduce((s,x)=>s+x,0)+' încălcări',d:Object.keys(m.cerinte_dure).join(' · ')}];
 document.getElementById('kpis').innerHTML=cards.map(c=>`<div class="kpi"><div class="l">${esc(c.l)}</div><div class="v">${esc(c.v)}</div><div class="d muted">${esc(c.d)}</div></div>`).join('');
 document.getElementById('sub').textContent=`${D.clienti} clienți · ${D.total_cazuri||D.cazuri.length} cazuri${D.total_cazuri&&D.total_cazuri>D.cazuri.length?' (afișate primele '+D.cazuri.length+')':''} · azi ${D.azi} · date 100% sintetice · agentul recomandă, consilierul decide`;}
function filters(){const el=document.getElementById('filters');const opts=['toate',...D.benzi,'cu ofertă','blocate'];
 el.innerHTML=opts.map(o=>`<button class="${o===band?'on':''}" data-b="${o}">${o}</button>`).join('');
 el.querySelectorAll('button').forEach(b=>b.onclick=()=>{band=b.dataset.b;filters();rows();});}
function visible(){return D.cazuri.filter(c=>{const k=c.case,r=c.rec;
 if(band!=='toate'){if(band==='cu ofertă'){if(!r.oferta)return false}else if(band==='blocate'){if(!k.blocaje.length)return false}else if(k.banda!==band)return false}
 if(query){const s=(k.case_id+' '+k.client_id+' '+c.client.nume+' '+k.produs+' '+r.recomandare+' '+r.eticheta).toLowerCase();if(!s.includes(query))return false}
 return true});}
function rows(){const tb=document.getElementById('rows');tb.innerHTML=visible().map(c=>{const k=c.case;const dec=decided[k.case_id];
 return `<tr class="row ${sel===k.case_id?'sel':''}" data-id="${k.case_id}"><td class="mono">${k.case_id}</td><td>${esc(c.client.nume)}<div class="muted mono">${k.client_id} · ${c.client.nivel}</div></td><td>${esc(k.produs||'—')}</td><td><span class="b ${k.banda}">${k.banda}</span>${k.blocaje.length?' <span class="tag">blocat</span>':''}</td><td class="num">${k.scoruri.prioritate.toFixed(2)}</td><td class="mono">${k.deadline}</td><td>${esc(LBL[c.rec.recomandare])}${dec?` <span class="tag">${esc(dec)}</span>`:''}</td></tr>`}).join('');
 tb.querySelectorAll('tr').forEach(tr=>tr.onclick=()=>{sel=tr.dataset.id;rows();panel();});}
function st(s){return `<span class="st ${s}">${{ok:'✔',avertizare:'⚠',fail:'✘',neexecutat:'·',indisponibil:'◌'}[s]} ${s}</span>`}
function panel(){const c=D.cazuri.find(x=>x.case.case_id===sel);if(!c)return;const k=c.case,ch=c.check,o=c.offer,r=c.rec,s=k.scoruri;
 const loan=c.loan?`sold ${ron(c.loan.sold)} RON · ${c.loan.tip_dobanda} ${c.loan.dobanda}%${c.loan.expira?' (fixă până la '+c.loan.expira+')':''} · rată ${ron(c.loan.rata)} RON`:'fără credit existent';
 let h=`<h2>${k.case_id} · ${esc(c.client.nume)} <span class="muted">(${k.client_id}, ${c.client.nivel}, ${c.client.tipologie}, client din ${c.client.client_din.slice(0,4)})</span></h2>
 <div class="muted">${k.loan_id||'—'} · ${esc(k.produs||'—')} · ${loan}</div>
 <div style="margin:8px 0"><span class="b ${k.banda}">${k.banda}</span> prioritate ${s.prioritate.toFixed(2)} · termen ${k.deadline} · acțiune ${esc(k.actiune_propusa)} · sursă ${k.sursa}${k.request_id?' · cerere '+k.request_id:''}</div>
 <div class="rec ${r.recomandare}">${esc(r.eticheta.toUpperCase())}${r.interventie?' · '+esc(r.interventie):''}</div><div style="margin:6px 0">${esc(r.motiv)}</div>`;
 h+=`<div class="acts"><button class="ok" data-d="aproba">Aprobă</button><button data-d="modifica">Modifică</button><button data-d="respinge">Respinge</button></div><div id="actout"></div>`;
 h+=`<h3>Semnale</h3><table><thead><tr><th>familie</th><th>semnal</th><th class="num">scor</th><th>dovada</th></tr></thead><tbody>${k.semnale.map(x=>`<tr><td><span class="tag">${x.familie}</span></td><td class="mono">${x.id}</td><td class="num">${x.scor.toFixed(2)}</td><td>${esc(x.dovada)}</td></tr>`).join('')}</tbody></table>
 <div class="muted" style="margin-top:6px">plecare ${s.plecare} × valoare ${s.valoare} × actiune ${s.actiune} = ${s.prioritate_retentie} · risc_credit ${s.risc_credit} · prioritate ${s.prioritate}</div>`;
 h+=`<h3>Verificări <span class="muted">(alese după produse deținute + motiv: ${ch.motive.map(m=>m.motiv).join(', ')})</span></h3>
 <div class="grid2"><div><div class="muted">planificate (înainte de rulare)</div><table><tbody>${ch.plan.map(x=>`<tr><td><span class="tag">${x.treapta}</span></td><td class="mono">${x.id}${x.externa?' <span class="tag">extern</span>':''}</td><td class="muted">${esc(x.motiv)}</td></tr>`).join('')}</tbody></table></div>
 <div><div class="muted">omise</div><table><tbody>${ch.omise.map(x=>`<tr><td class="mono">${x.id}${x.externa?' <span class="tag">extern</span>':''}</td><td class="muted">✗ ${esc(x.motiv)}</td></tr>`).join('')||'<tr><td class="muted">—</td></tr>'}</tbody></table></div></div>
 <div class="muted" style="margin:8px 0 4px">rezultate · interogări externe: ${ch.interogari.executate} din ${ch.interogari.rulare_tot} posibile (${ch.interogari.rulare_tot-ch.interogari.executate} evitate)${ch.oprit_la?' · <b>oprit la '+ch.oprit_la+' ('+ch.verificare_picata+')</b>':''}</div>
 <table><tbody>${ch.rezultate.map(x=>`<tr><td>${st(x.status)}</td><td class="mono">${x.id}</td><td>${esc(x.dovada)}${x.sursa&&x.sursa!=='intern'?' <span class="tag">'+esc(x.sursa)+'</span>':''}</td></tr>`).join('')}</tbody></table>`;
 const L=o.legaturi,b=o.B_detalii;
 h+=`<h3>Retenție <span class="muted">(cea mai ieftină implicare care păstrează clientul)</span></h3>
 <div>B = dobândă la noi ${ron(b.dobanda_la_noi)} − piață ${ron(b.dobanda_piata)} − cost mutare ${ron(b.cost_mutare)} = <b>${ron(o.B)} RON</b> în ${b.orizont_luni||0} luni · legături <b>${L.scor.toFixed(2)}</b> (produse ${L.componente.produse}, vechime ${L.componente.vechime}, nivel ${L.componente.nivel}, activitate ${L.componente.activitate}) · semnale active: ${o.semnale_active.join(', ')||'—'}</div>
 <div>p = <b>${pct(o.p)}</b> (țintă ≤ ${pct(o.p_tinta)})${o.model?' · model '+esc(o.model.nume)+(o.model.nume==='antrenat'?' '+esc(o.model.versiune):''):''} · V = ${ron(o.V)} RON · p × V = ${ron(o.p*o.V)} RON</div>
 ${o.contributii?`<div class="muted">contribuții pe logit: ${o.contributii.map(c=>esc(c[0])+' '+(c[1]>=0?'+':'')+c[1].toFixed(2)).join(', ')}</div>`:''}
 <table><thead><tr><th>intervenție</th><th>fezabil</th><th class="num">cost RON</th><th class="num">B după</th><th class="num">p după</th><th>țintă</th><th>merită</th><th>motiv</th></tr></thead><tbody>${o.interventii.map(i=>`<tr class="${i.id===o.aleasa?'chosen':''}"><td>${i.id===o.aleasa?'► ':''}${esc(i.eticheta)}</td><td>${i.fezabil?'da':'<span class=\"st fail\">nu</span>'}</td><td class="num">${ron(i.cost)}</td><td class="num">${ron(i.B_dupa)}</td><td class="num">${pct(i.p_dupa)}</td><td>${i.respecta_tinta?'da':'nu'}</td><td>${i.merita?'da':'nu'}</td><td class="muted">${esc(i.motiv_infezabil||'')}</td></tr>`).join('')}</tbody></table>
 <div style="margin-top:6px">${esc(o.explicatie)}</div>`;
 h+=`<h3>Recomandare</h3><div>${esc(r.explicatie)}</div>`;
 if(r.oferta){h+=`<h3>Oferta</h3><table><tbody>${Object.entries(r.oferta).filter(([k,v])=>v!==null&&v!==undefined).map(([k,v])=>`<tr><td class="muted">${k}</td><td>${typeof v==='number'&&['rata_veche','rata_noua','cost_banca','economie_client','suma','scutire_ron','sold_dupa_pauza'].includes(k)?ron(v)+' RON':esc(v)}</td></tr>`).join('')}</tbody></table>`}
 if(r.grafic){const g=r.grafic;h+=`<details><summary>Grafic de rambursare (primele 12 din ${g.nr_rate} rate · dobândă totală ${ron(g.dobanda_totala)} RON)</summary><table><thead><tr><th>nr</th><th>luna</th><th class="num">rata</th><th class="num">dobândă</th><th class="num">principal</th><th class="num">sold rămas</th></tr></thead><tbody>${g.primele_luni.map(x=>`<tr><td>${x.nr}</td><td class="mono">${x.luna}</td><td class="num">${ron(x.rata)}</td><td class="num">${ron(x.dobanda)}</td><td class="num">${ron(x.principal)}</td><td class="num">${ron(x.sold_ramas)}</td></tr>`).join('')}</tbody></table></details>`}
 h+=`<h3>Documente</h3>${r.documente_lipsa.length?'<ul>'+r.documente_lipsa.map(d=>`<li><b>${esc(d.tip)}</b> — ${esc(d.motiv)}</li>`).join('')+'</ul>':'<div class="muted">dosarul e complet pentru această recomandare</div>'}`;
 const p=document.getElementById('panel');p.innerHTML=h;p.scrollTop=0;
 p.querySelectorAll('.acts button').forEach(bt=>bt.onclick=()=>act(c,bt.dataset.d));}
function act(c,d){const k=c.case,o=c.offer,out=document.getElementById('actout');
 if(d==='aproba'){decided[k.case_id]='aprobat';out.innerHTML=`<div class="muted">Comanda echivalentă (scrie approvals.json + audit):</div><pre>python -m retailagent.approve ${k.case_id}</pre>`;rows();return}
 const fez=o.interventii.filter(i=>i.fezabil&&i.id!==o.aleasa);
 out.innerHTML=`<div class="muted">${d==='modifica'?'Alege intervenția și scrie motivul (obligatoriu la override):':'Motivul respingerii (obligatoriu):'}</div>
 ${d==='modifica'?`<select id="iv">${fez.map(i=>`<option value="${i.id}">${esc(i.eticheta)} · ${ron(i.cost)} RON · p ${pct(i.p_dupa)}</option>`).join('')}</select>`:''}
 <textarea id="mot" placeholder="motiv…"></textarea><div class="acts"><button class="ok" id="go">Generează comanda</button></div><pre id="cmd"></pre>`;
 document.getElementById('go').onclick=()=>{const m=document.getElementById('mot').value.trim();if(!m){document.getElementById('cmd').textContent='Motivul e obligatoriu pentru un override.';return}
  const iv=d==='modifica'?document.getElementById('iv').value:null;decided[k.case_id]=d==='modifica'?'modificat → '+iv:'respins';
  document.getElementById('cmd').textContent=`python -m retailagent.approve ${k.case_id} --decizie ${d}${iv?' --interventie '+iv:''} --motiv "${m.replace(/"/g,'\\"')}"`;rows();};}
document.getElementById('q').addEventListener('input',e=>{query=e.target.value.toLowerCase();rows();});
kpis();filters();rows();if(D.cazuri.length){sel=D.cazuri[0].case.case_id;rows();panel();}
</script>
</body>
</html>
"""


def main(argv: list[str] | None = None) -> None:
    setup_console()
    ap = argparse.ArgumentParser(description="Generează out/demo.html (pagină statică, autonomă).")
    ap.add_argument("--today")
    ap.add_argument("--data-dir", default=str(DATA_DIR))
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ap.add_argument("--config-dir", default=str(CONFIG_DIR))
    ap.add_argument("--max-cazuri", type=int, default=200, help="câte cazuri din coadă intră în pagină (0 = toate)")
    ap.add_argument("--ui-dir", default=str(UI_DIR), help="folderul interfeței React; dacă există, primește snapshot-ul în public/data")
    ap.add_argument("--fara-ui", action="store_true", help="nu sincroniza ui/public/data")
    a = ap.parse_args(argv)
    t0 = time.perf_counter()
    full = run_full(a.data_dir, a.out_dir, a.config_dir, a.today)
    gt = read_json(Path(a.data_dir) / "ground_truth.json")
    data = build_data(full, gt, a.max_cazuri or None)
    html = build_html(full, gt, data=data)
    out = Path(a.out_dir) / "demo.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    dt = time.perf_counter() - t0
    print(f"Demo: {len(full.res.cases)} cazuri → {out} ({out.stat().st_size / 1024:.0f} KB) în {dt:.2f}s — deschide fișierul în browser")
    if not a.fara_ui:
        dest = sync_ui(data, Path(a.out_dir), Path(a.ui_dir))
        if dest:
            print(f"  interfața React: snapshot → {dest} (cd ui && npm run dev)")
    log_event(a.out_dir, "demo", "done", cazuri=len(full.res.cases), kb=round(out.stat().st_size / 1024), secunde=round(dt, 3))


if __name__ == "__main__":
    main()
