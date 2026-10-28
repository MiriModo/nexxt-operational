# retailagent-ui

Interfață de ofițer pentru coada de cazuri produsă de `retailagent`. Vite + React + TypeScript.

## Pornire

```
cd ui
npm install
npm run dev        # http://localhost:5173
npm run build      # dist/
```

## Surse de date

- **Azi (fără API):** `public/data/demo.json` este snapshot-ul încorporat în `out/demo.html`
  (`<script id="data">`), plus copii ale `out/*.json`. Deciziile se țin în `localStorage`;
  ecranul de decizie afișează comanda `python -m retailagent.approve` echivalentă.
- **Cu API (pasul 4):** setează `VITE_API_URL` (de exemplu `http://127.0.0.1:8000/api`) și
  aceleași funcții din `src/api/client.ts` lovesc `GET /cazuri`, `GET /cazuri/{id}`,
  `POST /cazuri/{id}/decizie`, `GET /metrici`.

Reîmprospătarea datelor statice, când `out/` e regenerat (din rădăcina proiectului):

```
python -m retailagent.demo          # scrie out/demo.html ȘI ui/public/data/{demo,queue,checks,offers,recommendations,evaluation}.json
python -m retailagent.pipeline      # tot fluxul; apelează demo la final, deci sincronizează și UI-ul
```

`public/data/` e generat și ignorat de git. Cu API-ul pornit:

```
uvicorn retailagent.api:app --reload --port 8000      # din rădăcină
cd ui && VITE_API_URL=/api npm run dev                 # Vite proxy-ază /api → 8000
```

Deciziile trimise prin API intră în `out/approvals.json` și `out/audit.jsonl`, exact ca `python -m retailagent.approve`.

## Ecrane

| Rută                   | Resursă API            | Conținut                                                                 |
| ---------------------- | ---------------------- | ------------------------------------------------------------------------ |
| `/`                    | `GET /cazuri`, `GET /metrici/context` | pagina de start: salut, data, ce te așteaptă azi (deschise, cu termen azi, blocate, decise), primele 5 cazuri de deschis |
| `/dashboard`           | `GET /metrici`         | cifra-vedetă (agent vs uniform), nu interveni, interogări evitate, acuratețe, cerințe dure, distribuție |
| `/cazuri`              | `GET /cazuri`          | coada ca listă de carduri grupate pe bandă (azi / săptămâna aceasta / poate aștepta), fiecare card e link spre detalii; filtre pe bandă, căutare, ordonare |
| `/cazuri/:id`          | `GET /cazuri/{id}`     | client, credit, semnale cu dovezi, verificări (rezultate + omise), concluzii, model de retenție (B, p, V, meniu), recomandare, grafic, documente lipsă |
| `/cazuri/:id/decizie`  | `POST /cazuri/{id}/decizie` | aprobă / modifică (cu intervenție alternativă) / respinge, motiv obligatoriu, comanda CLI echivalentă |

## Design: paletă și font Raiffeisen, elemente împrumutate de la outcomelab.co.uk

De la outcomelab.co.uk: butoanele pill de 44 px (primar plin, secundar alb cu chenar care se întunecă la hover),
cardurile cu chenar fin și umbră lungă discretă, easing-ul `cubic-bezier(.25,1,.5,1)` cu durate 0.25 s / 0.5 s,
linkurile cu subliniere care coboară la hover, panoul hero închis și rotunjit cu titlu mare și strâns
(`letter-spacing -0.045em`, `line-height 0.98`), perechile număr mare + etichetă mică și o singură animație
de intrare (hero-rise), dezactivată la `prefers-reduced-motion`.

Tokenurile din `src/styles.css` reproduc paleta publică din CSS-ul raiffeisen.ro: galben `#fee600`
(doar pentru acțiunea principală și linia de sus a antetului), off-black `#2b2d33` pentru text,
teal `#037080` pentru linkuri, gri cald `#f8f6f2` / `#f1ede6` pentru fundaluri, semnale
`#cf030a` / `#e54f1b` / `#0b7d3e`. Există variantă dark (`prefers-color-scheme`), fără comutator
propriu în aplicație. Toate perechile text/fundal au contrast ≥ 4.5:1 (valorile sunt notate în CSS).

Fontul de brand este **Amalia** (proprietar, licență enterprise). Lanțul este
`Amalia, Figtree, Arial, Helvetica, sans-serif`:
- dacă ai licența, pune fișierele `AmaliaW05-Regular.woff2`, `AmaliaW05-Medium.woff2`,
  `AmaliaW05-Bold.woff2` în `public/fonts/` și se încarcă automat (până atunci consola
  afișează un avertisment de decodare a fontului, inofensiv);
- altfel se folosește Figtree (Google Fonts, geometric cu x-height mare, apropiat de Amalia),
  iar offline Arial/Helvetica.

Contractul de date este în `src/types/api.ts`; pe partea de Python îl produce `retailagent/demo.py → build_data`
(același snapshot pentru `demo.html`, `public/data/demo.json` și API). Câmpurile `offer.model` și
`offer.contributii` apar când platforma rulează pe modelul de churn antrenat.
