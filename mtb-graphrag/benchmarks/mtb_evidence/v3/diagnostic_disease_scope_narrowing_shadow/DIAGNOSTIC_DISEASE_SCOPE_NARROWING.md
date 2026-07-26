# Diagnostic disease-scope narrowing

Repository: `qualified_claim_repository/1.2`
Stato: `shadow_not_promoted`

La source closure richiede che i claim di `evidence:1846` e `evidence:1847`
descrivano **Intrahepatic Cholangiocarcinoma**, non il colangiocarcinoma
generico. I due claim 1.1 restano leggibili nell'audit e sono sostituiti da ID
ricalcolati con `non_therapeutic_claim_id_formula/1.0`.

## Esito

- parent: 147
- claim terapeutici: 146
- claim diagnostici attivi: 2
- claim diagnostici ritirati: 2
- claim prognostici: 0
- claim attivi totali: 148
- parent senza claim: 3

Il 13,6% resta una prevalenza aggregata delle fusioni FGFR2 e non viene
attribuito né a BICC1 né ad AHCYL1. Non vengono affermati utilità clinica, test
diagnostico validato, prognosi, intervento o scelta terapeutica.

## Perimetro

La relazione iCCA/colangiocarcinoma non viene promossa ad alias o gerarchia
operativa. Il match resta strict: la query generica non è exact. I piani di link
e view hanno `executed = false`; corpus, adapter, repository, retriever, scoring
e QualifiedEvidenceView operative restano invariati.
