# Cerințe (rezumat operațional)

Referință: `MODEL_FINAL.md` (28 oct 2026). Flux: portofoliu → scan semnale → coadă (plecare × valoare ×
actiune; risc = canal separat) → verificări alese din produse deținute + motiv (intern → ANAF → BC → CRC →
garanție, oprire la primul pas picat) → model de retenție (cea mai ieftină implicare: meniu × cost ×
probabilitate de rămânere; BNR + plafoane = constrângeri) → recomandare (nu interveni | ofertă minimă |
ofertă + produs | restructurare | respins/escaladat; + blocat) → consilierul aprobă → documente + log.

Metrici cerute: cost retenție agent vs. „aceeași reducere pentru toți" la aceeași rată de rămânere
(cifra-vedetă); % „nu interveni"; interogări externe evitate; P/R pe semnale; acuratețe benzi/acțiuni;
cerințe dure: 0 oferte către risc activ, 0 oferte în afara limitelor, toate expirările < 30 zile în P1.

Principii: tot ce e regulă/pondere/prag/meniu stă în YAML; date 100% sintetice; agentul recomandă, omul
decide; fiecare decizie explicabilă în română, cu cifre și sursă.

Starea la bootstrap: Modulul 1 gata (22 semnale, coadă, explain, evaluate, 66 teste). Date extinse pentru
modelul final: `data/conturi.json`, `data/documente.json`, `data/externe/{anaf,biroul_credit,crc,garantii}.json`,
`market.json → dobanzi_piata, costuri_mutare`, `ground_truth → recomandare_asteptata, verificare_picata_asteptata,
comportament`.
