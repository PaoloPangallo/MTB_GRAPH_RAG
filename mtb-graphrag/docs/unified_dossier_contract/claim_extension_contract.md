# Claim extension contract

Le estensioni sono indicizzate esclusivamente dal `claim_id` presente in
`core_result.claims`.

## Provenance

Sono separati `claim_level_sources`, `parent_level_publications`, `source_unit`,
`locators`, `provenance_status`, `first_missing_link` e `ambiguities`.
Una pubblicazione parent disponibile non viene promossa a fonte claim-level.

## Document support

Un modulo non eseguito produce `status=NOT_ASSESSED`. `NO_SUPPORT_FOUND` è
ammesso solo quando restituito esplicitamente dal modulo.

## Clinical actionability

Il campo riusa l’adapter ESCAT shadow e mantiene gli stati reali del record.
La fixture `TEST_FIXTURE_ONLY` non entra nelle preview reali.
