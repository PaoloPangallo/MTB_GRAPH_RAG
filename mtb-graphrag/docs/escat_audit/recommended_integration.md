# Raccomandazione

## Decisione

**E. ESCAT non realmente presente nei dati attivi**

La scelta è E, con una distinzione importante:

- ESCAT compare come vocabolario nel contratto EvidenceStatement e come
  campo derivato escat_tier nel runtime legacy;
- non compare come annotazione del Knowledge Graph, del GraphEvidenceRecord,
  della source unit o delle qualified claim attive;
- evidence_level non può essere reinterpretato come ESCAT;
- il runtime legacy non fornisce provenance, versione o curator per il tier
  calcolato.

Non è quindi sicuro propagare direttamente il campo al runtime V3.

## Condizioni per una futura propagazione

Prima dell'integrazione servirebbe un record strutturato che conservi almeno:

- valore originale e sistema tassonomico;
- biomarcatore e alterazione;
- malattia e contesto;
- terapia e direzione;
- fonte, PMID/DOI e locator;
- versione ESCAT, data di validità e curator/provider;
- distinzione tra assegnazione del provider e mappatura locale.

La normalizzazione dovrebbe usare solo valori espliciti con sistema escat.
Non deve trasformare A, B, C, D o LEVEL_* in I-A, I-B o altri tier.

## Non fare in questa fase

Non usare ESCAT o evidence_level per modificare gate, score, bucket, ordine,
promozione, esclusione o ammissione delle claim. Non collegare il campo alle
API V3, al frontend o al dossier companion diagnostic.
