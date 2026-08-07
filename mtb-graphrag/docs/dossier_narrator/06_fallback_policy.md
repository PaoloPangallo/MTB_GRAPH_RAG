# 06 — Policy di fallback

## La regola

```
NARRATIVE VERIFIER FAIL  →  la narrativa NON viene mostrata
                         →  STRUCTURED_DOSSIER_FALLBACK
```

Il dossier strutturato resta completo e visibile. Non viene mai nascosto.

## Cosa NON viene fatto

- **nessun secondo passaggio LLM** per correggere la narrativa;
- **nessun retry semantico**;
- nessuna richiesta al modello del tipo «correggi gli errori».

Un retry tecnico resta ammesso soltanto per timeout, trasporto malformato o
fallimento della tool call — ed è già implementato in
`transport.post_with_infra_retry`, che ritenta solo su 5xx, timeout ed errori di
connessione, mai su un esito semantico.

Un test conta le invocazioni: davanti a una narrativa che fallisce la verifica,
il modello è chiamato **una volta sola**.

## Perché non correggere automaticamente

Chiedere al modello di correggere la propria narrativa significherebbe usare il
modello per riparare un difetto che il modello ha introdotto, e affidarsi a lui
per stabilire quando ha finito. Il fallback strutturato è invece un esito
definito: il dossier canonico esiste già, è completo, ed è la cosa che volevamo
mostrare.

## Cosa vede l'utente

| Stato | Contenuto |
|---|---|
| `VERIFICATA` | narrativa + hash + versione del verifier |
| `NON DISPONIBILE — FALLBACK STRUTTURATO` | reason code + dossier strutturato |

La UI dichiara esplicitamente che il dossier strutturato resta completo e
consultabile.

## Osservabilità

`STRUCTURED_FALLBACK_USED` è un evento di dominio sul ledger append-only, con
`stage_id`, reason code, `narrator_input_hash` e `narrative_hash`. Un fallback
non è silenzioso: è un fatto registrato.
