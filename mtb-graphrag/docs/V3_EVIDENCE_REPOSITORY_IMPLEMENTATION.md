# V3 — repository degli EvidenceStatement e layer di qualificazione

**Branch:** `feat/v3-evidence-repository`, da `b22ab83`.
Implementa i punti 2 e 3 della roadmap V3. **Non** implementa il qualified retrieval.

---

## 1. Audit del codice reale

Verificato leggendo i file, non dedotto.

| Componente | File reale | Responsabilità attuale | Modifica prevista | Stato |
| --- | --- | --- | --- | --- |
| Contratto EvidenceStatement | `schemas/evidence_statement.schema.json` | JSON Schema draft 2020-12, unica fonte di verità | nessuna | **riusato** |
| Adapter V2 → V3 | `backend/pipeline/evidence/v2_adapter.py` | converte record del grafo in statement | nessuna | **riusato** |
| Merger dei duplicati | `v2_adapter.merge_duplicate_records` | fonde proiezioni dello stesso `evidence_id` | riusato dal repository | **riusato** |
| Misure dell'adapter | `backend/pipeline/evidence/adapter_metrics.py` | quattro misure di fedeltà | nessuna | **riusato** |
| SourceClinicalProfile | `benchmarks/mtb_evidence/evaluation/contracts.py` | dataclass frozen, 8 profili annotati | nessuna | **riusato** |
| Repository dei profili | `benchmarks/.../evaluation/source_profiles.py:25` | **pattern Repository esistente** | seguito, non duplicato | **riusato come modello** |
| Errore tipizzato | `source_profiles.ProfileNotFound(KeyError)` | convenzione per lookup mancante | stessa convenzione | **riusato** |
| Serializzazione | `benchmarks/.../pilot/audit_lib/serialize.py` | `write_json`, `write_jsonl`, `read_jsonl`, `canonical_json`, `fingerprint`, scrittura atomica | riusata | **riusato** |
| Fingerprint dello snapshot | `pilot/audit_lib/snapshot.py` | SHA-256 del JSON canonico delle statistiche | letto dal manifest | **riusato** |
| Normalizzazione | `pilot/audit_lib/normalize.py`, `aliases.py`, `disease.py` | casefold, PMID, NCT, alias farmaci, relazioni fra malattie | riusata per gli indici | **riusato** |
| Statement del pilota | `benchmarks/.../evaluation/results/adapter_v1/evidence_statements.jsonl` | 147 statement prodotti dall'adapter | input | **riusato** |
| Test dell'adapter | `backend/tests/test_v2_evidence_adapter.py` | 40 test | restano verdi | **riusato** |
| **Repository degli statement** | `backend/pipeline/evidence/repository.py` | — | — | **nuovo** |
| **Link di qualificazione** | `backend/pipeline/evidence/qualification.py` | — | — | **nuovo** |

### Convenzioni adottate dal progetto

Il pattern Repository esiste già in `SourceClinicalProfileRepository` e viene seguito
invece di introdurne un secondo: costruttore che costruisce gli indici, lookup `by_*`
che restituiscono `None`, un `require` che solleva un errore tipizzato, funzioni di
modulo per il caricamento. Gli errori derivano da eccezioni standard (`KeyError`,
`ValueError`) come `ProfileNotFound`.

La serializzazione passa da `audit_lib/serialize.py`, che scrive in modo atomico e
canonico ed è già coperta da test.

---

## 2. Perché il repository è separato dal Knowledge Graph

Il repository **non** è una cache del grafo. È il livello in cui gli statement esistono
come oggetti interrogabili indipendentemente da Neo4j, e serve a tre cose che il grafo
non può fare:

1. **funzionare offline** — nessun test di questa fase richiede Neo4j, rete o LLM;
2. **isolare per snapshot** — statement provenienti da grafi diversi non si mescolano;
3. **restare immutabile** — il grafo è la fonte, il repository non lo riscrive né lo
   arricchisce.

Il grafo resta la sorgente. Il repository è una vista materializzata e versionata di ciò
che ne è stato estratto, con l'identità di ogni statement riconducibile al record
originale.

## 3. Identità degli statement

Quattro nozioni distinte, che è facile confondere:

| Nozione | Definizione | Conseguenza |
| --- | --- | --- |
| **statement identity** | `evidence_statement_id` | chiave primaria del repository |
| **graph evidence identity** | `provenance.graph_record_ids` | risale al record V2 |
| **projection duplicate** | stesso `evidence_id`, proiezioni diverse | **fuso** field-level |
| **semantic duplicate** | statement diversi con lo stesso significato | **non** collassato |
| **source duplicate** | statement diversi che citano la stessa fonte | **non** collassato |

## 4. Semantica dei duplicati

**Un PMID condiviso non è un duplicato.** Due statement possono citare lo stesso studio
e dire cose diverse: lo stesso lavoro può riportare sensibilità per una popolazione e
resistenza per un'altra. Collassarli perderebbe proprio la distinzione che la V3 esiste
per rappresentare.

Non vengono mai collassati statement che differiscono per: `direction`,
`assertion_polarity`, `disease`, `intervention`, `biomarker`, contesto clinico.

