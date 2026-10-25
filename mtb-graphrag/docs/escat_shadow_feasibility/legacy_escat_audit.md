# Audit della logica ESCAT legacy

## Funzione e input

La logica è in backend/pipeline/agents/variant_interpreter.py, funzione
_variant_interpreter_core.

Input principali da MTBState:

- gene;
- variant;
- tumor_type;
- alteration_type;
- disease_keywords derivati dal tumor_type.

La funzione interroga query Cypher diverse per point_mutation/itd, biomarker e
fusion/cna/atypical. I record usati per il prompt includono significance,
evidence_level, disease e PMID. Le query filtrano alcuni evidence_level
ammessi, ma non un campo ESCAT.

## Regole osservate

| regola | comportamento | classificazione |
|---|---|---|
| prompt con definizioni Tier I/II | chiede a un LLM un tier globale | UNKNOWN_ORIGIN |
| output ammessi I-A, I-B, I-C, II, II-B, non determinato | restringe il vocabolario e non copre tutti i valori richiesti | HEURISTIC_APPROXIMATION |
| evidence_level A/B/LEVEL_1/LEVEL_2 nel prompt | usa scale generiche come input al giudizio | GENERIC_EVIDENCE_MAPPING |
| significance Resistance | fallback sempre non determinato | HEURISTIC_APPROXIMATION |
| confronto disease con substring/keyword | definisce match dello stesso tumore | HEURISTIC_APPROXIMATION |
| stesso tumore e livello A/B/C/D | mappa A->I-A, B->I-B, C->II-A, D->II-B | GENERIC_EVIDENCE_MAPPING |
| tumore diverso | declassa A/B/C a II-A/II-B/non determinato | HEURISTIC_APPROXIMATION |
| risposta II-A | viene riscritta come II | UNSUPPORTED_INFERENCE |
| nessun record o eccezione | restituisce non determinato | EXPLICIT_DEFAULT, non regola ESCAT verificata |

Le categorie EXPLICIT_ESCAT_RULE, HEURISTIC_APPROXIMATION,
GENERIC_EVIDENCE_MAPPING, UNSUPPORTED_INFERENCE e UNKNOWN_ORIGIN sono
classificazioni dell'origine della regola, non giudizi clinici.

## LLM e dipendenze

La funzione invoca llm.invoke con SystemMessage. Il client è configurato in
backend/pipeline/llm/__init__.py con temperatura 0.0, modello configurabile e
endpoint Ollama configurabile. Il valore restituito dal modello viene
normalizzato e validato contro un set ristretto; se non valido entra il
fallback euristico.

Il risultato quindi dipende da:

- query e filtri locali;
- keyword disease;
- modello LLM e prompt;
- output parsing;
- fallback;
- assenza di una versione ESCAT e di una fonte normativa registrata.

## Fonti e test

Il prompt dichiara il nome ESMO Scale for Clinical Actionability of molecular
Targets, ma non collega una versione, DOI, regola o passage locale. La voce R6
di docs/V3_POSITIONING.md è un riferimento bibliografico da verificare e
dichiara esplicitamente che le definizioni originali devono ancora essere
controllate.

I test locali trovati verificano la presenza del campo escat_tier nello stato e
negli eventi, ma non verificano le regole cliniche di
variant_interpreter.py. Non è stato trovato un test che dimostri una
assegnazione ESCAT con fonte versionata.

## Conclusione

La logica legacy non è riutilizzabile come assegnatore shadow. Può essere
conservata solo come comportamento storico da confrontare, marcato
LEGACY_DERIVED e non come annotazione esplicita o ground truth.
