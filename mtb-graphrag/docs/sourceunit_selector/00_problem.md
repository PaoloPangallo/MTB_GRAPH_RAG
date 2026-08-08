# Il problema

**VERIFIABLE RESEARCH PIPELINE — NOT CLINICALLY VALIDATED.**
**Fase sperimentale. Il selector non è integrato nel runtime.**

## 1. Cosa era già stato stabilito

Il recupero documentale live è tecnicamente fattibile. Una sonda precedente ha
mostrato la catena intera:

```
GraphCandidateAssertion -> PMID (dalla provenance)
  -> PubMed E-utilities -> abstract + PMCID dichiarato dalla risposta
  -> PMC OAI -> JATS full text
  -> parser -> SourceUnit con testo
  -> Gemma -> QUOTE / ABSTAIN -> validatore
```

Nessun identificatore viene digitato da un essere umano.

## 2. Cosa restava scoperto

Fra il parser e il modello c'è un passaggio che nessun componente esegue:

```
DOCUMENT -> PARSER -> N SOURCEUNIT -> ??? -> GEMMA
```

Oggi quel `???` è un artefatto congelato. `paper_selection.py:35` legge
`bundle["source_unit_ids"]`, e quel bundle fu costruito una volta dal pilot:

```python
source_unit_ids = bundle["source_unit_ids"]
resolved_units = [uid for uid in source_unit_ids
                  if uid in source_units_by_id and (source_units_by_id[uid].get("text") or "").strip()]
if not text_available:
    excluded.append({... "reason_codes": ["TEXT_NOT_AVAILABLE_IN_CACHE"]})
```

Su un documento recuperato al volo quel bundle non esiste. Senza di esso ogni
bundle viene escluso, e la pipeline arriva allo stage 8 senza paper — con la
cache valida e nessun segnale del perché.

Il numero rende il problema concreto: `PMC248481` produce **243 SourceUnit**. Il
modello ne riceve al massimo quattro. Sceglierle è il componente mancante.

## 3. La domanda di questa fase

> Possiamo selezionare automaticamente e deterministicamente, dal testo di un
> documento recuperato live, le SourceUnit rilevanti per una GCA — senza usare
> bundle congelati e senza affidare la selezione a un LLM?

## 4. Vincoli

| Vincolo | Motivo |
|---|---|
| Nessun LLM nella selezione | Un ranking prodotto da un modello non è né riproducibile né contestabile riga per riga |
| Nessun accesso al gold in inferenza | Usare i bundle per scegliere le unità significherebbe misurare la propria risposta |
| Deterministico | Stesso input, stesso ordine, sempre |
| Spiegabile | Ogni unità selezionata deve poter essere contestata guardando il motivo |
| Nessuna integrazione nel runtime | Questa fase misura, non modifica |

## 5. Cosa il selector **non** deve fare

Non decide se una candidate sia supportata. Non produce `SUPPORTED`,
`UNSUPPORTED`, `DIRECT`, `AMBIGUOUS`, `CONTRADICTED`, né gate, bucket o status.

Risponde a una domanda sola: *quali passaggi meritano di essere mostrati al
modello?* Un'unità in cima al ranking può benissimo non contenere supporto, e
l'astensione del modello resta l'esito corretto.
