# Selezione dei 5 casi

Tutti i casi sono derivati da `GraphCandidateAssertion`/`EvidenceBundle` già
congelati (25 bundle, stesso universo usato in tutte le fasi precedenti del
Claim Extractor), così da conoscere il risultato atteso senza inventare
associazioni cliniche. Il parser non riceve mai il record strutturato di
origine — solo il testo clinico libero (vedi `case_definitions.py`).

| Caso | Candidate | Disease/Biomarker/Drug | Baseline B | Obiettivo |
|---|---|---|---|---|
| 1 | GCA-008ae3aad1a64c118318ef79 | Colorectal Cancer / KRAS G12D / panitumumab | DIRECT | Match forte, THERAPY_EVALUATION |
| 2 | GCA-0031c17c5ff5ae29ff221b1e | Colorectal Cancer / BRAF V600E / encorafenib (omesso dal testo) | AMBIGUOUS | THERAPY_DISCOVERY, scoperta dal KG |
| 3 | GCA-02861e174359dd9f4f53df9b | Colorectal Cancer / MSI (sottotipo omesso) / nivolumab | PARTIAL | Contesto incompleto, warning atteso |
| 4 | GCA-0062c0237b990701837a1cc4 | Lung Squamous Cell Carcinoma / FGFR1 Amplification / infigratinib | CONTRADICTED | Nessuna promozione impropria a positivo |
| 5 | — (fabbricato) | Colorectal Cancer / ZZTK9 P44R (gene inesistente) / panitumumab | n/a | NO_MATCH, nessuna evidenza artificiale |

Per ciascun caso, campi usati/omessi/perturbati e risultato atteso sono
registrati in dettaglio in `case_definitions.py` e in `test_cases.json`.
