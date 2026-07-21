# Audit del gold pilota MTB-Evidence contro lo snapshot Neo4j

- **Timestamp (UTC):** 2026-07-21T17:35:58.570517+00:00
- **Commit:** `c295e1d7753fb247a60456f8e69d2f4210d2e309`
- **Neo4j:** 2026.04.0 enterprise su `bolt://localhost:7687`, database `neo4j`
- **Fingerprint snapshot:** `ffc97bc7c660f19478c33d28d1599b70e442525f0fae34b512e5efbf0796a9ae`
- **Nodi / relazioni:** 43003 / 61185

Questo documento e' un audit del grafo. Non modifica il gold, non usa output del modello come ground truth e non formula raccomandazioni cliniche: constata quali record esistono nello snapshot e come si rapportano all'annotazione provvisoria.

## Sintesi

| Caso | Decisione | Claim piene | Parziali | Senza riscontro | Freeze blockers |
| --- | --- | --- | --- | --- | --- |
| `PILOT-K1-FGFR2-iCCA` | **AMEND** | 0 | 1 | 1 | 5 |
| `PILOT-A2-ALK-G1202R` | **AMEND** | 1 | 0 | 2 | 2 |
| `PILOT-C1-EGFR-L858R-CONTEXT` | **AMEND** | 2 | 0 | 1 | 3 |
| `PILOT-N1-RMI2-SNAPSHOT` | **KEEP** | 1 | 0 | 0 | 0 |

## PILOT-K1-FGFR2-iCCA

_Adulto con colangiocarcinoma intraepatico non resecabile o metastatico, fusione/riarrangiamento FGFR2, progressione dopo ≥1 linea sistemica, nessun precedente FGFR-inibitore._

### Che cosa e' stato trovato

- terapie: ['derazantinib', 'erdafitinib', 'infigratinib', 'pazopanib hydrochloride', 'pd173074', 'pemigatinib', 'ponatinib']
- PMID: ['160559', '18757403', '23658459', '23786770', '24122810', '24550739', '26324363', '26574622', '27179038', '27870574', '29182496', '30420614', '32203698', '32973082', '34358484', '35507888', '38710951']
- NCT: nessuno
- record di evidenza normalizzati: 28

### Che cosa manca

- terapie: ['futibatinib']
- PMID: ['36652354']
- NCT: ['NCT02052778', 'NCT02924376']

### Che cosa e' presente in piu'

- terapie: ['derazantinib', 'erdafitinib', 'infigratinib', 'pazopanib hydrochloride', 'pd173074', 'ponatinib']
- PMID: ['160559', '18757403', '23658459', '23786770', '24122810', '24550739', '26324363', '26574622', '27179038', '27870574', '29182496', '30420614', '32973082', '34358484', '35507888', '38710951']

### Qualificatori

- confrontati sul grafo: 8
- assenti o non confrontabili: 4
- non modellati dallo schema: ['ecog', 'line', 'prior_therapy', 'resection_status', 'setting', 'stage']

### Conflitti

- `K1-C1 / disease: gold 'intrahepatic cholangiocarcinoma' vs grafo 'cholangiolocellular carcinoma'`

### Problemi di schema

- `nessuno degli NCT attesi e' presente come nodo ClinicalTrial`
- `citazioni con PMID implausibilmente corti: ['160559']; probabile difetto di ingestione nel campo citation_id, da verificare prima di usarli come fonte`
- `13 record usano una denominazione di malattia meno specifica di 'intrahepatic cholangiocarcinoma' (es. colangiocarcinoma generico): non sono equivalenti e non vengono contati come corrispondenza`
- `linea di terapia, stadio ed esposizione precedente a FGFR-inibitori non sono modellati dallo schema: ricavabili solo per euristica testuale`

### Freeze blockers

- `PMID attesi assenti dallo snapshot: ['36652354']`
- `NCT attesi assenti dallo snapshot: ['NCT02052778', 'NCT02924376']`
- `terapie attese non raggiunte dal traversal: ['futibatinib']`
- `claim senza alcun record corrispondente: ['K1-C2']`
- `conflitti di qualificatore non risolti: ['disease']`

