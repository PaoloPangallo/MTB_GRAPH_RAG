# Unsupported or partial claims

## Parzialità rilevate

| claim_id | asse | motivo deterministico |
|---|---|---|
| CLM-091cf6602db85e2a2d41 | direction | stable disease, non risposta non qualificata |
| CLM-5ce532268b4aa1661311 | biomarker | ALK-rearranged è esplicito, EML4 non è esplicito nell'abstract |
| CLM-4ffe85304f3ef5533b58 | biomarker/context | L858R è accorpato alle delezioni exon 19 |
| CLM-90e863f00f134fc3cd3d | intervention/context | BGJ398/PD173074 e NIH3T3; non infigratinib clinico |
| CLM-1fc4af943701d57d45ad | biomarker/context | effetto del gruppo non isolato per L858R |
| CLM-89ea67ee7946d9ccd552 | biomarker/context | effetto del gruppo non isolato per L858R |
| CLM-a7e1c40b794d2c4d4ca8 | biomarker/context | prevalenza riferita alle fusioni FGFR2 aggregate |
| CLM-5071bb2d8657ac0fbed0 | intervention/context | BGJ398 e NIH3T3; risultato non separato come beneficio clinico AHCYL1 |
| CLM-0269a5c7db107cd8a893 | intervention/evidence type | AZD9291 non collegato localmente al nome canonico; modelli misti |
| CLM-1e4f404ac84ee591fbda | intervention/disease | BGJ398, non infigratinib; trattamento su cholangiocarcinoma ampio |

## Categorie non osservate nel campione

Non sono stati assegnati `CONTEXT_ONLY`, `CONTRADICTED`, `NO_SUPPORT_FOUND` o
`TEXT_UNAVAILABLE`. Non sono stati forzati: un testo assente per un campo non è
stato trasformato in contraddizione e un titolo non è stato usato come prova.

## Applicabilità

Le claim preclinical FGFR2 sono applicabili al contesto di un assay cellulare,
non a una conclusione clinica. Le claim diagnostic FGFR2 sono applicabili a
una definizione di sottotipo molecolare, non a clinical utility. Le claim B
sono applicabili come candidati da sottoporre a source-unit review, non come
provenance già verificata.
