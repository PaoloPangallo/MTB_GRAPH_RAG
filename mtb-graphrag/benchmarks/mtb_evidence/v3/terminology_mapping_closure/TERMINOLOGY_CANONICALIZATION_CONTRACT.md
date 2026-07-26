# Contratto di canonicalizzazione degli interventi

Versione: `intervention-canonicalization-contract/1.0`

## Invarianti

- Un alias pending non entra negli exact match.
- Un mapping verificato non cancella il source literal.
- Un development code non e' un farmaco diverso quando l'identita' e' verificata, ma resta registrato come letterale della fonte.
- Forme realmente differenti, come un sale, non vengono fuse senza un qualificatore esplicito.
- La canonicalizzazione e' deterministica e non consulta il grafo.
- Il mapping non produce supporto documentale dove non esiste.
- Mapping globale e mapping source-local restano distinti.

## Voci

### `AUY922`

- canonical label: nessuna
- source literals: `AUY922`
- development codes: nessuno
- verified aliases: nessuno
- relazioni di forma o sale: nessuna
- mapping scope: `none`
- mapping status: `unresolved_pending_external_review`
- review status: `first_review_complete`
- propagation policy: `prototype_only`
- effective from: non applicabile
- effective to: non applicabile

### `TIV-INFIGRATINIB`

- canonical label: `infigratinib`
- source literals: `BGJ398`
- development codes: `BGJ398`
- verified aliases: `infigratinib`
- relazioni di forma o sale: infigratinib fosfato (ncit:C175088) e' una forma salificata distinta dalla moiety infigratinib (rxcui:2550729) e non viene fusa con essa
- mapping scope: `global`
- mapping status: `verified_pending_second_review`
- review status: `first_review_complete`
- propagation policy: `prototype_only`
- effective from: 2021
- effective to: non applicabile

## Determinismo

La canonicalizzazione e' una funzione totale dei campi qui registrati: stesso input, stessa etichetta, stesso ID. Non consulta il grafo, non misura somiglianze e non dipende dall'ordine in cui le voci vengono presentate.