### Decisione proposta: AMEND

0 claim pienamente corrispondenti, 1 parziali, 1 senza riscontro; 5 freeze blocker da risolvere prima del congelamento.

## PILOT-A2-ALK-G1202R

_Paziente con NSCLC avanzato ALK-riarrangiato, progressione dopo ALK-TKI di seconda generazione, singola mutazione G1202R; nessuna seconda mutazione ALK riportata._

### Che cosa e' stato trovato

- terapie: ['alectinib hydrochloride', 'brigatinib', 'ceritinib', 'crizotinib', 'lorlatinib', 'neladalkib', 'tanespimycin']
- PMID: ['22277784', '24675041', '24736079', '25727400', '26698910', '27130468', '27432227', '29373100', '29376144', '29650534', '29935304', '30892989', '31358542', '31585938', '32600123', '39269178']
- NCT: nessuno
- record di evidenza normalizzati: 13

### Che cosa manca

- terapie: nessuna
- PMID: nessuno
- NCT: ['NCT01970865']

### Che cosa e' presente in piu'

- terapie: ['alectinib hydrochloride', 'brigatinib', 'ceritinib', 'crizotinib', 'neladalkib', 'tanespimycin']
- PMID: ['22277784', '24675041', '24736079', '25727400', '26698910', '27130468', '29373100', '29376144', '29935304', '31358542', '31585938', '32600123', '39269178']

### Qualificatori

- confrontati sul grafo: 12
- assenti o non confrontabili: 6
- non modellati dallo schema: ['ecog', 'line', 'prior_therapy', 'resection_status', 'setting', 'stage']

### Conflitti

- _nessuno_

### Problemi di schema

- `nessuno dei PMID attesi e' presente come nodo Publication`
- `nessuno degli NCT attesi e' presente come nodo ClinicalTrial`
- `1 record riguardano mutazioni composte: conservati in un bucket separato e non applicati al caso a mutazione singola`
- `l'esposizione precedente a un ALK-TKI di seconda generazione non e' modellata dallo schema: ricavabile solo per euristica testuale`

### Freeze blockers

- `NCT attesi assenti dallo snapshot: ['NCT01970865']`
- `claim senza alcun record corrispondente: ['A2-C1', 'A2-C3']`

### Decisione proposta: AMEND

1 claim pienamente corrispondenti, 0 parziali, 2 senza riscontro; 2 freeze blocker da risolvere prima del congelamento.

## PILOT-C1-EGFR-L858R-CONTEXT

_Paziente con adenocarcinoma polmonare avanzato/metastatico EGFR L858R, non precedentemente trattato, prima linea; nessuna T790M e nessun contesto di resezione._

### Che cosa e' stato trovato

- terapie: ['afatinib', 'amivantamab', 'canertinib', 'carboplatin', 'cetuximab', 'crizotinib', 'dacomitinib', 'erlotinib', 'gefitinib', 'lapatinib', 'lazertinib', 'multikinase inhibitor aee788', 'neratinib maleate', 'osimertinib', 'ramucirumab']
- PMID: ['15118125', '15329413', '16818618', '17177598', '17877814', '18089823', '18408761', '18509184', '19147750', '20038723', '20942962', '21132006', '21531810', '22235099', '22285168', '22370314', '22452895', '23816960', '23982599', '24263064', '24353160', '24439929', '24457318', '24662454', '24736073', '24755888', '24868098', '24893891', '25923549', '25939061', '26181354', '26269204', '26515464', '26720284', '26729184', '26768165', '27022112', '27032107', '27102076', '27612423', '27959700', '28202511', '28274957', '28874593', '28958502', '31208370', '31591063', '32955177', '35245845', '35399574', '37879444', '37937763', '38074875', '38525318', '38942080']
- NCT: ['NCT02511106']
- record di evidenza normalizzati: 81

