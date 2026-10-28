# MODEL FINAL — Agent de retenție și procesare credite retail (Raiffeisen · Operational Efficiency)

Versiune: 28 oct 2026, 15:23. Acesta este modelul de referință. Orice spec, cod sau pitch pleacă de aici.

## Ce construim
Un coleg virtual pentru consilierul de credite retail (persoane fizice: ipotecar, imobiliar, nevoi personale, card de credit, refinanțare). Găsește singur în portofoliu cazurile care trebuie lucrate, face verificările pe care le-ar face omul, și calculează **cea mai ieftină implicare a băncii care păstrează clientul**. Consilierul aprobă.

## Schema
```
Portofoliu ──scan semnale──┐
                           ├──► Coadă prioritizată (plecare × valoare × urgență; risc de credit = canal separat)
Cereri clienți ────────────┘            │
                                        ▼
            Verificări alese din: produse deținute + motiv (cerere sau semnal)
            (intern → ANAF → Biroul de Credit → CRC → garanție; în trepte, se oprește la primul pas picat)
                                        │
                                        ▼
          Model de retenție: cea mai ieftină implicare care păstrează clientul
          (meniu de intervenții × cost pentru bancă × probabilitate de rămânere;
           limitele BNR și plafoanele interne = constrângeri, nu etapă)
                                        │
                                        ▼
   recomandare: nu interveni | ofertă minimă | ofertă + produs | restructurare | respins/escaladat
                                        │
                                        ▼
                         consilierul aprobă → documente + log
```

## Ce s-a tăiat (decizii luate cu mentorul)
- **Tipologia clientului ca etapă** — tăiată. Verificările se aleg din produse deținute + motiv; detaliile despre client se citesc din date când e nevoie.
- **„Reguli BNR + politica băncii" ca pas vizibil** — tăiat. Limitele (DTI 40/20 +5 prima locuință, LTV, vârstă, marjă minimă, buget de retenție) rămân ca **constrângeri în interiorul modelului de ofertă**.

## 1. Scan semnale → coadă
Trei familii de semnale (configurate în YAML):
- **plecare**: expirare dobândă fixă, gap față de piață în bani, cerere adeverință de sold / refinanțare, rate plătite către alt creditor, salariu mutat, eligibilitate externă (istoric curat, LTV < 0,8, fără restructurare), vechime credit, sold rămas, simulări în app.
- **risc de credit**: întârziere nouă, venit în scădere/dispărut, card la ≥90% cu plată minimă, angajator în dificultate, restructurare anterioară, poprire activă, LTV depășit.
- **blocaj de proces**: CI expirată, KYC vechi, consimțământ lipsă, asigurare expirată, flag blocant (PEP/fraudă/decedat).

Prioritate:
```
plecare  = Σ pondere_i × scor_i
valoare  = 0,6 × venit_viitor_norm + 0,4 × produse_atașate_norm
actiune  = 1 | 0,5 | 0   (există intervenție posibilă în plafoane?)
prioritate_retentie = plecare × valoare × actiune
risc_credit = max(semnale risc)
prioritate_caz = max(risc_credit, prioritate_retentie)
```
Benzi P1/P2/P3 cu SLA; deadline = min(SLA, expirare dobândă fixă − 30 zile). Risc de credit ≥ 0,7 → **nicio ofertă de retenție**, traseu de restructurare. Blocaj activ → task, cazul rămâne „blocat".

