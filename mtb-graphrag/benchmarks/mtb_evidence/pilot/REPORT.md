# Audit del gold pilota MTB-Evidence contro lo snapshot Neo4j

**Branch:** `feat/pilot-gold-graph-audit` (da `c295e1d`) · **Commit:** `cce87f1`, `63ed143`
**Data:** 21 luglio 2026 · **Fingerprint snapshot:** `ffc97bc7c660f19478c33d28d1599b70e442525f0fae34b512e5efbf0796a9ae`

---

> **Nota di destinazione.** Questo documento contiene le decisioni proposte
> dall'audit (KEEP/AMEND/REPLACE/REJECT) e le divergenze già interpretate. **Non va
> consegnato al secondo annotatore**: vederlo comprometterebbe l'indipendenza della
> seconda revisione, che è uno dei requisiti di freeze. Per quello esiste un
> pacchetto separato e deliberatamente neutro in
> `benchmarks/mtb_evidence/pilot/second_review/`.
>
> Questo report è per chi supervisiona il lavoro.

---

## 1. Perché è stato fatto

Le note di annotazione del bundle (`MTB_Evidence_annotation_notes_v1.md`) dichiarano
che i quattro casi sono una **prima annotazione**, non ancora ground truth congelata.
La regola di freeze richiede sei condizioni; tre non erano soddisfacibili perché
mancava l'evidenza materiale:

- le fonti del gold non erano mai state confrontate con un manifest dello snapshot;
- il caso no-answer (RMI2) non aveva la prova negativa archiviata;
- non esisteva un secondo pacchetto di revisione.

Il problema a monte era più serio: **non era possibile dire contro quale grafo il gold
fosse stato annotato**. Lo snapshot Neo4j del progetto non ha dump, né checksum, né
version stamp. È costruito in modo incrementale con `LOAD CSV` da `import.cypher`, e i
CSV sorgente hanno date di modifica in tre ondate distinte (27 maggio, 31 maggio, 2
giugno 2025): il grafo non corrisponde a un singolo istante di snapshot.

Questo lavoro produce quell'evidenza mancante. È **esclusivamente un audit**: nessun
valore del gold è stato modificato, nessun output del modello è stato usato come
ground truth, e nessuna raccomandazione clinica viene formulata.

## 2. Che cosa è stato costruito

```
mtb-graphrag/benchmarks/mtb_evidence/pilot/
├── input/                      i tre file del bundle, invariati
├── scripts/audit_pilot_gold.py il punto di ingresso
├── audit_lib/                  12 moduli: normalizzazione, confronto, query, report
├── audit/                      gli artefatti prodotti
└── second_review/              il pacchetto per il secondo annotatore
```

più `backend/tests/test_pilot_gold_audit.py` e la sua controparte di integrazione.

Comando di riesecuzione:

```bash
cd mtb-graphrag
PYTHONPATH=. python benchmarks/mtb_evidence/pilot/scripts/audit_pilot_gold.py \
    --gold benchmarks/mtb_evidence/pilot/input/mtb_evidence_gold_pilot_v1.jsonl \
    --output benchmarks/mtb_evidence/pilot/audit
```

L'audit riusa il client Neo4j già configurato dal backend (`backend/pipeline/helpers.run_cypher`,
credenziali da `mtb-graphrag/.env`). Non duplica configurazione e non apre un secondo driver.

## 3. Lo snapshot identificato

Neo4j **2026.04.0 enterprise**, database `neo4j` su `bolt://localhost:7687`.
**43.003 nodi**, **61.185 relazioni**.

| Label | Nodi | | Relazione | Archi |
|---|---:|---|---|---:|
| Drug | 24.502 | | INTERACTS_WITH | 25.589 |
| ClinicalTrial | 5.570 | | TESTS_DRUG | 8.018 |
| Evidence | 4.860 | | ASSOCIATED_GENE | 5.501 |
| Publication | 2.222 | | HAS_EVIDENCE | 4.860 |
| Variant | 1.975 | | CITED_IN | 4.840 |
| MolecularProfile | 1.937 | | HAS_DISEASE | 4.684 |
| Gene | 1.437 | | TARGETS_DRUG | 3.372 |
| Disease | 334 | | IN_MOLECULAR_PROFILE | 2.281 |
| CompanionDiagnostic | 166 | | HAS_VARIANT | 1.727 |

