# 03 — Prompt del Dossier Narrator

`dossier-narrator-prompt/1.0` — lingua **italiana**, coerente con il frontend.

## Cosa il prompt dichiara

- stai riscrivendo un dossier **già deciso**;
- non stai valutando il caso, non stai facendo evidence grading, non stai
  raccomandando terapia;
- non usare conoscenza esterna, non correggere il dossier, non colmare
  informazioni mancanti;
- preserva status, direzione, warning e limitazioni;
- distingui **candidate** da **recommendation**.

## Regole vincolanti

1. Solo le entità presenti nell'input.
2. Nessuna citazione inventata: se citi, riporta alla lettera una delle
   `validated_quotes`, senza tradurla.
3. Una candidate `AMBIGUOUS` non è «supportata», «confermata», «consolidata».
4. Una fonte che non supporta richiede una **negazione esplicita**.
5. Se non esiste una citazione validata, dillo.
6. Nessun linguaggio prescrittivo.

## Lingua

Italiano. **Non** vanno tradotti: nomi di farmaci, geni, alterazioni, PMID,
identificativi di trial e le citazioni letterali degli autori. Tradurre una
citazione la renderebbe non più verificabile contro la SourceUnit.

## Formulazioni suggerite

> «il sistema ha identificato…», «la candidate è associata nel Knowledge Graph
> a…», «il documento selezionato riporta…», «la citazione validata descrive…»,
> «lo stato canonico della candidate è…», «la relazione rimane ambigua…», «la
> fonte non supporta…», «non è stato trovato supporto documentale esplicito…»

## Il prompt non è la sicurezza

È un'ottimizzazione: rende probabile una narrativa che il verifier accetti. Se
il modello lo ignora, il verifier interviene comunque. Nella run LIVE del
benchmark 25 narrative su 25 hanno superato la verifica, ma il fallback
esisterebbe anche se ne fossero passate zero.
