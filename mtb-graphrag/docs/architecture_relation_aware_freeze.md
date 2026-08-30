# Relation-aware MTB Evidence Architecture — Frozen Specification

## Status

Architecture status: FROZEN

Branch: `feature/relation-aware-core`

Base audited commit: `39b3e2eca5147fa8eddfd410c9244f7dec574102`

This freeze incorporates the bounded compatibility fix `FULL_SUPPORT ->
STRONG_SUPPORT` exclusively at the legacy-gate boundary. The relation-aware
support object is not mutated, and the relation-aware dossier continues to
carry `FULL_SUPPORT`.

## Core pipeline

Clinical text
→ Gemma CaseContext Parser
→ deterministic CaseContext validation
→ Knowledge Graph GCA retrieval
→ deterministic relation-family classification

The resulting relation families are `PAPER_EVIDENCE`, `CLINICAL_TRIAL`, and
`KG_ONLY`. A candidate carrying both a PMID and an NCT is
`INVALID_PROVENANCE` and is not processed as evidence.

## Paper branch

PMID
→ PubMed/PMC resolution
→ canonical document
→ SourceUnit materialization
→ deterministic selector
→ Gemma Paper Reader
→ `QUOTE` or `ABSTAIN`
→ literal quote validation
→ deterministic relation support
→ `paper_evidence`

PMC full text is preferred when available; PubMed abstract is the explicit
fallback. The pipeline does not search for an alternative paper when the
provenance document is unavailable.

## Trial branch

NCT
→ ClinicalTrials.gov API v2
→ structured trial record
→ `clinical_trials`

The trial branch uses no paper SourceUnit, no Paper Reader, and no paper quote
validator. It does not perform patient eligibility assessment and does not
make an efficacy claim.

## KG-only branch

No PMID and no NCT
→ preserve graph relation and graph provenance
→ `kg_only_relations`

This branch performs no document resolution, SourceUnit materialization,
Reader call, or quote validation. It does not create an invented source.

## Relation-aware support model

The deterministic relation-aware support vocabulary is:

- `FULL_SUPPORT`
- `PARTIAL_SUPPORT`
- `NO_SUPPORT`
- `UNVERIFIABLE`
- `CONTRADICTORY`

`FULL_SUPPORT` remains unchanged in the relation-aware dossier. The mapping
`FULL_SUPPORT -> STRONG_SUPPORT` exists exclusively as a compatibility adapter
for the legacy gate. It operates on a temporary view and does not alter the
relation-aware support object or dossier output. `PARTIAL_SUPPORT`,
`NO_SUPPORT`, `UNVERIFIABLE`, and `CONTRADICTORY` are not promoted.

## Canonical dossier

The canonical relation-aware dossier is built deterministically and contains
the top-level sections:

- `paper_evidence`
- `clinical_trials`
- `kg_only_relations`
- `limitations`
- `provenance_summary`

It does not require the Narrator, the Narrative Verifier, or the legacy gate.
Narrative generation, when configured, is a later presentation layer and the
structured dossier remains available as the fallback.

## LLM boundary

Core LLM role 1: Gemma CaseContext Parser.

Core LLM role 2: Gemma Paper Reader, only in the Paper branch and only over
already selected SourceUnits.

No other LLM is required to construct the canonical relation-aware dossier.

## Fail-closed behaviour

Insufficient CaseContext stops before retrieval and yields an explicit empty
report. No relevant GCA yields an explicit no-match report. Invalid provenance
is not processed as evidence. An unavailable paper, Reader `ABSTAIN`, or an
invalid quote cannot create document support. An unavailable trial remains an
unavailable structured trial record. None of these conditions generates
invented fallback evidence.

## Architecture invariants

1. KG candidates are not automatically evidence.
2. Provenance determines the processing branch.
3. Paper claims require literal validated source support.
4. Trial associations are not efficacy evidence.
5. KG-only relations never acquire invented document provenance.
6. LLMs do not assign the final deterministic support level.
7. Relation-aware support vocabulary is independent from legacy gate vocabulary.
8. The canonical dossier does not depend on narrative generation.
9. The three evidence families remain distinguishable in the final dossier.
10. Failure or unavailability must not increase evidential strength.

## Freeze statement

This document freezes the architecture used as the reference implementation
for the thesis.

Future changes that alter relation-family routing, Paper/Trial/KG-only
semantics, LLM authority boundaries, support-state semantics, provenance
rules, or dossier convergence must be treated as architecture changes and
require a new architecture version and explicit re-evaluation.

This is not a clinical validation claim and does not declare a validated
clinical decision-support system.
