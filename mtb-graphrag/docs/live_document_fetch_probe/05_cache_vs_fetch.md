# Cache contro fetch live

**VERIFIABLE RESEARCH PIPELINE — NOT CLINICALLY VALIDATED.**

Artefatto: `cache_vs_fetch.json`.

## 1. La domanda

Il documento scaricato adesso produce lo stesso materiale di quello congelato
nella cache? Se no, un'architettura cache-miss produrrebbe SourceUnit che i
bundle congelati non sanno indirizzare, e la pipeline a valle resterebbe muta.

La cache non è stata modificata: è stata letta per confronto, dopo il fetch.

## 2. Risultati

| Slot | Documento | Unità cache | Unità fetch | Intersezione | Mancanti | Nuove | Drift di testo |
|---|---|---:|---:|---:|---:|---:|---:|
| A | `pmid:24658966` | 9 | 9 | **9** | 0 | 0 | **0** |
| B | `pmcid:PMC248481` | 242 | 242 | **242** | 0 | 0 | **0** |
| C | `pmid:23724867` | 17 | 17 | **17** | 0 | 0 | **0** |

**Corrispondenza esatta su tutti e tre.** Nessun identificatore perso, nessuno
nuovo, nessuna differenza di testo sulle unità comuni.

## 3. Perché è più forte di un confronto di hash

Gli identificatori delle SourceUnit sono `SU-<sha256(document_id, unit_type,
text, offset)>`. Un'intersezione totale significa che il testo estratto oggi è
byte-identico a quello estratto il 2026-08-03 — su 268 unità complessive.

Questo vale **nonostante** i payload PMC abbiano hash diversi a ogni richiesta:
l'envelope OAI incorpora `<responseDate>`, ma il contenuto scientifico che il
parser estrae è invariato. È la stessa conclusione raggiunta nella ricostruzione
della cache, qui confermata su un percorso indipendente.

## 4. Conseguenza architetturale

Un documento recuperato al volo su cache miss produrrebbe SourceUnit
**compatibili con i bundle congelati**. Il materiale live e il materiale
sperimentale non divergono.

Con una riserva onesta: la verifica riguarda tre documenti, non l'intero corpus,
e riguarda documenti già pubblicati e stabili. Non dice nulla su cosa
accadrebbe a un articolo corretto o ritirato dopo la pubblicazione.
