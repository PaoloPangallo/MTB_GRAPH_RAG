# 01 — Decisione architetturale

## Il principio

```
CANONICAL STRUCTURED DOSSIER      ← sorgente di verità, invariata
        ↓  build_narrator_input()   deterministica, nessun LLM
NARRATOR INPUT PROJECTION
        ↓  gemma4:cloud, tool call forzata
NARRATIVE DRAFT
        ↓  verify_narrative()       deterministica, nessun LLM
   PASS → VERIFIED NARRATIVE        mostrata
   FAIL → STRUCTURED DOSSIER FALLBACK
```

**`NARRATIVE ≠ CANONICAL EVIDENCE STATE`.** La narrativa è una *presentation
view*; il dossier strutturato resta la *canonical view*.

## Perché il verifier è deterministico

Un secondo modello che giudica il primo sposterebbe il problema, non lo
risolverebbe: servirebbe un terzo giudice. Un verifier deterministico è invece
ispezionabile — ogni pattern del lexicon può essere mostrato a un revisore,
discusso e cambiato — e riproducibile: stessa coppia (dossier, narrativa) →
stesso esito, verificato per impronta.

Il costo è dichiarato: il verifier controlla la **fedeltà**, non la correttezza
clinica. La correttezza clinica non è verificabile deterministicamente, e
fingere il contrario sarebbe peggio che non provarci.

## Perché il prompt non è il meccanismo di sicurezza

Il prompt rende *probabile* una narrativa fedele. La sicurezza viene da tre
proprietà indipendenti dal testo del prompt:

1. **La projection** — il modello non può citare ciò che non riceve. Le quote
   rigettate non entrano nel `NarratorInput`.
2. **Lo schema chiuso** — quattro proprietà, `additionalProperties: false`, e il
   trasporto rifiuta le chiavi extra. È la stessa proprietà che rende
   `IMPOSSIBLE_BY_CONSTRUCTION` l'impossibilità per l'enricher di emettere un
   PMID.
3. **Il verifier** — sei famiglie di controllo prima che la narrativa sia
   visibile.

## Perché il Narrator non riapre RQ3

È il terzo uso dell'LLM, ma il primo che opera **dopo** che lo stato canonico è
già stato deciso. Non partecipa alla costruzione dell'evidenza: la descrive.

Verificato in modo diretto: il dossier canonico prodotto con un narratore
**ostile** — che tenta di riscrivere status, bucket e farmaco — è byte-identico
a quello prodotto senza narratore.

## Cosa questa fase NON ha toccato

GraphCandidateAssertion v3, OncoKB, RQ5, retrieval, CaseContext Parser,
eligibility, Knowledge Graph, DocumentResolver, generazione di SourceUnit, Paper
Context Enricher, quote validation, support mask, gate canonico, calcolo dello
status.

Il runtime resta su `graph_candidate_repository/2.0`.
