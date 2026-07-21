# Discrepanze - PILOT-K1-FGFR2-iCCA

**Categoria:** KNOWN_TRAVERSAL
**Stato annotazione:** Prima annotazione completa; seconda revisione necessaria

## Terapie

**Attese**
- `futibatinib`
- `pemigatinib`

**Trovate nel grafo**
- `derazantinib`
- `erdafitinib`
- `infigratinib`
- `pazopanib hydrochloride`
- `pd173074`
- `pemigatinib`
- `ponatinib`

**Mancanti**
- `futibatinib`

**In piu'**
- `derazantinib`
- `erdafitinib`
- `infigratinib`
- `pazopanib hydrochloride`
- `pd173074`
- `ponatinib`

## PMID

**Mancanti**
- `36652354`

**Trovati**
- `160559`
- `18757403`
- `23658459`
- `23786770`
- `24122810`
- `24550739`
- `26324363`
- `26574622`
- `27179038`
- `27870574`
- `29182496`
- `30420614`
- `32203698`
- `32973082`
- `34358484`
- `35507888`
- `38710951`

## NCT

**Mancanti**
- `NCT02052778`
- `NCT02924376`

**Trovati**
- _nessuno_

## Claim

- pienamente corrispondenti: 0
- parzialmente corrispondenti: 1
- senza riscontro: 1

## Conflitti

- **K1-C1** / `disease`: gold `intrahepatic cholangiocarcinoma` vs grafo `cholangiolocellular carcinoma` (relazione: different_specificity (sottotipo e genitore non sono equivalenti))

## Qualificatori non modellati dallo schema

- `ecog`
- `line`
- `prior_therapy`
- `resection_status`
- `setting`
- `stage`

## Avvertenze

- `nessuno degli NCT attesi e' presente come nodo ClinicalTrial`
- `citazioni con PMID implausibilmente corti: ['160559']; probabile difetto di ingestione nel campo citation_id, da verificare prima di usarli come fonte`
- `13 record usano una denominazione di malattia meno specifica di 'intrahepatic cholangiocarcinoma' (es. colangiocarcinoma generico): non sono equivalenti e non vengono contati come corrispondenza`
- `linea di terapia, stadio ed esposizione precedente a FGFR-inibitori non sono modellati dallo schema: ricavabili solo per euristica testuale`

## Freeze blockers

- `PMID attesi assenti dallo snapshot: ['36652354']`
- `NCT attesi assenti dallo snapshot: ['NCT02052778', 'NCT02924376']`
- `terapie attese non raggiunte dal traversal: ['futibatinib']`
- `claim senza alcun record corrispondente: ['K1-C2']`
- `conflitti di qualificatore non risolti: ['disease']`

**Freeze ready:** no

**Decisione proposta:** AMEND

0 claim pienamente corrispondenti, 1 parziali, 1 senza riscontro; 5 freeze blocker da risolvere prima del congelamento.
