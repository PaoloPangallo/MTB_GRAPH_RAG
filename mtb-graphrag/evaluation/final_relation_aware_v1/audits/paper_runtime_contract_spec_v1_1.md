# PAPER Runtime Contract v1.1

`STATUS=FROZEN_RUNTIME_CONTRACT`

This contract supersedes v1 for future runtime work. It does not alter or reinterpret prior artifacts.

## Canonical observation

`CANONICAL_OBSERVATION=observed_relation`

```text
observed_relation
├── disease
├── subjects[]: {type, surface_value, canonical_value?, linked_gene?}
├── intervention: {surface_value, canonical_value?} | null
├── observed_stance
├── effect_direction
├── relation_scope
└── evidence_context: {subject_level, claim_type}
```

`subjects[].type` is one of `GENE`, `ALTERATION`, `BIOMARKER`, `OTHER`.
`surface_value` is the Reader's source expression. `canonical_value` is produced only by the Canonical Normalizer. `linked_gene` may associate an alteration with its gene; it does not create a graph.

Existing flat fields are `LEGACY_COMPATIBILITY/TELEMETRY_ONLY`. They are derived from the canonical observation where compatibility is needed and must not independently override it.

`FLAT_FIELDS_MUST_NOT_OVERRIDE_CANONICAL_RELATION`

## Component contracts

| Component | Purpose | May do | Must not do | Conservative failure |
|---|---|---|---|---|
| Reader | extract the proposition stated in one supplied SourceUnit | semantic extraction of disease, participants, intervention, stance, effect, scope, observation level, claim type | decide support state or GCA sufficiency; add external facts; remove necessary participants to fit Candidate | structured ABSTAIN with reason |
| Canonical Normalizer | preserve representation while standardizing it | Unicode NFC, case/whitespace/line breaks, safe punctuation/hyphenation, versioned variant syntax and authorized aliases, enum mapping | add clinical facts, infer relations, collapse broader to narrower entities, create aliases | unresolved canonical value |
| Validator | establish structural validity and SourceUnit provenance | transport/schema/enum checks, SourceUnit/document authorization, quote provenance, weak consistency after normalization | prove clinical meaning, GCA sufficiency, predictive/prognostic claim, final support, keyword proof of subject level/claim type | reject before verifier |
| Verifier | compare expected Candidate relation with accepted normalized observation | identity/specificity, stance/effect, composition, evidence-context sufficiency, contradiction, final state | read raw text, normalize unversioned aliases, replace Reader extraction | PARTIAL/UNVERIFIABLE as policy requires |

`NORMALIZER_MUST_NOT_ADD_SEMANTIC_FACTS`

## Independent semantic axes

| Axis | Values / meaning | Primary source | Comparison owner |
|---|---|---|---|
| Expected stance | Candidate evidence stance | Candidate metadata | Verifier via direction primitive |
| Observed stance | SUPPORTS, DOES_NOT_SUPPORT, UNKNOWN, NOT_APPLICABLE | Reader | Verifier |
| Expected effect | resistance/sensitivity/etc. required by Candidate | Candidate predicate/significance | Verifier |
| Observed effect | source-reported clinical effect | Reader | Verifier |
| Claim type | assertion form | Reader | Verifier |
| Subject level | observational level | Reader, with normalizer cue signal | Verifier |
| Composition | necessary participant structure | Reader | Verifier |
| Identity/specificity | relation of normalized entities | Candidate + normalized relation | Verifier |

`Supports + Resistance` is not a contradiction. Effect contradiction exists only when expected and observed clinical effects are incompatible. `direction_semantics.py` is the canonical direction primitive; legacy fallbacks are non-authoritative for final support.

## Subject level and claim type

Subject level values are `INDIVIDUAL`, `COHORT`, `POPULATION`, `CELL_MODEL`, `ANIMAL_MODEL`, `OTHER`, `UNKNOWN`.

The Reader proposes the value. The normalizer may expose transparent cues as an auditable signal. Validator outcomes for the cue check are only `CONSISTENT`, `INCONSISTENT`, `UNRESOLVED`; `UNRESOLVED` must not reject an otherwise valid enrichment. Only gross demonstrable incompatibility may be `INCONSISTENT`.

