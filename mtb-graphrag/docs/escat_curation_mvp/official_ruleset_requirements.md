# Requisiti del rule set ufficiale

Prima di validare un assessment con tier serve un file locale e versionato
con framework `ESCAT`, versione, citazione bibliografica, DOI o PMID, sezione
o pagina, data di validit?, tier, subtier e requisiti. Ogni regola deve avere
`rule_id`, `framework_version`, fonte distinta dalle supporting sources,
`required_fields`, `required_conditions`, `exclusion_conditions`, eventuali
`alternative_conditions` e requisiti specifici del subtier.

La fonte locale `Mateo.pdf` ? ora formalizzata in
`ESCAT_2018_MATEO_RESEARCH_DRAFT_v1`. Il suo stato ? `RESEARCH_DRAFT`, non
`OFFICIAL_RULESET_AVAILABLE`: ? un artefatto tracciabile per revisione e non
una validazione clinica. Il validatore non pu? usare questo stato per rendere
CURATED un assessment con tier. La promozione richieder? revisione, versione
approvata e separazione esplicita della fonte della regola dalle supporting
sources.

`test_fixture_ruleset.json` ? esclusivamente tecnico, marcato
`TEST_FIXTURE_ONLY` e `NOT_AN_OFFICIAL_ESCAT_RULESET`; non ? una fonte ESCAT e
non pu? essere esportato come valutazione scientifica.
