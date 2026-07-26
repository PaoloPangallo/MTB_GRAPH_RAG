# BGJ398 / infigratinib

## Esito

- decisione: `verified_development_code_for_same_intervention`
- mapping scope: `global`
- canonical label: `infigratinib`
- source literal preservato: `BGJ398`
- confidence: high
- recommendation: `approve_for_shadow_update`
- reason codes: `AGGREGATE_RESULT_REMAINS_NON_SEPARABLE`, `DEVELOPMENT_CODE_VERIFIED`, `FORMULATION_RELATION_REQUIRES_QUALIFIER`, `GLOBAL_DRUG_IDENTITY_CONFIRMED`, `SOURCE_LITERAL_PRESERVED`
- gruppi interessati: `evidence:1851`, `evidence:1853`
- controllo di circolarita': superato

## Perche' l'identita' e' verificata

Il corpus locale contiene un record bibliografico peer-reviewed che appone il codice di sviluppo al nome generico nel proprio titolo, nella stessa malattia e sullo stesso biomarcatore del gruppo in revisione. Il vocabolario farmacologico fa convergere il codice su un unico concept id, asserito da cinque curatori distinti.

Il controllo che rende la prova utilizzabile e' negativo: il codice **non compare** tra i nodi farmaco del grafo. La relazione non puo' quindi essere stata dedotta da cio' che il grafo afferma di se stesso, che e' la circolarita' rifiutata dall'adjudication.

| evidence | fonte | tipo | livello | sostiene | da grafo | locator |
|---|---|---|---|---|---|---|
| EV-BGJ398-01 | PMID:34358484 | indexed_bibliographic_record | 8 | si | no | record bibliografico, campo title, apertura del titolo |
| EV-BGJ398-02 | PMID:34358484 | indexed_abstract | 7 | no | no | abstract, sezione BACKGROUND |
| EV-BGJ398-03 | PMID:29182496 | indexed_bibliographic_record | 8 | no | no | record bibliografico, campo title |
| EV-BGJ398-04 | PMID:27870574 | indexed_bibliographic_record | 8 | no | no | record bibliografico, campo title |
| EV-BGJ398-05 | DGIdb:drug_claims | drug_vocabulary_table | 5 | si | no | drugs.tsv, righe con drug_claim_name BGJ398 |
| EV-BGJ398-06 | DGIdb:drug_claims | drug_vocabulary_table | 5 | no | no | drugs.tsv, righe con drug_claim_name Infigratinib Phosphate |
| EV-BGJ398-07 | Graph:node_drug | graph_node_table | 5 | no | si | node_drug.csv, colonna drug_claim_name |

## Perche' il claim resta aggregato

La fonte enuncia la soppressione della trasformazione per i due inibitori insieme. Verificare il nome di un membro non rende separabile il risultato: i due claim restano `aggregate_intervention_claim` con `permits_member_specific_claims` falso, e nessun claim atomico viene autorizzato.

Questa e' la distinzione centrale della fase. Un mapping verificato agisce sulla terminologia, non sul supporto documentale.

## Effetto simulato sugli ID

| gruppo | claim ID corrente | ID potenziale | tipo dopo |
|---|---|---|---|
| evidence:1851 | `CLM-a7c903cf8d423f015e29` | `CLM-90e863f00f134fc3cd3d` | aggregate_intervention_claim |
| evidence:1853 | `CLM-aae818bbc8ec735a255d` | `CLM-5071bb2d8657ac0fbed0` | aggregate_intervention_claim |

La formula di identita' include la rappresentazione canonica dell'intervento, quindi l'ID cambia davvero. Nessuna sostituzione viene effettuata: la simulazione registra retirement, replacement e lineage `old -> new -> terminology_decision_id` e si ferma.

## Limitazioni

- Revisione non indipendente: un solo revisore reale.
- Il sale infigratinib fosfato ha concept id proprio e non viene fuso nella moiety.
- L'identificazione proviene da una pubblicazione successiva allo studio del gruppo: vale come identita' di sostanza, non come prova che la fonte del 2013 intendesse gia' il nome generico.