Claim type values are `OBSERVED_RESPONSE`, `PREDICTIVE_ASSOCIATION`, `PROGNOSTIC_ASSOCIATION`, `DIAGNOSTIC_ASSOCIATION`, `FUNCTIONAL_EFFECT`, `MECHANISTIC_EFFECT`, `ASSOCIATION`, `OTHER`, `UNKNOWN`. Reader extracts; normalizer canonicalizes enum; validator checks structure only; verifier applies evidence-context sufficiency.

## Evidence model

`claim_type`, `subject_level`, `effect_direction`, and `observed_stance` are canonical independent axes. Existing `observed_evidence_type` and `observed_relation.evidence_scope` are non-authoritative legacy/telemetry fields until a separately approved migration confirms an independent semantic role.

The evidence-context policy is a separately versioned deterministic policy. It must be explicit, tested, and the only owner of compatibility. At minimum, `PREDICTIVE` expectation plus `INDIVIDUAL + OBSERVED_RESPONSE` cannot automatically be FULL. Unknown context cannot add support.

## Identity, normalization and provenance

Entity comparison categories are `IDENTICAL`, `CANONICAL_ALIAS`, `SOURCE_BROADER`, `SOURCE_NARROWER`, `DIFFERENT`, `UNKNOWN`.

Canonical normalizer owns representation-safe changes. Examples: `PIK3CA) E545K` and `PIK3CA E545K` normalize to identical; HER2/ERBB2 is an alias only through an authorized versioned resource; BRCA1 and BRCA1/2 are not identical; F877L/F876L are different. Bidirectional substring containment is forbidden as an authoritative identity primitive.

Quote provenance remains strict: quote must derive from an authorized SourceUnit. Only Unicode, whitespace, and line-break representation normalization may be used for provenance matching. Entity punctuation handling belongs to entity normalization, not quote permissiveness.

## Composition

Reader reports all necessary participants and one of `SINGLE`, `COEXPRESSION`, `COMBINATION`, `CONDITIONAL`, `UNKNOWN`. Additional necessary participants prevent a FULL match to a single-participant Candidate. A mere contextual mention is not a necessary participant; that distinction belongs to Reader extraction.

## Abstain and error contract

For `ABSTAIN`, `abstain_reason` is mandatory: `NO_RELEVANT_EVIDENCE`, `INSUFFICIENT_RELATION`, `MISSING_REQUIRED_ANCHOR`, `AMBIGUOUS_EVIDENCE`, `COMPOSITION_UNCLEAR`, `EVIDENCE_CONTEXT_UNCLEAR`, `OTHER`. `OTHER` requires a short note. It is telemetry, not support evidence.

Errors remain distinct: `TRANSPORT_ERROR`, `SCHEMA_ERROR`, `PROVENANCE_ERROR`, `VALIDATION_REJECTION`, `READER_ABSTAIN`, `VERIFIER_UNVERIFIABLE`, `VERIFIER_CONTRADICTORY`.

## Normative invariants

1. No unauthorized SourceUnit contributes evidence.
2. No invalid quote reaches verifier.
3. Reader never assigns final support.
4. Normalizer never introduces semantic facts.
5. Validator never decides Candidate/GCA sufficiency.
6. Verifier never rereads free text.
7. Every semantic axis has one canonical owner.
8. UNKNOWN never implies confirmation.
9. FULL_SUPPORT has exactly one decision point.
10. No support rule depends on case ID, GCA ID, PMID, or prior outcome.
11. Canonical relation overrides flat legacy fields.
12. Aliases are explicit, versioned, and auditable.
13. Unresolved weak consistency does not reject.
14. Calibration/development artifacts cannot be claimed as untouched hold-out.

## Versioning

Every run records independent versions for Reader prompt/schema, canonical normalizer, validator contract, verifier policy, alias table, evidence-context policy, runtime commit, SourceUnit manifest, and hold-out manifest.

## Hold-out policy

The 200 naturalistic pairs and the 57 rejection audit are calibration/development data. A final hold-out must be GCA-disjoint and document-disjoint, selected from metadata only with a deterministic seed, sealed before any source reading or Reader invocation, and never tuned after opening.

## Implementation gate

`UNRESOLVED_ARCHITECTURAL_BLOCKERS=0`

The only remaining unresolved questions are evaluation-resource questions: authorized alias resource selection and availability of a disjoint local PAPER corpus large enough for the proposed hold-out. They do not alter ownership or final-support semantics, but they block a valid hold-out until resolved.
