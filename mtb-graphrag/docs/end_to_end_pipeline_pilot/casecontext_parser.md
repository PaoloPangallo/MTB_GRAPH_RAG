# CaseContext Parser

Prompt versionato `casecontext-parser-prompt/1.0`
(`casecontext_prompt.py`). Riceve esclusivamente il testo clinico libero;
non interroga il KG, non conosce il risultato atteso. Trasporto: forzato
via endpoint OpenAI-compatible di Ollama (`OLLAMA_FORCED_TOOL_CHOICE`),
tool `submit_case_context`, `gemma4:cloud`, `temperature=0`, `seed=0`.

## Risultati (5/5 chiamate)

Transport valido: 5/5. Nessun campo inventato osservato: ogni valore
prodotto ha un `source_span` letterale verificabile nel testo originale
(confermato dal Match Verifier: 25/25 span controllati risultano `MATCH`,
i restanti 5 record sono `MISSING_IN_TEXT` per campi legittimamente assenti
come `previous_interventions` quando il testo non ne menziona).

`THERAPY_DISCOVERY` correttamente prodotto con `target_intervention=null`
per il Caso 2 (nessuna stringa wildcard, nessuna drug inventata per
riempire il campo). Per il Caso 5, il parser ha estratto fedelmente il
gene fabbricato "ZZTK9 P44R" dal testo — comportamento corretto: il parser
riporta cosa c'è nel testo, non giudica se è clinicamente reale.

Unico limite osservato: gli offset (`start_offset`/`end_offset`)
autoriportati dal modello sono spesso imprecisi di pochi caratteri anche
quando la quote copiata è corretta — per questo il Match Verifier tratta
la presenza letterale della quote come autorevole e usa gli offset solo
per disambiguare occorrenze multiple (vedi `casecontext_match_verifier.md`).
