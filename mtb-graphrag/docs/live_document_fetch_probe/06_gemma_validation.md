# Gemma e validazione deterministica

**VERIFIABLE RESEARCH PIPELINE — NOT CLINICALLY VALIDATED.**

Artefatto: `gemma_probe.json`.

## 1. Cosa è stato passato al modello

Le SourceUnit **appena scaricate**, mai quelle della cache. Contratto invariato:
`paper_context_enricher_v2` reale, `PaperContextEnrichmentV2Validator` reale,
decisione `QUOTE` oppure `ABSTAIN`. Nessuna raccomandazione richiesta.

Due strategie di selezione delle unità, perché misurano cose diverse:

- **naive** — le prime N unità del documento. È ciò che potrebbe fare
  un'architettura cache-miss, che di bundle congelati non ne ha.
- **curated** — le unità che il bundle indica, prelevate però dal documento
  appena scaricato.

## 2. Esiti

| Slot | Selezione | Decisione | Validatore | Quote verificata |
|---|---|---|---|---|
| A | naive | `QUOTE` | `ENRICHMENT_V2_ACCEPTED` | sì, offset 1130 |
| A | curated | `QUOTE` | `ENRICHMENT_V2_ACCEPTED` | sì, offset 78 |
| B | naive | `ABSTAIN` | `ENRICHMENT_V2_ABSTAINED_WITH_INCONSISTENT_FIELDS` | — |
| B | curated | `ABSTAIN` | `ENRICHMENT_V2_ABSTAINED` | — |
| C | naive | `QUOTE` | `ENRICHMENT_V2_ACCEPTED` | sì, offset 144 |
| C | curated | `QUOTE` | `ENRICHMENT_V2_ACCEPTED` | sì, offset 144 |

`replayed: false` ovunque, `transport_result: V2_TRANSPORT_VALID`,
`status_code: 200`, modello `gemma4:cloud`.

L'`quote_offset` è la misura che conta: il validatore ha ritrovato la citazione
del modello, verbatim, dentro il testo scaricato pochi secondi prima. Non è
un giudizio di plausibilità — è una ricerca di sottostringa.

## 3. L'astensione di B, esaminata

Prima ipotesi: colpa della selezione. Su 243 unità la sonda ne aveva offerte
quattro — titolo, intestazione «Introduction» e due frammenti introduttivi.
Verifica: le 3 unità del bundle congelato erano **tutte presenti** nel documento
scaricato (3/3), ma solo una coincideva con le prime quattro.

Ripetuto con le unità curate, il modello **si è astenuto di nuovo**. L'ipotesi
era sbagliata, e il risultato è più interessante.

La candidate riguarda **ABL1 V299L** in leucemia mieloide cronica. Il bundle
congelato registra:

```json
{"support_status": "PARTIAL",
 "core_support_mask": {"biomarker": "UNSUPPORTED", "direction": "UNSUPPORTED",
                       "disease": "SUPPORTED", "intervention": "NOT_APPLICABLE"},
 "shadow_policy": {"result": "SHADOW_AUDIT_ONLY"}, "review_required": true}
```

Motivazione di Gemma oggi: *«No mention of the specific ABL1 V299L mutation in
the provided source units.»*

**Il modello, leggendo un documento riscaricato da zero, è arrivato alla stessa
conclusione che il pilot aveva registrato nel 2026-08-03**: quel documento non
sostiene quel biomarcatore. L'astensione è l'esito corretto, non un fallimento
del recupero.

## 4. Cosa la selezione curata ha comunque migliorato

Con le prime quattro unità il modello ha astenuto **e** ha compilato
`source_unit_id`, violando il contratto: il validatore lo ha intercettato con
`FIELDS_POPULATED_DESPITE_ABSTAIN`. Con le unità del bundle l'astensione è
pulita, `ENRICHMENT_V2_ABSTAINED`.

Un dato utile per il futuro: la qualità delle unità offerte influenza la
conformità al contratto, non solo la decisione.

## 5. Criterio §12

Richiesto: almeno una quote validata **oppure** un'astensione corretta.

- A: quote validata ✅
- B: astensione corretta, coerente con la baseline ✅
- C: quote validata ✅

Soddisfatto su tutti e tre.