Il **fingerprint** è lo SHA-256 del JSON canonico di: conteggi per label, conteggi per
tipo di relazione, totali e min/max degli identificatori stabili. Non essendoci un hash
ufficiale, questo è ciò che si può garantire — ed è dichiarato per quello che è: *due
grafi diversi con le stesse statistiche collidono*. Serve a rilevare che lo snapshot è
cambiato, non a provarne il contenuto.

## 4. Due trappole trovate interrogando il grafo

Meritano di essere segnalate perché hanno cambiato il disegno dell'audit e perché
chiunque rifaccia questo lavoro ci inciamperebbe.

**`Publication.pmid` è un INTEGER, `Evidence.citation_id` è un array di stringhe.**
Confrontare la forma sbagliata non produce un errore: produce zero risultati. Al primo
tentativo ho dichiarato assenti tutti e otto i PMID attesi; erano un problema di tipo.
La normalizzazione ora emette entrambe le forme e ogni query lega quella corretta.

**Un PMID può esistere solo come citazione, senza nodo `Publication`.** Sono due
situazioni diverse: nel secondo caso la fonte è comunque recuperabile dal grafo.
Trattarle insieme sarebbe stato un falso negativo dell'audit — e infatti per il caso A2
tutti e tre i PMID attesi esistono **solo** in questa forma.

## 5. Un limite di schema che riguarda tutti i casi

Le proprietà di `Evidence` sono: `evidence_id, evidence_type, evidence_level,
evidence_direction, significance, evidence_statement, citation_id, source_type, rating,
variant_origin, disease, doid`.

**Non c'è alcun campo per setting, linea di terapia, stadio o esposizione precedente.**
Sono esattamente i qualificatori su cui i casi K1 e C1 sono costruiti. Recuperarli è
possibile solo come euristica testuale su `evidence_statement`, e ogni classificazione
prodotta porta `classification_basis: "text_heuristic"` più gli span che l'hanno
determinata.

Di conseguenza l'audit distingue due stati che è facile confondere:

- `not_modelled_by_schema` — il grafo non può rappresentare quel qualificatore;
- `absent_in_record` — il grafo potrebbe, ma quel record non lo riporta.

Il primo è un limite dell'infrastruttura, il secondo un dato mancante. Confonderli
falserebbe il giudizio di freeze.

## 6. Le non-fusioni, imposte dal codice

Le tre distinzioni richieste non sono affidate a commenti ma a controlli che falliscono:

- `build_alias_table` alza `ValueError` su qualunque alias che contenga un termine di
  malattia, un termine di tipo-alterazione, una notazione di variante o un separatore
  composto. Un alias `"g1202r/l1196m" → "g1202r"` non è registrabile.
- Il confronto fra malattie separa **vocabolario** (NSCLC ≡ Lung Non-small Cell
  Carcinoma, ammesso), **specificità** (intraepatico vs colangiocarcinoma generico:
  segnalato, mai equiparato) e **qualificatori di stadio**, che vengono estratti e
  mandati alla dimensione non modellata.
- Mutazione singola e composta sono riconosciute dal nome del profilo e tenute in
  bucket separati che nessun passaggio successivo unisce.

Una claim conta come **completamente corrispondente** solo se, oltre a farmaco e PMID,
coincidono variante/profilo, malattia, direzione e fonte. Farmaco e PMID da soli
producono una corrispondenza parziale con l'elenco esplicito dei campi divergenti.

## 7. Risultati per caso

| Caso | Query | Record grezzi | Claim normalizzate | Piene | Parziali | Senza riscontro | Blockers | Decisione |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| K1 FGFR2 iCCA | 11 | 72 | 28 | 0 | 1 | 1 | 5 | **AMEND** |
| A2 ALK G1202R | 11 | 466 | 13 | 1 | 0 | 2 | 2 | **AMEND** |
| C1 EGFR L858R | 11 | 985 | 81 | 2 | 0 | 1 | 3 | **AMEND** |
| N1 RMI2 | 10 | 2 | 0 | 1 | 0 | 0 | 0 | **KEEP** |

### K1 — FGFR2 fusion/rearrangement, colangiocarcinoma intraepatico

