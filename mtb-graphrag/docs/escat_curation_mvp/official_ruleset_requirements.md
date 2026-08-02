# Requisiti del rule set ufficiale

Prima di validare un assessment con tier serve un file locale e versionato
con framework `ESCAT`, versione, citazione bibliografica, DOI o PMID, sezione
o pagina, data di validit?, tier, subtier e requisiti. Ogni regola deve avere
`rule_id`, `framework_version`, fonte distinta dalle supporting sources,
`required_fields`, `required_conditions`, `exclusion_conditions`, eventuali
`alternative_conditions` e requisiti specifici del subtier.

Il repository corrente non contiene questo asset in forma verificabile. La
citazione bibliografica presente in `docs/V3_POSITIONING.md` non ? importata
come regola. Il modello ? pronto a riceverlo in futuro, ma il validatore
mantiene `OFFICIAL_RULESET_NOT_AVAILABLE` fino a quel momento.

`test_fixture_ruleset.json` ? esclusivamente tecnico, marcato
`TEST_FIXTURE_ONLY` e `NOT_AN_OFFICIAL_ESCAT_RULESET`; non ? una fonte ESCAT e
non pu? essere esportato come valutazione scientifica.
