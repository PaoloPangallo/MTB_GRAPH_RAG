# V3 PMID document-support pilot

Pilota read-only eseguito sul branch `research/v3-pmid-document-pilot`, a
partire da `e70f81b`. Usa soltanto record già presenti nel repository:

- claim strutturate e provenance inventory della `qualified_claim_repository/1.4`;
- metadati locali in `v3/qualification_corpus/source_metadata_cache.jsonl`;
- abstract locali in `v3/priority_curation/source_abstract_cache.jsonl`;
- locator/span locali e source-review già esistenti.

Non sono state interrogate fonti live. Non è stato usato un LLM: i record
locali espongono già identificatori, metadati e testo reale sufficienti per un
confronto deterministico. I locator `ABSTRACT` indicano che il record locale
contiene l'abstract ma non un offset claim-level verificato.

## Perimetro

- Gruppo A: 12 claim `CLAIM_VERIFIED_LOCATOR`, con sensibilità, resistenza,
  aggregate, preclinical, diagnostic, EGFR, ALK e FGFR.
- Gruppo B: 4 claim `PARENT_PUBLICATION_AVAILABLE`. Il PMID resta una
  pubblicazione candidata e non diventa una fonte claim-level.

Il pilota distingue sempre:

1. pubblicazione identificata;
2. testo locale disponibile;
3. passaggio candidato;
4. supporto effettivo degli elementi della claim;
5. applicabilità al contesto.

## Interpretazione

Il CSV principale usa gli stati richiesti: `EXACT`, `COMPATIBLE`, `PARTIAL`,
`MISSING`, `CONTRADICTED`, `NOT_APPLICABLE` per i singoli campi e gli stati
documentali finali richiesti. `DIRECT_SUPPORT` nel Gruppo B significa che il
testo candidato contiene gli elementi della claim; non significa che il
collegamento parent -> claim sia stato verificato.

## File

- `pilot_claim_selection.md`: selezione e motivazione dei 16 casi.
- `document_availability.csv`: metadati, abstract e livelli di disponibilità.
- `claim_document_alignment.csv`: confronto strutturato principale.
- `claim_support_report.md`: evidenza per claim e passaggi esatti.
- `parent_publication_candidates.md`: candidati parent-level e regole di non-promozione.
- `unsupported_or_partial_claims.md`: parzialità, limiti e categorie senza casi nel campione.
- `recommended_document_model.md`: modello proposto senza integrazione runtime.
- `pmid_pilot_summary.json`: conteggi e invarianti macchina.

Gli output sono evidenza di ricerca documentale e non aggiornano provenance,
gate, scoring, bucket, claim, Knowledge Graph o runtime V3.