## 2. Verificări după produse deținute + motiv
- **bază**: identitate/KYC/consimțăminte (moștenite din coadă), expuneri interne (credite, carduri la % din limită, codebitor/garant), venit observat din încasări, sold mediu/minim.
- **strat produse deținute**: ipotecar → LTV, asigurări, CF; card → utilizare limită; nevoi personale → nimic în plus.
- **strat motiv** — adaugă / sare:
  - expirare dobândă fixă / refinanțare → scenarii rămâi/refinanțezi/pleci, cost mutare, meniu intervenții; nu sare nimic din eligibilitate.
  - simulare rambursare anticipată → comision OUG 50 (0 la variabilă), fond de urgență, lunar vs anual; sare BC, CRC, garanție.
  - credit nou / majorare limită → eligibilitate completă pe produsul-țintă.
  - întârziere / venit în scădere / card stres → capacitate de plată actuală, opțiuni restructurare; grila de retenție blocată.
  - adeverință de sold → documentul + declanșează analiza de retenție.
  - CI expirată / consimțământ lipsă → doar task-ul; restul așteaptă.
- Lista rezultată se afișează **înainte** de rulare, cu motivul fiecărei verificări și al fiecărei omisiuni. Metrică: interogări externe evitate față de „rulează tot".
- Produsele deținute (expuneri) ≠ produsul vizat (eligibilitate). La refinanțare, produsul vizat e cel nou; cel vechi intră la deținute cu sold și comision.

## 3. Model de retenție — cea mai ieftină implicare
Pe client:
- **B** = câștigul clientului dacă pleacă = (dobânda lui după expirare − dobânda pieței) × sold × ani rămași − costul mutării (evaluare, notar, OCPI, asigurări noi, comision bancă nouă).
- **p** = probabilitatea de plecare = sigmoid(a·B_norm + b·semnale_active − c), parametri în YAML.
- **V** = valoarea clientului dacă rămâne = marjă × sold × ani rămași + produse atașate.

Meniu de intervenții (fiecare cu cost pentru bancă și efect asupra lui B / p):
nu interveni · informare + simulare personalizată · scutire comision / evaluare gratuită · reducere marjă 0,2/0,4/0,6 pp · nouă perioadă fixă la dobânda pieței (1/3/5 ani) · ajustare maturitate / pauză de rată (pentru risc) · pachet (salariu la noi + reducere).

Optimizare: alege intervenția cu **cost minim** pentru care `p_după ≤ p_țintă` **și** `cost ≤ p_înainte × V`. Dacă nu există → „nu interveni" sau „informare". Risc de credit activ → „restructurare". Constrângerile (BNR + plafoane interne) elimină opțiunile înainte de optimizare.

Output pentru consilier (exemplu): „Clientul ar câștiga 41.200 RON plecând; p = 68%. Oferta minimă care îl aduce sub 20%: fix 3 ani la 5,1%, cost 9.800 RON față de 38.000 RON valoare pierdută. Alternativa 0,4 pp pe toată durata: 17.300 RON. Recomandare: fix 3 ani."

## 4. Recomandare și aprobare
Una din: nu interveni | ofertă minimă | ofertă + produs | restructurare | respins/escaladat. Consilierul aprobă sau modifică **cu motiv**; override-ul intră în log. Se generează oferta, graficul, lista documentelor lipsă, explicația în română cu cifre, logul de audit (semnal/verificare/valoare/sursă/timestamp).

## Metrici (evaluate.py, pe 50 de cazuri sintetice cu semnale plantate)
- costul total al retenției cu agentul vs. „aceeași reducere pentru toți", la aceeași rată de rămânere (cifra-vedetă);
- procentul de cazuri „nu interveni" (bani necheltuiți);
- interogări externe evitate prin alegerea verificărilor după motiv;
- precizie/recall pe semnale plantate; acuratețea benzilor și a acțiunilor;
- cerințe dure: 0 oferte către clienți cu risc de credit activ, 0 oferte în afara limitelor, toate expirările < 30 zile în P1.

## Principii
- Tot ce e regulă, pondere, prag, meniu sau constrângere stă în YAML; un produs/semnal/intervenție nou(ă) = configurație, nu cod.
- Date 100% sintetice, mock-uri pentru ANAF / Biroul de Credit / CRC / garanție.
- Agentul pregătește și recomandă; omul decide. Nu negociază marja; aplică meniul și plafoanele.
- Fiecare decizie e explicabilă în română, cu cifre și cu sursa.
