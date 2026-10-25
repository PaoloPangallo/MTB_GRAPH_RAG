# Limiti dello Stadio 2

Due sole run per bundle (run 1, run 2): sufficienti a rilevare instabilità
di transport e a distinguere segnali ripetuti da one-off, ma non a stimare
una vera varianza statistica (servirebbero più di 2 osservazioni per
bundle per un intervallo di confidenza).

Il confronto a tre run (run 0/1/2) è esplicitamente secondario: run 0 mescola
due trasporti diversi (nativo Ollama per 17 bundle, forced-tool per 7),
quindi non è un'osservazione omogenea con run 1/run 2 e i suoi numeri
(es. l'accordo più alto su status/astensione) vanno letti come un
artefatto della selezione post-hoc del trasporto migliore per bundle, non
come una terza misura indipendente di stabilità.

L'etichetta "contraddizione persa" nell'analisi di ricorrenza degli errori
è in parte un effetto strutturale della mappatura deterministica
`ABSTAINED -> AMBIGUOUS` (mai `-> CONTRADICTED`), non necessariamente un
fallimento di comprensione del modello sui 2 bundle baseline
`CONTRADICTED` — vedi `gemma_recurring_errors.md`.

La normalized-value agreement (19%) è pesantemente influenzata dal gran
numero di slot `SAME_AMBIGUITY` (nessun valore validato da nessuna delle
due run) nel denominatore "active"; letta da sola sovrastima l'instabilità
semantica rispetto a quanto osservabile guardando `VALUE_DISAGREEMENT`=0 e
`DIRECTION_DISAGREEMENT`=0 su tutti i 100 slot.

Non è stata condotta un'analisi di correlazione tra dimensione/complessità
del bundle (numero di caratteri, numero di SourceUnit) e fallimento del
transport — utile per capire se `FORCED_TOOL_IGNORED`/`TEXT_RESPONSE` sono
prevedibili o casuali.

Le risposte raw dei modelli non sono committate (solo hash); l'analisi si
basa sulle proposte canoniche post-adapter e sui `reason_codes`.
