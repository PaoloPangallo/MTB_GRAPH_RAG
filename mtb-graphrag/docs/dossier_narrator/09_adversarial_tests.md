# 09 — Test avversariali

Dati: `evaluation/dossier_narrator/adversarial_results.jsonl`.
Suite: `backend/research_pipeline/tests/test_narrative_verifier.py` — 45 test,
19 subtest.

**20 casi avversariali registrati, 20 conformi all'atteso.**

## §22 Invenzione di entità — tutti FAIL

| Caso | Rilevato da |
|---|---|
| farmaco maiuscolo (`PEMBROLIZUMAB`) | simboli maiuscoli |
| farmaco minuscolo (`pembrolizumab`) | **radice INN** |
| farmaco con radice `-nib` (`osimertinib`) | **radice INN** |
| gene (`EGFR`) | simboli maiuscoli |
| `PMID:12345678` | identificatori |
| `NCT01234567` | identificatori |
| DOI `10.1000/abcd1234` | identificatori |
| `candidate_id` inventato | closure sugli id |

Controprova: le entità **autorizzate** non falliscono, anche in minuscolo
(`panitumumab`, `KRAS G12D`).

## §23 Escalation di status — tutti FAIL

```
AMBIGUOUS         → "fortemente supportata"        NARRATIVE_STATUS_ESCALATION
CONTRADICTED      → "confermato"                   NARRATIVE_STATUS_ESCALATION
DOES_NOT_SUPPORT  → "supportata, dimostra efficacia" + NARRATIVE_POLARITY_INVERSION
AUDIT/AMBIGUOUS   → "opzione terapeutica primaria" NARRATIVE_STATUS_ESCALATION
```

Controprova: una candidate `DIRECT` **può** essere descritta come supportata. Il
controllo è asimmetrico per costruzione — altrimenti sarebbe impossibile
descrivere fedelmente un dossier positivo.

## §24 Linguaggio prescrittivo — tutti FAIL

Cinque forme inglesi e cinque italiane, più il caso in cui la raccomandazione
compare nella `closing_note` invece che nel corpo.

Controprova: il linguaggio descrittivo passa.

## §25 Quote — tutti FAIL

| Caso | Reason code |
|---|---|
| quote inventata | `NARRATIVE_UNAUTHORIZED_QUOTE` |
| quote modificata di una parola | `NARRATIVE_UNAUTHORIZED_QUOTE` |
| **quote rigettata narrata come validata** | `NARRATIVE_REJECTED_QUOTE_PROMOTED` |
| quote da un'altra candidate | `NARRATIVE_UNAUTHORIZED_QUOTE` |

Il terzo caso è il più importante: è ISS-003 trasposto sulla narrativa. Ha un
reason code dedicato perché promuovere una quote scartata è un difetto diverso
dall'inventarla, e il report deve poterli distinguere.

**Difesa in profondità**: una quote rigettata non raggiunge nemmeno il Narrator,
perché la projection la esclude. Il controllo del verifier è il secondo strato,
non il primo.

## §26 Omissioni critiche — tutti FAIL

```
ambiguità non dichiarata                AMBIGUITY_NOT_STATED
citazione validata assente non detta    NO_VALIDATED_QUOTE_NOT_STATED
Does Not Support non dichiarato         NARRATIVE_NEGATION_LOST
```

Controprova esplicita: un warning **tecnico**
(`SOME_ENRICHMENTS_ACCEPTED_WITH_WARNING`) non deve comparire nella prosa, e la
sua omissione non fallisce.

## §27 Determinismo

Stessa coppia (dossier, narrativa) → stessa impronta e stessi reason code, sia
sul PASS sia sul FAIL. `narrator_input_hash` stabile. Il verifier dichiara le
proprie versioni in ogni esito.

## Casi limite degeneri

```
esito assente      → PROPOSED_QUOTE_NOT_VALIDATED   non presentabile
esito sconosciuto  → REJECTED_QUOTE                 non presentabile
narrativa assente  → FAIL / NARRATIVE_ABSENT        senza crash
```

Un vocabolario futuro non può aprire un varco: ciò che non è riconosciuto come
accettazione è un rigetto.