Vengono fusi solo i **projection duplicate**: lo stesso `evidence_id` restituito da
query diverse con colonne diverse. La fusione è field-level e conservativa — un valore
già presente non viene sovrascritto, le liste si uniscono — così il risultato non
dipende dall'ordine delle query.

Se due statement dichiarano lo stesso `evidence_statement_id` con payload incompatibile,
il repository **solleva `DuplicateStatementConflict`** invece di scegliere: scegliere
arbitrariamente il primo o l'ultimo produrrebbe un repository il cui contenuto dipende
dall'ordine di ingestione.

## 5. Order invariance

L'ordinamento dei risultati è dichiarato e non dipende dall'ingestione:

1. malattia normalizzata;
2. biomarcatore normalizzato;
3. intervento normalizzato;
4. primo identificatore di fonte;
5. `evidence_statement_id`.

Il `content_hash` del repository è calcolato sul JSON canonico degli statement ordinati
per `evidence_statement_id`: due ingestioni con ordine diverso producono lo stesso hash.

## 6. Snapshot isolation

Il manifest registra `snapshot_fingerprint`. Il default **rifiuta** statement provenienti
da uno snapshot diverso con `SnapshotMismatchError`. La modalità multi-snapshot esiste ma
va richiesta esplicitamente (`allow_multiple_snapshots=True`) e viene registrata nel
manifest: mescolare snapshot senza dichiararlo renderebbe le metriche non interpretabili.

## 7. Statement, Profile, Link, View

```
Base EvidenceStatement        (origin: frozen_kg, immutabile)
        +
SourceClinicalProfile         (origin: reviewed_source_profile, immutabile)
        +
EvidenceQualificationLink     (spiega il collegamento e i suoi limiti)
        ↓
QualifiedEvidenceView         (derivata, read-only, mai congelata)
```

Nessuno dei primi due viene modificato. Il link non copia i qualificatori dentro lo
statement: registra quali dimensioni *potrebbero* essere aggiunte e quali no.

## 8. Perché un join per PMID non implica applicabilità

È il punto centrale di questa fase.

Un `SourceClinicalProfile` descrive **lo studio**: popolazione, setting, linea di
terapia, criteri di inclusione. Uno `EvidenceStatement` descrive **una proposizione**
estratta da quello studio. Uno studio contiene tipicamente più proposizioni, e non tutte
riguardano la stessa coorte.

Esempio concreto dai dati reali: un profilo dichiara `therapy_line: second line`
riferendosi al braccio principale. Uno statement che cita lo stesso PMID ma riguarda
un'analisi di sottogruppo, o un intervento diverso, o una direzione opposta, non eredita
automaticamente quella linea di terapia.

Prima di rendere una dimensione disponibile nella vista, il link verifica la coerenza
su **malattia, intervento e direzione**. Se il profilo dichiara più coorti o più
interventi e il matching non è risolvibile, lo stato è `ambiguous_match` e **nessun
qualificatore ambiguo viene applicato**.

## 9. Gestione dei conflitti

Un conflitto è una divergenza fra ciò che il profilo dichiara e ciò che lo statement
riporta sulla stessa dimensione — tipicamente la malattia, quando lo statement è annotato
su un sottotipo diverso da quello dello studio.

I conflitti non bloccano il link: lo marcano `conflicting_match`, vengono elencati nella
vista, e le dimensioni coinvolte restano non qualificate. L'informazione resta
disponibile a un revisore invece di sparire.

## 10. Limiti

- Il matching è **solo source-based**. Nessun fuzzy matching sul titolo entra in una
  decisione automatica: il titolo resta un segnale diagnostico.
- Precision e recall del linking **non sono calcolabili**: non esiste un gold di
  collegamento indipendente. Il report riporta conteggi e copertura, e marca
  precision/recall come `not_evaluated` invece di inventare un denominatore.
- Il repository non risolve l'incompletezza del grafo. Le dimensioni che né il KG né i
  profili contengono restano `unknown`.

## Open Decisions

| # | Decisione | Tipo | Note |
| --- | --- | --- | --- |
| R1 | Quali dimensioni sono *bloccanti* per il match (oggi: malattia, intervento, direzione) | **revisione clinica** | aggiungerne altre rende il linking più conservativo |
| R2 | Se un `conflicting_match` debba impedire l'intero link o solo le dimensioni coinvolte | **revisione clinica** | oggi: solo le dimensioni coinvolte |
| R3 | Come rappresentare un profilo multi-coorte | **necessaria prima del retrieval qualificato** | oggi produce `ambiguous_match` |
| R4 | Se il repository debba essere persistito o ricostruito a ogni run | ingegneristica | oggi: ricostruito, artefatti deterministici |
| R5 | Soglia di `qualifier_addition_coverage` accettabile | rimandabile | dipende da quante fonti verranno annotate |

## Prossimo passo

`QualifiedEvidenceRetriever` e primo confronto **V2 contro V3-A** sui quattro casi
development. Questa fase prepara i dati; non implementa il retrieval.
