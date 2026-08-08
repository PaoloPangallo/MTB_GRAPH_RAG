# Analisi del drift degli hash

**VERIFIABLE RESEARCH PIPELINE — NOT CLINICALLY VALIDATED.**

Artefatto: `hash_drift_report.json`.

## 1. Il fatto

23 dei 40 documenti recuperati hanno un SHA-256 diverso da quello registrato nel
manifest congelato.

| Sorgente | File | Esito |
|---|---:|---|
| `pubmed/abstracts/` | 17 | `HASH_MATCH` |
| `pubmed/metadata/` | 17 | `HASH_MATCH` |
| `pmc/xml/` | 11 | `HASH_MISMATCH` |
| `clinical_trials/` | 12 | `HASH_MISMATCH` |

Un mismatch ha due spiegazioni possibili con conseguenze opposte: il payload è
**non deterministico**, oppure il **contenuto è cambiato**. Dedurlo dai nomi
delle sorgenti non è ammissibile, e la baseline non conserva i payload originali
con cui fare un diff.

## 2. L'esperimento

Il discriminante è scaricare due volte **adesso** lo stesso documento. Se i due
hash differiscono fra loro, il payload è non deterministico e l'hash della
baseline non era riproducibile nemmeno il giorno in cui fu scritto.

| Sorgente | Fetch 1 vs Fetch 2 | Verdetto |
|---|---|---|
| PMC (`PMC248481`) | **diversi** | `PAYLOAD_NONDETERMINISTIC` |
| ClinicalTrials (`NCT02624973`) | identici | `PAYLOAD_STABLE_ACROSS_FETCHES` |

### PMC — non determinismo strutturale

L'envelope OAI-PMH incorpora l'istante della risposta:

```xml
<OAI-PMH ...>
    <responseDate>2026-08-08T07:38:06Z</responseDate>
```

Ogni richiesta produce quindi un file diverso, a contenuto scientifico
invariato. Gli 11 mismatch PMC sono spiegati, e nessun confronto di hash su
questa sorgente potrà mai avere successo.

### ClinicalTrials — payload stabile ma mutato

Due fetch consecutivi danno lo stesso hash: la sorgente è deterministica oggi.
Il mismatch rispetto al 2026-08-03 indica quindi un cambiamento reale del
record. I marcatori presenti sono `derivedSection`, `lastUpdatePostDateStruct`,
`statusVerifiedDate` — sezioni ricalcolate dal registro e metadata di stato.

Il non determinismo non basta a spiegarli. Serve il secondo canale probatorio.

## 3. Prova a livello di testo

L'hash del payload non è ciò che il runtime consuma. Ciò che consuma è il testo
estratto, e per quello esiste una prova più forte: se ogni SourceUnit ri-parsata
oggi compare nell'indice congelato, il testo da cui deriva è byte-identico,
perché l'identificatore è `SU-<sha256(document_id, unit_type, text, offsets)>`.

Per tutti e 12 i documenti ClinicalTrials: **tutte le SourceUnit prodotte
appartengono all'indice congelato** (130 unità su 130).

I campi che alimentano l'estrazione — `briefTitle`, `briefSummary`,
`detailedDescription`, `conditions`, `interventions` — non sono cambiati. È
cambiato ciò che sta attorno, e che la pipeline non legge.

## 4. Classificazione finale

| Verdetto | Documenti |
|---|---:|
| `EXPLAINED_NONDETERMINISTIC_PAYLOAD` | 11 (PMC) |
| `EXPLAINED_TEXT_UNCHANGED` | 12 (ClinicalTrials) |
| **`UNEXPLAINED`** | **0** |

Nessun hash storico è stato sostituito, e il manifest congelato non è stato
modificato: i `content_hash` originali restano quelli del 2026-08-03, e
continuano a divergere. È una proprietà registrata, non un difetto corretto.

## 5. Conseguenza per la provenance

`content_hash` resta utile come lineage del documento del pilot, ma **non è un
criterio di validazione della cache ricostruita** per PMC e ClinicalTrials. Il
criterio verificabile è l'allineamento degli identificatori delle SourceUnit,
che è esatto — vedi [05_source_unit_reconstruction.md](05_source_unit_reconstruction.md).
