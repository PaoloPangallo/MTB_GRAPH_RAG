# Contratto del selector

**VERIFIABLE RESEARCH PIPELINE — NOT CLINICALLY VALIDATED.**

Modulo: `backend/research_pipeline/experimental/sourceunit_selector.py`

## 1. Ingresso

```python
@dataclass(frozen=True)
class SourceUnitSelectionInput:
    candidate_id: str
    document_id: str
    disease: tuple[str, ...]
    genes: tuple[str, ...]
    alterations: tuple[str, ...]
    interventions: tuple[str, ...]
    graph_relation: str | None
    source_units: tuple[Mapping[str, Any], ...]
```

Otto campi, e nient'altro. Un test verifica che l'insieme dei campi sia
esattamente questo: aggiungerne uno che porti informazione posteriore al
grounding sarebbe leakage, e deve costare la rottura di un test.

`from_candidate()` separa geni e alterazioni guardando `biomarkers[].type`. Una
variante trattata come gene perderebbe il proprio peso, ed è la feature più
discriminante disponibile.

## 2. Uscita

```python
@dataclass(frozen=True)
class SourceUnitSelectionResult:
    candidate_id, document_id, status, top_k
    selected_source_unit_ids: tuple[str, ...]
    ranked_source_units: tuple[RankedSourceUnit, ...]
    selection_scores, matched_features, selection_reason
    selector_version, input_hash, ranking_hash, selected_ids_hash
```

`status` vale `SELECTED` oppure `NO_RELEVANT_SOURCE_UNIT`.

Ogni riga del ranking porta con sé quanto serve per contestarla:

```python
@dataclass(frozen=True)
class RankedSourceUnit:
    source_unit_id, rank, score_total, score_lexical, section_prior,
    unit_type, text_length, matched_gene, matched_alteration,
    matched_intervention, matched_disease, context_factor, selection_reason
```

Esempio di `selection_reason` reale:

```
alterazione: V299L · gene: ABL1 · farmaco: dasatinib · tipo unità: FULLTEXT_PARAGRAPH
```

## 3. Riproducibilità (§34)

Tre hash accompagnano ogni selezione:

| Hash | Su cosa |
|---|---|
| `input_hash` | candidate, feature, e gli id delle unità offerte |
| `ranking_hash` | l'ordine completo prodotto |
| `selected_ids_hash` | i soli id selezionati |

Una selezione può quindi essere ricontrollata a posteriori senza conservare il
testo del documento.

## 4. Nessun LLM, nessun gold

Verificato strutturalmente sull'AST del modulo, non cercando parole nei
commenti:

- gli import non contengono `openai`, `ollama`, `transformers`, `torch`,
  `llm_config`, `requests`, `urllib`;
- **nessun import comincia per `backend.`**: il selector non può raggiungere
  `data_access`, i dataset congelati o il retrieval;
- nessun identificatore usato dal codice si chiama `source_unit_ids`,
  `evidence_bundles_path`, `gold`, `author_claim_quote`, `support_status`,
  `bundle`.

In più, un test di inferenza sostituisce le funzioni di `data_access` con
trappole che sollevano: il selector produce comunque il proprio risultato, e il
contatore degli accessi resta a zero.

## 5. Cosa il selector non decide

Nessuno status, nessun gate, nessun bucket. La selezione risponde a «quali
passaggi mostrare», non a «questa candidate è supportata». La distinzione non è
formale: un'unità in cima al ranking può non contenere alcun supporto, e
l'astensione del modello resta l'esito corretto — è successo, ed è documentato
in [07_gemma_end_to_end.md](07_gemma_end_to_end.md).

## 6. Fallimento esplicito (§24)

Quando nessuna unità raggiunge un punteggio positivo, il risultato è
`NO_RELEVANT_SOURCE_UNIT` con selezione vuota. Non viene scelta la «meno
peggio»: consegnare al modello un passaggio irrilevante produrrebbe
un'astensione che sembra un giudizio sull'evidenza e invece è un difetto di
selezione.