Trovati il gene, entrambi i farmaci come nodi `Drug`, e l'evidenza pemigatinib
(PMID 32203698, Evidence 8173). Mancano il PMID 36652354 (futibatinib, FOENIX-CCA2) e
**entrambi** gli NCT attesi; futibatinib esiste come farmaco ma non è raggiungibile dal
traversal per questo profilo.

Il reperto sostanziale è un altro: l'evidenza pemigatinib è annotata su
`Cholangiolocellular Carcinoma`, non su colangiocarcinoma intraepatico. Sottotipo e
categoria non sono intercambiabili — è esattamente la distinzione che il caso richiede
di preservare — quindi è un conflitto di qualificatore, non una corrispondenza.

Il traversal restituisce anche sei terapie non previste dal gold (derazantinib,
erdafitinib, infigratinib, pazopanib, PD173074, ponatinib), su profili in gran parte
di mutazione generica anziché di fusione.

### A2 — ALK G1202R

Tutti e tre i PMID attesi sono presenti, ma **solo come citazioni** in `Evidence`, non
come nodi `Publication`. Manca NCT01970865.

I profili contenenti G1202R sono tre, e la separazione funziona: `ALK G1202R AND v::ALK
Fusion` è correttamente trattata come mutazione singola (G1202R su una fusione ALK,
cioè il contesto normale), mentre `EML4::ALK Fusion AND ALK G1202R AND ALK I1171N AND
ALK L1196M` finisce nel bucket delle mutazioni composte e non viene applicata al caso.

La claim di guardrail A2-C3 sulle compound mutations resta senza riscontro, il che è
coerente: il gold stesso la marca `not_compatible`.

### C1 — EGFR L858R, prima linea avanzata

**È il caso più significativo.** Le due fonti che il gold marca *non applicabili* —
ADAURA (adiuvante, PMID 32955177 + NCT02511106) e AURA3 (T790M, PMID 27959700) —
corrispondono strutturalmente. FLAURA, l'unica direttamente applicabile al caso, **non
ha riscontro**: il PMID 29151359 è assente dallo snapshot, così come NCT02296125 e
NCT02151981.

Detto altrimenti: il grafo copre bene proprio i contesti che il caso deve escludere, e
non copre quello su cui la risposta corretta si fonda. Per una pipeline
snapshot-defined è una condizione avversa, ed è utile che il benchmark la registri.

La classificazione strutturale degli 81 record dà: 40 `insufficient_context`, 22
`post_progression_t790m`, 11 `other`, 5 `first_line_advanced`, 3 `adjuvant_resected` —
tutte per euristica testuale, tutte marcate come tali.

### N1 — RMI2

**Negativo genuino.** Il nodo `Gene` RMI2 esiste (entrez 116028, alias BLAP18,
C16orf75, MGC24665) ma **non ha alcuna relazione di alcun tipo**: zero varianti, zero
profili, zero evidenze, zero interazioni farmacologiche, zero trial.

Un dettaglio che vale la pena segnalare: il nodo porta la proprietà
`categories: ["CLINICALLY ACTIONABLE", "DNA REPAIR"]` pur non avendo alcun percorso
terapeutico. È una trappola per qualunque euristica che usasse quella proprietà come
segnale di azionabilità.

La prova è archiviata in `PILOT-N1-RMI2-SNAPSHOT/negative_path_proof.json` con query,
parametri, risultato completo, conteggio, fingerprint e timestamp. Se in futuro
emergesse anche un solo percorso, lo script lo dichiara freeze blocker invece di
archiviare un negativo.

## 8. Freeze blockers

| Caso | Blockers |
|---|---|
| K1 | PMID 36652354 assente · NCT02052778 e NCT02924376 assenti · futibatinib non raggiungibile · claim K1-C2 senza riscontro · conflitto di specificità sulla malattia |
| A2 | NCT01970865 assente · claim A2-C1 e A2-C3 senza riscontro |
| C1 | PMID 29151359 assente · NCT02151981 e NCT02296125 assenti · claim C1-C1 senza riscontro |
| N1 | nessuno |

Un avvertimento separato, che non blocca il freeze ma va dichiarato: per le claim che
corrispondono, `setting` e `line` restano **non verificabili** sullo snapshot. Una
corrispondenza strutturale non è una conferma di applicabilità clinica.

