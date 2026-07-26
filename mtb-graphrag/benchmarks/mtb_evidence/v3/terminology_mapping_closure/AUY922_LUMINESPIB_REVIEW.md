# AUY922 / luminespib

## Esito

- decisione: `insufficient_authoritative_evidence`
- mapping scope: `none`
- canonical label: nessuna
- source literal preservato: `AUY922`
- confidence: insufficient
- recommendation: `require_external_review`
- reason codes: `INSUFFICIENT_AUTHORITATIVE_SOURCE`, `MAPPING_REMAINS_UNRESOLVED`, `SOURCE_LITERAL_PRESERVED`, `VOCABULARY_CONCEPT_ID_CONFLICT`
- gruppi interessati: `evidence:841`
- controllo di circolarita': FALLITO

## Perche' l'identita' non e' verificata

Qui la fonte di massima priorita' e' disponibile. Il full text nomina soltanto il codice di sviluppo e non dichiara alcuna equivalenza. Un'assenza in una fonte accessibile pesa piu' di un'assenza in una fonte che non si e' potuta aprire.

Il vocabolario farmacologico non colma il vuoto, lo documenta: il letterale usato dalla fonte risolve a un concept id, e il nome generico e' raggiunto solo da un letterale diverso, con prefisso di produttore. Trattare i due letterali come lo stesso termine sarebbe inferenza da somiglianza di stringa, che questa fase non ammette.

Il nome generico compare unicamente in file derivati dal grafo. Il controllo di circolarita' fallisce.

| evidence | fonte | tipo | livello | sostiene | da grafo | locator |
|---|---|---|---|---|---|---|
| EV-AUY922-01 | PMID:26698910 | full_text | 2 | no | no | full text, Case Report, frase sulla linea con inibitore HSP90 |
| EV-AUY922-02 | DGIdb:drug_claims | drug_vocabulary_table | 5 | no | no | drugs.tsv, righe con drug_claim_name AUY922 e NVP-AUY922 |
| EV-AUY922-03 | Graph:node_drug | graph_node_table | 5 | no | si | node_drug.csv, colonna drug_claim_name |

## Conseguenza

L'associazione resta `unresolved_association`, esattamente come prima della revisione. Nessun claim viene creato, nessun ID cambia, nessun conteggio si muove. La revisione ha prodotto una decisione, non un cambiamento.

La coppia va a una revisione esterna: la decisione dice che le prove **localmente disponibili** non bastano, non che l'equivalenza sia falsa.

## Limitazioni

- Revisione non indipendente: un solo revisore reale.
- Nessuna fonte ammissibile e' stata trovata localmente: la decisione non esclude che ne esista una fuori dal materiale disponibile.
