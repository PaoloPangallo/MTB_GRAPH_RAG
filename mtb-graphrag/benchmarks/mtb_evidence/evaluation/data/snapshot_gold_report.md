# Clinical gold e snapshot gold

- **Generato:** 2026-07-21T19:52:00.987143+00:00
- **Fingerprint snapshot:** `ffc97bc7c660f19478c33d28d1599b70e442525f0fae34b512e5efbf0796a9ae`
- **Casi:** 4
- **Hash del gold pilota di input:** `30e64dc5f3dffde3d1d43c316f6bc75f1afafab41567fa8657214a10fa16c667`

Il clinical gold descrive cio' che dovrebbe essere ricostruito secondo fonti primarie e annotazione umana. Lo snapshot gold descrive cio' che di quella annotazione e' presente e raggiungibile in questo grafo. Sono oggetti distinti: una fonte clinica valida ma assente dal grafo abbassa la copertura del Knowledge Graph, non il recall del retriever.

## Stati di presenza per tipo di elemento

| Tipo | absent | ambiguous | partially_present | present |
| --- | --- | --- | --- | --- |
| claim | 4 | 1 | 0 | 4 |
| nct_id | 5 | 0 | 0 | 1 |
| pmid | 2 | 0 | 3 | 3 |
| qualifier | 24 | 0 | 0 | 0 |
| therapy | 0 | 0 | 1 | 3 |

## Per caso

### PILOT-K1-FGFR2-iCCA

- elementi clinici mappati: 14
- recuperabili dallo snapshot: 2
- terapie recuperabili: ['pemigatinib']
- PMID recuperabili: ['32203698']
- NCT recuperabili: nessuno
- astensione attesa: no

  - nessuno degli NCT attesi e' presente come nodo ClinicalTrial
  - citazioni con PMID implausibilmente corti: ['160559']; probabile difetto di ingestione nel campo citation_id, da verificare prima di usarli come fonte
  - 13 record usano una denominazione di malattia meno specifica di 'intrahepatic cholangiocarcinoma' (es. colangiocarcinoma generico): non sono equivalenti e non vengono contati come corrispondenza
  - linea di terapia, stadio ed esposizione precedente a FGFR-inibitori non sono modellati dallo schema: ricavabili solo per euristica testuale
  - dimensioni non verificabili sullo snapshot per le claim corrispondenti: ['line', 'setting']. La corrispondenza e' strutturale, non una conferma di applicabilita': serve il giudizio del secondo revisore.

### PILOT-A2-ALK-G1202R

- elementi clinici mappati: 14
- recuperabili dallo snapshot: 5
- terapie recuperabili: ['lorlatinib']
- PMID recuperabili: ['27432227', '29650534', '30892989']
- NCT recuperabili: nessuno
- astensione attesa: no

  - nessuno dei PMID attesi e' presente come nodo Publication
  - nessuno degli NCT attesi e' presente come nodo ClinicalTrial
  - 1 record riguardano mutazioni composte: conservati in un bucket separato e non applicati al caso a mutazione singola
  - l'esposizione precedente a un ALK-TKI di seconda generazione non e' modellata dallo schema: ricavabile solo per euristica testuale
  - dimensioni non verificabili sullo snapshot per le claim corrispondenti: ['line', 'setting']. La corrispondenza e' strutturale, non una conferma di applicabilita': serve il giudizio del secondo revisore.

### PILOT-C1-EGFR-L858R-CONTEXT

- elementi clinici mappati: 16
- recuperabili dallo snapshot: 6
- terapie recuperabili: ['osimertinib']
- PMID recuperabili: ['27959700', '32955177']
- NCT recuperabili: ['NCT02511106']
- astensione attesa: no

  - 3 record in setting adiuvante/resecato: conservati e classificati, non eliminati
  - 22 record post-progressione T790M: conservati e classificati, non eliminati
  - dimensioni non verificabili sullo snapshot per le claim corrispondenti: ['line', 'setting']. La corrispondenza e' strutturale, non una conferma di applicabilita': serve il giudizio del secondo revisore.

### PILOT-N1-RMI2-SNAPSHOT

- elementi clinici mappati: 7
- recuperabili dallo snapshot: 1
- terapie recuperabili: nessuna
- PMID recuperabili: nessuno
- NCT recuperabili: nessuno
- astensione attesa: si

  - prova negativa archiviata: percorsi terapeutici = 0, valida = True
  - il nodo Gene RMI2 esiste ma non ha alcuna relazione: l'astensione e' un negativo genuino del traversal
  - il nodo RMI2 porta le categorie ['CLINICALLY ACTIONABLE', 'DNA REPAIR'] pur non avendo alcun percorso terapeutico: la proprieta' non implica evidenza clinica ed e' una trappola per qualunque euristica che la usasse come segnale

## Integrita'

- clinical gold non modificato rispetto al pilota: si
- emendamenti proposti NON applicati: 9 righe lette e ignorate deliberatamente