## 9. Proposte di emendamento

Nove proposte in `proposed_gold_amendments.jsonl`, **nessuna applicata**. Ognuna porta
`requires_human_review: true` insieme a motivazione, record di supporto e confidenza.

| Caso | Campo | Confidenza |
|---|---|---|
| K1 | `expected_pmids` | high |
| K1 | `expected_nct_ids` | high |
| K1 | `expected_therapies` | medium |
| K1 | `claims[K1-C1].disease` | medium |
| K1 | `required_context` | informational |
| A2 | `expected_nct_ids` | high |
| A2 | `required_context` | informational |
| C1 | `expected_pmids` | high |
| C1 | `expected_nct_ids` | high |

La distinzione che attraversa quasi tutte: una fonte assente dallo snapshot resta una
**fonte documentale valida**, ma non può essere pretesa da una pipeline
snapshot-defined. È una decisione sul perimetro del benchmark, non sulla verità della
claim, e spetta a un umano.

## 10. Pacchetto per il secondo revisore

`benchmarks/mtb_evidence/pilot/second_review/` — `review_cases.csv`,
`review_claims.csv`, `review_sources.csv`, `reviewer_instructions.md`.

Il revisore vede domanda, contesto, claim provvisorie, fonti, valori osservati nel
grafo, qualificatori e differenze. **Non** vede la decisione dell'audit, output del
GraphRAG o del planner, né alcuna formulazione che indichi quale risposta accettare: il
pacchetto è costruito da gold e record grezzi, mai dal report, e un test verifica ogni
colonna testuale contro una lista di pattern proibiti.

Le quattro opzioni sono `accept`, `accept_with_changes`, `reject`,
`insufficient_information`.

## 11. Verifica

- **294 test**, tutti verdi (2 skip = integrazione opzionale). 78 sono nuovi.
- Nessun test unitario richiede Neo4j: il grafo è sostituito da un client scriptato.
  Necessario perché `backend/pipeline/llm.py` istanzia driver e client LLM al momento
  dell'import; il client dell'audit risolve la dipendenza dentro il metodo.
- **Determinismo** verificato: due esecuzioni con timestamp fisso producono output
  byte per byte identico, artefatti e CSV compresi.
- **Neo4j irraggiungibile**: exit code 3 e messaggio leggibile con URI sanitizzato,
  nessuna credenziale.
- **Nessuna credenziale negli artefatti**: un test scansiona ricorsivamente ogni file
  prodotto cercando i segreti d'ambiente, userinfo negli URI e password note.
- Integrazione opzionale con `RUN_NEO4J_INTEGRATION=1`: passa.
- **68 file, tutti aggiunte.** Nessun file di frontend, LaTeX o architettura toccato.

## 12. Limiti di questo audit

- Il fingerprint è derivato da statistiche aggregate: identifica una configurazione,
  non prova un contenuto.
- Setting, linea, stadio e resezione non sono modellati. Le classificazioni relative
  sono indizi testuali, non dati.
- L'assenza di un PMID dallo snapshot **non** implica che la pubblicazione non esista,
  né che la claim sia falsa: è un'informazione sulla copertura del grafo.
- Nessuna decisione qui è definitiva. Tutte richiedono la seconda revisione
  indipendente prevista dalle note di annotazione.

## 13. Questione fuori perimetro, segnalata

Nel corso del lavoro sono emersi due problemi di sicurezza preesistenti, che **non ho
toccato** perché estranei al mandato:

- due file `.env` con segreti reali presenti sul disco (root del workspace e
  `mtb-graphrag/`);
- la password `pangallo22` hardcoded come fallback in `scratch/inspect_db.py` e
  `analisi/analisi.py`.

L'ho inserita nella lista dei valori che lo scrubber rimuove dagli artefatti, ma la
fonte resta. Meriterebbe un intervento dedicato, con rotazione della credenziale.

---

## Riepilogo

| | |
|---|---|
| **Decisioni** | K1 AMEND · A2 AMEND · C1 AMEND · N1 KEEP |
| **Freeze-ready** | solo N1 |
| **Gold modificato** | no — 9 proposte, tutte da revisionare |
| **Prova negativa** | archiviata e valida |
| **Test** | 294 verdi |