### Che cosa manca

- terapie: nessuna
- PMID: ['29151359']
- NCT: ['NCT02151981', 'NCT02296125']

### Che cosa e' presente in piu'

- terapie: ['afatinib', 'amivantamab', 'canertinib', 'carboplatin', 'cetuximab', 'crizotinib', 'dacomitinib', 'erlotinib', 'gefitinib', 'lapatinib', 'lazertinib', 'multikinase inhibitor aee788', 'neratinib maleate', 'ramucirumab']
- PMID: ['15118125', '15329413', '16818618', '17177598', '17877814', '18089823', '18408761', '18509184', '19147750', '20038723', '20942962', '21132006', '21531810', '22235099', '22285168', '22370314', '22452895', '23816960', '23982599', '24263064', '24353160', '24439929', '24457318', '24662454', '24736073', '24755888', '24868098', '24893891', '25923549', '25939061', '26181354', '26269204', '26515464', '26720284', '26729184', '26768165', '27022112', '27032107', '27102076', '27612423', '28202511', '28274957', '28874593', '28958502', '31208370', '31591063', '35245845', '35399574', '37879444', '37937763', '38074875', '38525318', '38942080']

### Qualificatori

- confrontati sul grafo: 12
- assenti o non confrontabili: 6
- non modellati dallo schema: ['ecog', 'line', 'prior_therapy', 'resection_status', 'setting', 'stage']

### Conflitti

- _nessuno_

### Problemi di schema

- `3 record in setting adiuvante/resecato: conservati e classificati, non eliminati`
- `22 record post-progressione T790M: conservati e classificati, non eliminati`

### Freeze blockers

- `PMID attesi assenti dallo snapshot: ['29151359']`
- `NCT attesi assenti dallo snapshot: ['NCT02151981', 'NCT02296125']`
- `claim senza alcun record corrispondente: ['C1-C1']`

### Decisione proposta: AMEND

2 claim pienamente corrispondenti, 0 parziali, 1 senza riscontro; 3 freeze blocker da risolvere prima del congelamento.

## PILOT-N1-RMI2-SNAPSHOT

_Domanda gene→farmaco sullo snapshot congelato del progetto._

### Che cosa e' stato trovato

- terapie: nessuna
- PMID: nessuno
- NCT: nessuno
- record di evidenza normalizzati: 0

### Che cosa manca

- terapie: nessuna
- PMID: nessuno
- NCT: nessuno

### Che cosa e' presente in piu'

- terapie: nessuna
- PMID: nessuno

### Qualificatori

- confrontati sul grafo: 0
- assenti o non confrontabili: 0
- non modellati dallo schema: ['ecog', 'line', 'prior_therapy', 'resection_status', 'setting', 'stage']

### Conflitti

- _nessuno_

### Problemi di schema

- `il nodo Gene RMI2 esiste ma non ha alcuna relazione: l'astensione e' un negativo genuino del traversal`
- `il nodo RMI2 porta le categorie ['CLINICALLY ACTIONABLE', 'DNA REPAIR'] pur non avendo alcun percorso terapeutico: la proprieta' non implica evidenza clinica ed e' una trappola per qualunque euristica che la usasse come segnale`

### Freeze blockers

- _nessuno_

### Decisione proposta: KEEP

Nessun freeze blocker: gold e grafo concordano su tutte le dimensioni.

## Limiti dell'audit

- Il fingerprint e' derivato da statistiche aggregate, non e' un hash del contenuto: due grafi con le stesse statistiche collidono.
- Setting, linea di terapia, stadio ed esposizione precedente non sono modellati dallo schema. Le classificazioni corrispondenti sono euristiche testuali su `evidence_statement` e vanno lette come indizi, non come dati.
- L'assenza di un PMID come nodo `Publication` non implica che la pubblicazione non esista: implica che non e' recuperabile da questo snapshot.
- Nessuna decisione qui e' definitiva: tutte richiedono la seconda revisione indipendente prevista dalle note di annotazione.
