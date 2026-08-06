# Limitazioni della pipeline live

**VERIFIABLE RESEARCH PIPELINE — NOT CLINICALLY VALIDATED.**

Ciò che il percorso live **non** dimostra. Elencarlo è parte del risultato: una
dimostrazione che non dichiara il proprio perimetro invita a estenderlo per conto
proprio.

## 1. Perimetro dei dati

**Il "grafo" è un repository materializzato, non Neo4j interrogato dal vivo.**
`kg_retrieval` legge `graph_candidate_repository/2.0/candidates.jsonl`, statico e
congelato. Una query Cypher live era fuori scopo già nel pilot.

**La cache contiene 40 documenti.** Un caso clinico che non ricada su uno di
essi si ferma a `DOCUMENT_UNAVAILABLE` o `RETRIEVAL_NO_MATCH`. Il percorso resta
live; ciò che manca è la copertura documentale.

**Il retrieval è ristretto alle candidate che hanno già un EvidenceBundle
congelato.** È deliberato — impedisce che una run scarichi documenti nuovi — ma
significa che la selezione delle candidate non è quella che si avrebbe su un
grafo completo.

## 2. Perimetro dell'esperimento

**Campione minuscolo.** 5 casi sintetici, 10 chiamate al modello, 5 proposte di
enrichment. Non è una valutazione: è una verifica di meccanica.

**Nessun ground truth clinico è stato usato per giudicare gli output.** Il
validatore verifica letteralità e coerenza strutturale, non correttezza clinica.

**Casi composti a partire da record noti.** Gli esiti attesi erano noti in
anticipo. Questo rende il percorso verificabile e rende l'esperimento inadatto a
misurare accuratezza.

## 3. Limiti noti del validatore

**Nessuna tabella di sinonimi per i farmaci.** CASE-4 lo ha mostrato: il modello
ha citato correttamente una frase su *BGJ398*, il farmaco richiesto era
*infigratinib*, e il validatore — che confronta stringhe normalizzate — ha
rigettato con `DRUG_NOT_PRESENT_IN_PASSAGE`. È un falso negativo.

Non è stato corretto in questo lavoro, e la ragione conta: la soluzione a una
tabella di sinonimi mancante non è allentare il controllo di letteralità.
Aggiungere sinonimi è un cambiamento al validatore, che richiede la propria
valutazione.

**Overlap lessicale come misura di ancoraggio.** Il controllo che il summary sia
ancorato alla quote usa una soglia sull'intersezione di parole di contenuto
(0.25 / 0.50). È una euristica, non una verifica semantica.

## 4. Stage non implementati

`stage_14_narrator` e `stage_15_narrative_verifier` esistono nel contratto e
sono **permanentemente** `SKIPPED` con `NOT_APPLICABLE`. `PipelineStage`
rifiuta di costruirli con qualunque altro stato. Nessuna narrazione è generata.

## 5. Casi non eseguiti live

**CASE-2** è stato eseguito in REPLAY esplicito: live sarebbe costato 3 chiamate
su un residuo di 1. È etichettato REPLAY ovunque compaia, con
`replay_artifacts_used = 6` e `llm_calls = 0`.

**CASE-6** resta un test automatico. Produrre un `CASECONTEXT_MISMATCH` dal
modello reale richiederebbe che il parser inventi un campo assente dal testo:
non lo si può chiedere in modo affidabile. Il test è etichettato `TEST SCENARIO`
e non è presentato come demo.

## 6. Ambiente

**Ollama Cloud è raggiunto attraverso l'app Ollama locale**, che fa da proxy
autenticato. `gemma4:cloud` non è un modello scaricato in locale — è risolto come
modello cloud con capability `tools`. È lo stesso percorso del pilot `6ee64c5`.
Il transport funziona identicamente contro `https://api.ollama.com` con
`OLLAMA_API_KEY`, ma quella configurazione non è stata esercitata qui.

**La cache vive in un worktree temporaneo.** È fuori dal repository per scelta —
contiene testo di terzi — ma la sua posizione attuale non è un'installazione
stabile. `RESEARCH_DOCUMENT_CACHE_PATH` va configurata su ogni macchina.

**Verifica nel browser non eseguita.** L'estensione Chrome non era connessa
durante questa sessione. Il comportamento della UI è coperto da 182 test
frontend e dalla verifica HTTP degli endpoint che la UI consuma; una prova
visiva resta da fare.

## 7. Prestazioni

Una chiamata all'enricher ha impiegato **61 secondi** (CASE-3, primo paper).
Nessun timeout è scattato — il limite è 60 secondi per richiesta, e la latenza
misurata include il tempo di risposta completo. La variabilità osservata va da
3.3 a 61.5 secondi. Non è stata caratterizzata.

## 8. Cosa resta vero

- La pipeline **non** è un runtime clinico validato.
- **Non** produce raccomandazioni cliniche, e il validatore rigetta i summary
  che ne contengono.
- Gemma **non** decide status, gate, bucket, score, direzione o contraddizione.
- Un'astensione è un esito legittimo, non un guasto.
